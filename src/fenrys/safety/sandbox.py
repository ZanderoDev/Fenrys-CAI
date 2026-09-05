from __future__ import annotations

import asyncio
import os
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class SandboxResult:
    ok: bool
    stdout: str
    stderr: str
    returncode: int | None
    error: str | None = None


class RestrictedExecutionBackend:
    """Run untrusted Crypto/Misc artifacts with network disabled by default."""

    def __init__(self, timeout_seconds: int = 30, memory_mb: int = 512, allow_network: bool = False):
        self.timeout_seconds = timeout_seconds
        self.memory_mb = memory_mb
        self.allow_network = allow_network

    def _available(self) -> bool:
        return bool(shutil.which("bwrap") or shutil.which("firejail"))

    def command(self, argv: list[str], cwd: str | Path | None = None) -> list[str]:
        workdir = str(Path(cwd).resolve()) if cwd else os.getcwd()
        if shutil.which("bwrap"):
            command = ["bwrap", "--die-with-parent", "--ro-bind", "/", "/", "--proc", "/proc",
                       "--dev", "/dev", "--chdir", workdir]
            if not self.allow_network:
                command.append("--unshare-net")
            if not shutil.which("prlimit"):
                raise RuntimeError("prlimit is required for the bwrap memory limit")
            return ["prlimit", "--as", str(self.memory_mb * 1024 * 1024), "--"] + command + argv
        if shutil.which("firejail"):
            command = ["firejail", "--quiet", "--private", f"--rlimit-as={self.memory_mb}M"]
            if not self.allow_network:
                command.append("--net=none")
            return command + argv
        raise RuntimeError("no restricted sandbox available; install bubblewrap or firejail")

    async def run(self, argv: list[str], cwd: str | Path | None = None,
                  approved_unsandboxed: bool = False) -> SandboxResult:
        try:
            command = self.command(argv, cwd)
        except RuntimeError as exc:
            if not approved_unsandboxed:
                return SandboxResult(False, "", "", None, str(exc))
            command = argv
        try:
            process = await asyncio.create_subprocess_exec(
                *command, cwd=str(cwd) if cwd else None,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), self.timeout_seconds)
            return SandboxResult(process.returncode == 0, stdout.decode(errors="replace"),
                                 stderr.decode(errors="replace"), process.returncode)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return SandboxResult(False, "", "", None, "sandbox timeout")
        except Exception as exc:
            return SandboxResult(False, "", "", None, type(exc).__name__ + ": " + str(exc)[:160])
