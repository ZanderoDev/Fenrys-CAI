from __future__ import annotations

import os
import shutil
import signal
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class HexStrikeInstallation:
    path: Path
    python: Path
    server: Path
    mcp: Path
    pid_file: Path
    log_file: Path


class HexStrikeManager:
    """Discover and supervise an already-installed upstream HexStrike server.

    Fenrys deliberately does not clone HexStrike or install its dependencies.
    The operator image owns that installation; this class only locates it and
    starts/stops the existing server when explicitly requested.
    """

    def __init__(self, root: str | Path | None = None,
                 python: str | Path | None = None):
        configured = root or os.environ.get("HEXSTRIKE_HOME") or "/root/hexstrike-ai"
        self.path = Path(configured).expanduser()
        self.python_override = str(python or os.environ.get("HEXSTRIKE_PYTHON") or "")

    def _candidate_paths(self) -> list[Path]:
        candidates = [self.path]
        for value in (
            os.environ.get("HEXSTRIKE_HOME"),
            "/root/hexstrike-ai",
            "/opt/hexstrike-ai",
            "/usr/local/hexstrike-ai",
        ):
            if value:
                candidate = Path(value).expanduser()
                if candidate not in candidates:
                    candidates.append(candidate)
        return candidates

    def _resolve_path(self) -> Path:
        for candidate in self._candidate_paths():
            try:
                found = (candidate / "hexstrike_mcp.py").is_file()
            except OSError:
                found = False
            if found:
                return candidate
        return self.path

    def _resolve_python(self, path: Path) -> Path:
        choices: list[str | Path] = []
        if self.python_override:
            choices.append(self.python_override)
        choices.extend([
            path / ".venv" / "bin" / "python",
            path / "venv" / "bin" / "python",
            path / "hexstrike-env" / "bin" / "python",
            shutil.which("python3") or "",
            sys.executable,
        ])
        for choice in choices:
            resolved = Path(choice).expanduser() if choice else Path("")
            try:
                if resolved.is_file() and os.access(resolved, os.X_OK):
                    return resolved
            except OSError:
                continue
        return Path(self.python_override or "python3")

    @property
    def installation(self) -> HexStrikeInstallation:
        path = self._resolve_path()
        return HexStrikeInstallation(
            path,
            self._resolve_python(path),
            path / "hexstrike_server.py",
            path / "hexstrike_mcp.py",
            path / ".hexstrike.pid",
            path / "hexstrike.log",
        )

    def mcp_command(self, server_url: str) -> list[str] | None:
        install = self.installation
        try:
            available = install.mcp.is_file()
        except OSError:
            available = False
        if not available:
            return None
        return [str(install.python), str(install.mcp), "--server", server_url]

    def start(self, port: int = 8888) -> int:
        install = self.installation
        if not install.server.exists() or not install.python.exists():
            raise RuntimeError(
                "Existing HexStrike installation not found. Set HEXSTRIKE_HOME "
                "to the installed directory; Fenrys never installs HexStrike."
            )
        running = self.status()
        if running:
            return running
        import subprocess
        log = install.log_file.open("a", encoding="utf-8")
        process = subprocess.Popen(
            [str(install.python), str(install.server), "--port", str(port)],
            cwd=install.path, stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        install.pid_file.write_text(str(process.pid), encoding="utf-8")
        return process.pid

    def status(self) -> int | None:
        install = self.installation
        if not install.pid_file.exists():
            return None
        try:
            pid = int(install.pid_file.read_text(encoding="utf-8").strip())
            os.kill(pid, 0)
            return pid
        except (ValueError, OSError):
            install.pid_file.unlink(missing_ok=True)
            return None

    def stop(self) -> bool:
        pid = self.status()
        if not pid:
            return False
        os.kill(pid, signal.SIGTERM)
        self.installation.pid_file.unlink(missing_ok=True)
        return True