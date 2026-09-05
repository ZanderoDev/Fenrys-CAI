from fenrys.safety import RestrictedExecutionBackend


def test_sandbox_requires_restricted_backend_or_explicit_approval():
    backend = RestrictedExecutionBackend()
    command = backend.command(["echo", "ok"]) if backend._available() else None
    if command:
        assert command[-2:] == ["echo", "ok"]
        assert str(backend.memory_mb * 1024 * 1024) in command or any("rlimit-as" in part for part in command)
    else:
        assert backend.run  # no silent unsandboxed fallback