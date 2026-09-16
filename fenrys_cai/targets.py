from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


@dataclass
class Host:
    address: str
    id: str = field(default_factory=lambda: _id("host"))
    hostname: str = ""
    os_fingerprint: str = ""
    status: str = "unknown"
    evidence: list[str] = field(default_factory=list)
    confidence: float = 0.0
    first_seen: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


@dataclass
class Service:
    host_id: str
    port: int
    protocol: str = "tcp"
    id: str = field(default_factory=lambda: _id("svc"))
    service: str = ""
    version: str = ""
    state: str = "unknown"
    confidence: float = 0.0
    evidence: list[str] = field(default_factory=list)


@dataclass
class Endpoint:
    url: str
    id: str = field(default_factory=lambda: _id("endpoint"))
    method: str = "GET"
    host_id: str = ""
    status_observation: int | None = None
    technologies: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    confidence: float = 0.0


def upsert_by_identity(items: list, item, identity) -> None:
    for existing in items:
        if identity(existing) == identity(item):
            for evidence_id in item.evidence:
                if evidence_id not in existing.evidence:
                    existing.evidence.append(evidence_id)
            for key, value in vars(item).items():
                if key not in {"id", "evidence", "first_seen"} and value not in ("", None, "unknown", 0.0, []):
                    setattr(existing, key, value)
            return
    items.append(item)
