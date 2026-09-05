# Fenrys-CAI

Fenrys-CAI is a local-first, terminal-first multi-agent cybersecurity operator. It
coordinates specialist agents around a structured SQLite investigation state while
keeping model providers, tool discovery, evidence, scope, and execution budgets
explicit.

This repository is a safe, runnable foundation for CTF, lab, security research,
and authorized pentest workflows. It does not bypass authorization or treat tool
output as instructions.

## Quick start

```bash
./scripts/install.sh
# or, in an existing uv environment:
uv sync --extra dev
uv run fenrys setup
uv run fenrys
```

The supported deployment runs as `root`, so configuration is stored under
`/root/.config/fenrys-cai/` and large raw tool output under
`/root/.local/share/fenrys-cai/raw/`. A project-local `.fenrys/` directory can
override user settings.

Useful commands:

```text
fenrys doctor
fenrys model list
fenrys model set web openai_compatible llama3.1
fenrys model test openai
fenrys tools status
fenrys agents status
fenrys session new --target challenge.local --mode CTF
fenrys session run <session-id> recon "enumerate the target"
fenrys session investigate <session-id> "map the web attack surface"
fenrys session resume <session-id>
fenrys session export <session-id> --format html
fenrys report --format markdown
```

Fenrys does **not** clone HexStrike, create a HexStrike virtualenv, or install
HexStrike dependencies. It consumes the existing root-owned installation:
`/root/hexstrike-ai` by default. Set `HEXSTRIKE_HOME` and optionally
`HEXSTRIKE_PYTHON` when the existing installation lives elsewhere or uses a
dedicated Python environment. `fenrys hexstrike start` only starts the existing
`hexstrike_server.py`; it never installs anything. API keys are never written to
config or printed.

## Design notes

- Provider adapters implement one async interface; OpenAI-compatible endpoints
  cover local models and proxies without a new adapter per vendor.
- Tool registry tracks MCP registration, backend registration, and binary
  detection independently.
- SQLite is the source of truth for sessions, tasks, findings, and evidence.
- Raw output is written to disk and only a bounded summary is suitable for model
  context.
- Scope checks, stop budgets, untrusted tool-output wrapping, and flag detection
  are deterministic code paths rather than LLM responsibilities.
- `fenrys session run` exercises the connected agent loop: provider completion,
  per-agent tool-profile filtering, scope/budget checks, HexStrike invocation,
  evidence normalization, and SQLite bookkeeping.
- The HexStrike adapter starts the already-installed upstream `hexstrike_mcp.py`
  with its existing Python environment as an MCP stdio subprocess, performs
  `initialize` → `tools/list` → `tools/call`, and uses the Flask API only as the
  separately tracked backend-health fallback.
- `fenrys session investigate` uses deterministic planning to queue Recon first
  and then delegate to a specialist agent, persisting each task and report in
  SQLite.

## Changelog

### 0.0.1-beta
- Fixed `BudgetController` so `max_total_tool_calls_per_session` is tracked
  per session (persists across every task) instead of resetting on each
  `run_task()` call. Per-task counters (`max_tool_calls_per_task`,
  `max_agent_turns_per_task`) now reset via `start_task()` at the start of
  each task.
- Removed the unused `budget` field from `Orchestrator` (planning never
  enforced it; enforcement lives in `InvestigationRuntime`).
- Fixed the setup wizard rendering as a blank screen: `SetupScreen` is a
  `Screen`, not a child widget, so yielding it from `compose()` gave it a
  0x0 layout and only the background was visible. It is now pushed onto the
  screen stack from `on_mount()` instead.
- Added `.gitignore` for local config, virtualenvs, and runtime data.

## Known limitations (0.0.1-Beta)

- Tested by static review and the bundled unit tests only (`uv run pytest`);
  it has not yet been run against a live HexStrike backend or a real target
  end-to-end. Treat findings and reports as needing manual verification.
- `RestrictedExecutionBackend` requires `bwrap` or `firejail` on the host; if
  neither is available it refuses to run untrusted artifacts rather than
  falling back to unsandboxed execution.
- Requires Python 3.13 exactly (see `pyproject.toml` / `scripts/install.sh`).
