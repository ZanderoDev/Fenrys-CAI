from pathlib import Path
import time

from fenrys_cai.config import RuntimeConfig
from fenrys_cai.runtime import LocalTerminalRuntime


def runtime(tmp_path: Path) -> LocalTerminalRuntime:
    return LocalTerminalRuntime(RuntimeConfig(tmp_path / "workspace", timeout_seconds=2, max_output_bytes=1024))


def test_foreground_persistent_session_cwd_and_isolation(tmp_path: Path) -> None:
    terminal = runtime(tmp_path)
    first = terminal.execute("mkdir child", "one")
    assert first.status == "success"
    terminal.session("one").cwd = terminal.session("one").cwd / "child"
    assert terminal.execute("pwd", "one").stdout.rstrip().endswith("child")
    assert terminal.execute("pwd", "two").stdout.rstrip() != terminal.execute("pwd", "one").stdout.rstrip()


def test_environment_timeout_output_and_background_lifecycle(tmp_path: Path) -> None:
    terminal = runtime(tmp_path)
    assert terminal.execute("printf $FENRYS_VALUE", "one", env={"FENRYS_VALUE": "ok"}).stdout == "ok"
    bounded = LocalTerminalRuntime(RuntimeConfig(tmp_path / "bounded", timeout_seconds=2, max_output_bytes=12))
    assert "stdout truncated" in bounded.execute("yes", "one").observations
    assert terminal.execute("sleep 5", "one", timeout=0.1).status == "timeout"
    started = terminal.execute("printf background", "one", background=True)
    assert terminal.poll(started.process_id).status in {"running", "success"}
    assert terminal.wait(started.process_id).stdout == "background"


def test_pty_requires_background(tmp_path: Path) -> None:
    assert runtime(tmp_path).execute("true", "one", pty=True).status == "error"
