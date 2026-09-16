import os
import resource
import signal
import subprocess
import tempfile
import time
import uuid
import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from .config import RuntimeConfig
from .artifacts import LocalArtifactStore
from .models import ToolResult
from .security import DEFAULT_REDACTOR


@dataclass
class TerminalSession:
    id: str
    cwd: Path
    env: dict[str, str]


@dataclass
class ManagedProcess:
    id: str
    process: subprocess.Popen[bytes]
    cwd: Path
    started: float = field(default_factory=time.monotonic)
    stdout_path: Path | None = None
    stderr_path: Path | None = None
    pid: int | None = None
    command_fingerprint: str = ""
    session_id: str = ""
    workspace: str = ""
    owner_runtime_id: str = ""
    state: str = "running"


class LocalTerminalRuntime:
    """Session-isolated local process runtime; orchestration never handles subprocesses."""
    def __init__(self, config: RuntimeConfig) -> None:
        self.config = config
        self.config.workspace.mkdir(parents=True, exist_ok=True)
        self.runtime_id = f"runtime_{uuid.uuid4().hex}"
        self.artifact_store = LocalArtifactStore(self.config.workspace / ".artifacts", max_artifact_bytes=self.config.max_artifact_bytes)
        self._sessions: dict[str, TerminalSession] = {}
        self._processes: dict[str, ManagedProcess] = {}

    def session(self, session_id: str) -> TerminalSession:
        if session_id not in self._sessions:
            cwd = self.config.workspace / session_id
            cwd.mkdir(parents=True, exist_ok=True)
            self._sessions[session_id] = TerminalSession(session_id, cwd, dict(os.environ))
        return self._sessions[session_id]

    def _bounded(self, value: bytes) -> tuple[str, bool]:
        truncated = len(value) > self.config.max_output_bytes
        return value[:self.config.max_output_bytes].decode(errors="replace"), truncated

    def _capture_files(self) -> tuple[Path, Path]:
        stdout = Path(tempfile.mkstemp(prefix="fenrys-stdout-", dir=self.config.workspace)[1])
        stderr = Path(tempfile.mkstemp(prefix="fenrys-stderr-", dir=self.config.workspace)[1])
        return stdout, stderr

    def _read_capture(self, path: Path) -> tuple[str, bool]:
        with path.open("rb") as handle:
            selected = handle.read(self.config.max_output_bytes + 1)
        text, exceeded = self._bounded(selected)
        return text, exceeded or path.stat().st_size >= self.config.max_output_bytes

    def _output(self, path: Path, *, stream: str) -> tuple[str, list[str], list[dict]]:
        size = path.stat().st_size
        if size > self.config.artifact_threshold_bytes:
            data = path.read_bytes()[:self.config.max_artifact_bytes]
            artifact = self.artifact_store.save(data, kind="process-output", name=f"{stream}.log", content_type="text/plain",
                                                source="local-runtime", tool="execute", provenance={"stream": stream})
            preview = DEFAULT_REDACTOR.redact_text(data[:self.config.max_output_bytes].decode(errors="replace"))
            return preview, [artifact.id], [artifact.to_dict()]
        text, _ = self._read_capture(path)
        return DEFAULT_REDACTOR.redact_text(text), [], []

    def _limits(self):
        memory = self.config.max_memory_mb * 1024 * 1024
        def apply() -> None:
            resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
            resource.setrlimit(resource.RLIMIT_CPU, (max(1, int(self.config.timeout_seconds)), max(2, int(self.config.timeout_seconds) + 1)))
            resource.setrlimit(resource.RLIMIT_FSIZE, (self.config.max_output_bytes, self.config.max_output_bytes))
            os.setsid()
        return apply

    def execute(self, command: str, session_id: str, *, background: bool = False,
                stdin: str | None = None, timeout: float | None = None,
                env: dict[str, str] | None = None, pty: bool = False) -> ToolResult:
        if pty and not background:
            return ToolResult(status="error", tool="execute", error="PTY commands must run in the background", cwd=str(self.session(session_id).cwd))
        session = self.session(session_id)
        effective_env = {**session.env, **(env or {})}
        effective_env["FENRYS_RUNTIME_ID"] = self.runtime_id
        started = time.monotonic()
        try:
            stdout_path, stderr_path = self._capture_files()
            stdout_handle = stdout_path.open("wb")
            stderr_handle = stderr_path.open("wb")
            process = subprocess.Popen(command, shell=True, cwd=session.cwd, env=effective_env,
                stdin=subprocess.PIPE, stdout=stdout_handle, stderr=stderr_handle, preexec_fn=self._limits())
            stdout_handle.close()
            stderr_handle.close()
        except OSError as exc:
            return ToolResult(status="error", tool="execute", cwd=str(session.cwd), error=DEFAULT_REDACTOR.redact_exception(exc))
        if background:
            process_id = f"proc_{uuid.uuid4().hex}"
            fingerprint = hashlib.sha256(f"{command}\0{session_id}\0{session.cwd}".encode()).hexdigest()
            self._processes[process_id] = ManagedProcess(process_id, process, session.cwd, stdout_path=stdout_path, stderr_path=stderr_path,
                pid=process.pid, command_fingerprint=fingerprint, session_id=session_id, workspace=str(session.cwd), owner_runtime_id=self.runtime_id)
            return ToolResult(status="running", tool="execute", cwd=str(session.cwd), process_id=process_id,
                observations=["Background process started", "PTY requested" if pty else ""])
        try:
            if stdin is not None and process.stdin is not None:
                process.stdin.write(stdin.encode())
            if process.stdin is not None:
                process.stdin.close()
            process.wait(timeout=timeout or self.config.timeout_seconds)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait()
            out, _ = self._read_capture(stdout_path)
            err, _ = self._read_capture(stderr_path)
            return ToolResult(status="timeout", tool="execute", stdout=out, stderr=err, cwd=str(session.cwd), duration_ms=int((time.monotonic()-started)*1000), error="Process timed out")
        out, out_artifacts, out_meta = self._output(stdout_path, stream="stdout")
        err, err_artifacts, err_meta = self._output(stderr_path, stream="stderr")
        out_truncated = bool(out_artifacts) or stdout_path.stat().st_size >= self.config.max_output_bytes
        err_truncated = bool(err_artifacts) or stderr_path.stat().st_size >= self.config.max_output_bytes
        observations = [note for note in ("stdout truncated" if out_truncated else "", "stderr truncated" if err_truncated else "") if note]
        return ToolResult(status="success" if process.returncode == 0 else "error", tool="execute", exit_code=process.returncode,
            stdout=out, stderr=err, cwd=str(session.cwd), duration_ms=int((time.monotonic()-started)*1000), observations=observations,
            artifacts=out_artifacts + err_artifacts, artifact_metadata=out_meta + err_meta)

    def poll(self, process_id: str) -> ToolResult:
        managed = self._processes.get(process_id)
        if managed is None:
            return ToolResult(status="error", tool="execute", process_id=process_id, error="process_disappeared")
        code = managed.process.poll()
        return ToolResult(status="running" if code is None else ("success" if code == 0 else "error"), tool="execute", process_id=process_id, exit_code=code, cwd=str(managed.cwd))

    def wait(self, process_id: str, timeout: float | None = None) -> ToolResult:
        managed = self._processes[process_id]
        try:
            managed.process.wait(timeout=timeout or self.config.timeout_seconds)
        except subprocess.TimeoutExpired:
            return self.poll(process_id)
        out, _ = self._read_capture(managed.stdout_path)
        err, _ = self._read_capture(managed.stderr_path)
        return ToolResult(status="success" if managed.process.returncode == 0 else "error", tool="execute", process_id=process_id, exit_code=managed.process.returncode, stdout=out, stderr=err, cwd=str(managed.cwd))

    def terminate(self, process_id: str) -> ToolResult:
        managed = self._processes[process_id]
        if managed.process.poll() is None:
            os.killpg(managed.process.pid, signal.SIGTERM)
        return ToolResult(status="terminated", tool="execute", process_id=process_id, cwd=str(managed.cwd))

    def process_record(self, process_id: str) -> dict:
        managed = self._processes[process_id]
        return {"id": managed.id, "pid": managed.pid, "command_fingerprint": managed.command_fingerprint,
                "session_id": managed.session_id, "workspace": managed.workspace, "owner_runtime_id": managed.owner_runtime_id,
                "state": "running" if managed.process.poll() is None else "exited"}

    def recover_process(self, record: dict) -> str:
        """Reattach only when /proc environment proves Fenrys identity; otherwise mark disappeared."""
        pid = record.get("pid")
        if not isinstance(pid, int) or not Path(f"/proc/{pid}").exists():
            return "disappeared"
        try:
            environ = Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
            marker = f"FENRYS_RUNTIME_ID={record.get('owner_runtime_id', '')}".encode()
            return "running" if marker in environ else "disappeared"
        except (OSError, PermissionError):
            return "disappeared"
