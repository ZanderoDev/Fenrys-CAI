import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .models import ToolResult, ToolSpec
from .runtime import LocalTerminalRuntime
from .artifacts import ArtifactStore
from .security import DEFAULT_REDACTOR


class ToolProvider:
    name: str
    def discover(self) -> list[ToolSpec]: raise NotImplementedError
    def invoke(self, name: str, arguments: dict[str, Any]) -> ToolResult: raise NotImplementedError


class ToolRegistry:
    def __init__(self, artifact_store: ArtifactStore | None = None, spill_threshold: int = 32 * 1024) -> None:
        self._providers: dict[str, ToolProvider] = {}
        self._tools: dict[str, tuple[ToolSpec, ToolProvider]] = {}
        self.artifact_store = artifact_store
        self.spill_threshold = spill_threshold

    def register_provider(self, provider: ToolProvider) -> None:
        self._providers[provider.name] = provider
        for spec in provider.discover():
            if spec.name in self._tools:
                raise ValueError(f"Duplicate tool name: {spec.name}")
            self._tools[spec.name] = (spec, provider)

    def register_provider_if_available(self, provider: ToolProvider) -> bool:
        """Register an optional provider without making provider availability core-critical."""
        try:
            self.register_provider(provider)
            return True
        except Exception:
            return False

    def discover(self, capabilities: set[str] | None = None) -> list[ToolSpec]:
        return [spec for spec, _ in self._tools.values() if not capabilities or capabilities.intersection(spec.capabilities)]

    def invoke(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        if name not in self._tools:
            return ToolResult(status="error", tool=name, error="Tool unavailable")
        spec, provider = self._tools[name]
        result = provider.invoke(name, arguments)
        result.stdout = DEFAULT_REDACTOR.redact_text(result.stdout)
        result.stderr = DEFAULT_REDACTOR.redact_text(result.stderr)
        result.error = DEFAULT_REDACTOR.redact_text(result.error) if result.error else None
        result.provenance = DEFAULT_REDACTOR.redact_mapping(result.provenance)
        if self.artifact_store:
            for stream in ("stdout", "stderr"):
                value = getattr(result, stream)
                if len(value.encode()) > self.spill_threshold:
                    artifact = self.artifact_store.save(value.encode(), kind="tool-output", name=f"{name}-{stream}.txt",
                        content_type="text/plain", source=provider.name, tool=name,
                        provenance={"stream": stream, "provider": provider.name})
                    result.artifacts.append(artifact.id)
                    result.artifact_metadata.append(artifact.to_dict())
                    setattr(result, stream, value[:self.spill_threshold])
        result.provenance["provider"] = provider.name
        result.provenance["tool_spec"] = spec.name
        return result


class LocalProvider(ToolProvider):
    name = "local"
    def __init__(self, runtime: LocalTerminalRuntime) -> None: self.runtime = runtime
    def discover(self) -> list[ToolSpec]:
        return [
            ToolSpec("read_file", "Read a bounded file relative to the current Fenrys session workspace. Do not invent absolute host paths.", {
                "type": "object", "additionalProperties": False,
                "properties": {"path": {"type": "string", "description": "Workspace-relative file path."}, "session_id": {"type": "string"},
                               "offset": {"type": "integer", "minimum": 0}, "limit": {"type": "integer", "minimum": 1, "maximum": 65536}},
                "required": ["path", "session_id"]}, ("filesystem",)),
            ToolSpec("write_file", "Create, overwrite, or append a workspace-relative file. Paths cannot escape the current session workspace.", {
                "type": "object", "additionalProperties": False,
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}, "session_id": {"type": "string"},
                               "mode": {"type": "string", "enum": ["overwrite", "append"]}},
                "required": ["path", "content", "session_id"]}, ("filesystem",)),
            ToolSpec("execute", "Run a simple bounded command in the current session workspace, or manage a known background process. Use only known paths and valid shell syntax.", {
                "type": "object", "additionalProperties": False,
                "properties": {"command": {"type": "string"}, "session_id": {"type": "string"}, "background": {"type": "boolean"},
                               "stdin": {"type": "string"}, "timeout": {"type": "number", "exclusiveMinimum": 0},
                               "env": {"type": "object", "additionalProperties": {"type": "string"}}, "pty": {"type": "boolean"},
                               "action": {"type": "string", "enum": ["run", "poll", "wait", "terminate"]}, "process_id": {"type": "string"}},
                "required": ["session_id"]}, ("terminal", "process")),
        ]
    def _path(self, raw: str, session_id: str) -> Path:
        root = self.runtime.session(session_id).cwd.resolve()
        path = (root / raw).resolve() if not Path(raw).is_absolute() else Path(raw).resolve()
        if not path.is_relative_to(root): raise ValueError("Path is outside the session workspace")
        return path
    def invoke(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        session_id = arguments.get("session_id", "default")
        try:
            if name == "execute":
                action = arguments.get("action", "run")
                if action != "run": return getattr(self.runtime, action)(arguments["process_id"], arguments.get("timeout")) if action == "wait" else getattr(self.runtime, action)(arguments["process_id"])
                return self.runtime.execute(arguments["command"], session_id, background=arguments.get("background", False), stdin=arguments.get("stdin"), timeout=arguments.get("timeout"), env=arguments.get("env"), pty=arguments.get("pty", False))
            path = self._path(arguments["path"], session_id)
            if name == "read_file":
                data = path.read_bytes()
                offset, limit = arguments.get("offset", 0), arguments.get("limit", 65536)
                selected = data[offset:offset + limit]
                return ToolResult(status="success", tool=name, stdout=selected.decode(errors="replace"), cwd=str(path.parent), artifacts=[str(path)], observations=["binary data replaced" if b"\0" in selected else ""])
            path.parent.mkdir(parents=True, exist_ok=True)
            mode = "a" if arguments.get("mode") == "append" else "w"
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
                handle.write(arguments["content"])
                temporary = Path(handle.name)
            if mode == "a":
                with path.open("a", encoding="utf-8") as handle: handle.write(temporary.read_text())
                temporary.unlink()
            else: os.replace(temporary, path)
            return ToolResult(status="success", tool=name, cwd=str(path.parent), artifacts=[str(path)])
        except (KeyError, OSError, ValueError) as exc:
            return ToolResult(status="error", tool=name, error=DEFAULT_REDACTOR.redact_exception(exc), cwd=str(self.runtime.session(session_id).cwd))
