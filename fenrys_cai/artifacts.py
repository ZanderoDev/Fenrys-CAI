from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, BinaryIO, Protocol

from .security import DEFAULT_REDACTOR, Redactor


@dataclass(frozen=True)
class Artifact:
    id: str
    kind: str
    name: str
    path: str
    size: int
    content_type: str
    sha256: str
    source: str
    tool: str
    target: str
    timestamp: float
    provenance: dict[str, Any] = field(default_factory=dict)
    retention: str = "session"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ArtifactStore(Protocol):
    def save(self, data: bytes, *, kind: str, name: str, content_type: str = "application/octet-stream", source: str = "", tool: str = "", target: str = "", provenance: dict[str, Any] | None = None) -> Artifact: ...
    def read(self, artifact_id: str, offset: int = 0, limit: int = 64 * 1024) -> bytes: ...
    def metadata(self, artifact_id: str) -> Artifact: ...
    def exists(self, artifact_id: str) -> bool: ...
    def delete(self, artifact_id: str) -> None: ...


class LocalArtifactStore:
    def __init__(self, root: Path, *, max_artifact_bytes: int = 64 * 1024 * 1024, redactor: Redactor = DEFAULT_REDACTOR) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.max_artifact_bytes = max_artifact_bytes
        self.redactor = redactor

    def _paths(self, artifact_id: str) -> tuple[Path, Path]:
        if not re_valid_id(artifact_id):
            raise ValueError("Invalid artifact ID")
        data = (self.root / f"{artifact_id}.bin").resolve()
        meta = (self.root / f"{artifact_id}.json").resolve()
        if not data.is_relative_to(self.root) or not meta.is_relative_to(self.root):
            raise ValueError("Artifact path escapes artifact root")
        return data, meta

    def save(self, data: bytes, *, kind: str, name: str, content_type: str = "application/octet-stream", source: str = "", tool: str = "", target: str = "", provenance: dict[str, Any] | None = None) -> Artifact:
        if len(data) > self.max_artifact_bytes:
            raise ValueError("Artifact exceeds configured size limit")
        artifact_id = f"art_{uuid.uuid4().hex}"
        path, metadata_path = self._paths(artifact_id)
        path.write_bytes(data)
        artifact = Artifact(artifact_id, kind, self.redactor.redact_text(Path(name).name), str(path), len(data), content_type,
                            hashlib.sha256(data).hexdigest(), source, tool, target, time.time(),
                            self.redactor.redact_mapping(provenance or {}))
        metadata_path.write_text(json.dumps(artifact.to_dict(), sort_keys=True), encoding="utf-8")
        return artifact

    def metadata(self, artifact_id: str) -> Artifact:
        _, path = self._paths(artifact_id)
        return Artifact(**json.loads(path.read_text(encoding="utf-8")))

    def read(self, artifact_id: str, offset: int = 0, limit: int = 64 * 1024) -> bytes:
        if offset < 0 or limit < 0 or limit > 1024 * 1024:
            raise ValueError("Invalid bounded artifact range")
        path, _ = self._paths(artifact_id)
        with path.open("rb") as handle:
            handle.seek(offset)
            return handle.read(limit)

    def preview(self, artifact_id: str, offset: int = 0, limit: int = 4096) -> str:
        return self.redactor.redact_text(self.read(artifact_id, offset, limit).decode(errors="replace"))

    def exists(self, artifact_id: str) -> bool:
        data, meta = self._paths(artifact_id)
        return data.exists() and meta.exists()

    def delete(self, artifact_id: str) -> None:
        for path in self._paths(artifact_id):
            path.unlink(missing_ok=True)


def re_valid_id(value: str) -> bool:
    return value.startswith("art_") and len(value) == 36 and all(char in "0123456789abcdef" for char in value[4:])
