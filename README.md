# Fenrys-CAI

Fenrys-CAI is a local-first, terminal-first multi-agent cybersecurity operator. It
coordinates specialist agents around a structured SQLite investigation state while
keeping model providers, tool discovery, evidence, scope, and execution budgets
explicit.

This repository is a safe, runnable foundation for CTF, lab, security research,
and authorized pentest workflows. It does not bypass authorization or treat tool
output as instructions.

## Quick start

Run from the existing `~/fenrys-cai` project; the normal operator path does not open the setup wizard once configuration exists.

```bash
cd ~/fenrys-cai
uv sync
export OPENROUTER_API_KEY="sk-or-..."
uv run fenrys hexstrike start
# in another terminal:
cd ~/fenrys-cai
export OPENROUTER_API_KEY="sk-or-..."
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

Custom OpenAI-compatible providers (OpenRouter, DeepSeek, vLLM, LM Studio,
LiteLLM, and similar endpoints) can be added directly in the setup wizard at
**Provider Setup → Save Custom Provider**. The wizard writes only the endpoint
and the API-key environment variable name; the secret itself must already be
available in the root process environment. The equivalent YAML is:

```yaml
providers:
  my_provider:
    type: custom
    base_url: https://api.example.com/v1
    api_key_env: MY_PROVIDER_API_KEY
```

OpenRouter is the default provider for new installations. Set
`OPENROUTER_API_KEY` in the process environment; the default model for every
agent tier is `minimax/minimax-m3:free`. It can be replaced per agent or tier
in the wizard or directly in `agents.yaml`.

Fenrys does **not** clone HexStrike, create a HexStrike virtualenv, or install
HexStrike dependencies. It consumes the existing root-owned installation:
`/root/hexstrike-ai` by default. Set `HEXSTRIKE_HOME` and optionally
`HEXSTRIKE_PYTHON` when the existing installation lives elsewhere or uses a
dedicated Python environment. `fenrys hexstrike start` only starts the existing
`hexstrike_server.py`; it never installs anything. API keys are never written to
config or printed.

## Operator mode

The default `fenrys` UI is intentionally modeled after coding-agent terminals: there is one Fenrys conversation, not a wizard-driven agent selector. Type requests directly in the prompt. Fenrys Core can call the native HexStrike MCP backend through a compact `hexstrike_tool` bridge or delegate a focused subtask to a specialist. Specialist results return to the same conversation so the core can continue reasoning.

Useful in-session commands are `/new`, `/status`, `/agents`, `/doctor`, `/clear`, `/setup`, and `/quit`. The graphical setup wizard remains available through `/setup` or `fenrys setup`, but it is not part of the normal execution path.

HexStrike exposes a large MCP tool catalog, so Fenrys avoids sending the entire catalog as individual provider function definitions. This keeps the orchestrator comfortably under provider tool-array limits while still discovering tools dynamically from the installed HexStrike MCP server. This is particularly important because the upstream project has historically exposed 150+ tools and users have reported provider limits around 128 tools. citeturn296072search2turn296072search6

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

### 0.9.0-beta
- New Hermes-style scrollback REPL (`fenrys`): prompt_toolkit + Rich, copyable
  output (select + Ctrl+Shift+C), Enter submit, Alt+Enter/Ctrl+J newline,
  bracketed paste, slash commands, per-turn token/elapsed/tps status bar.
- New sequential setup wizard (`fenrys setup`): plain prompts, writes config
  files plus `~/.config/fenrys-cai/.env` for API keys. Legacy Textual TUI kept
  behind `fenrys --textual`.
- Startup panel: ASCII logo + pet art, tools/engine/model/session summary.
- Auto flag detection → clipboard + loot file; `/copy`, `/save`, `/resume`.
- Efficiency pass: direct answers for simple prompts, single direct tool for
  simple actions, delegation demoted to expensive last resort, trimmed tool
  surface (40 → 12), minimal specialist prompts.
- Streaming-callback hardening: sync/None `on_token`/`on_tool_*`/`on_usage`
  can no longer crash the agent loop.

### Unreleased
- Fixed: after the setup wizard's "Launch Dashboard" step, the CLI now opens
  the dashboard instead of exiting the process
  (`fenrys setup` / `fenrys` with no prior config).
- Default model for every agent tier is now `minimax/minimax-m3:free` via
  OpenRouter (was `openrouter/auto`).
- Removed the top-level `*.example.yaml` and `.env.example` files — they were
  documentation only and never read by the app; real defaults live in
  `fenrys.config.manager.DEFAULT_*`. Run `fenrys setup` to write real config.

## Agentic operator behavior

Fenrys opens as one conversation, similar to a coding-agent terminal. Natural-language requests go to the Fenrys Core. The core can call real HexStrike MCP tools directly, or delegate a focused task to a specialist agent and then continue from the specialist report. There is no mandatory recon→web→... sequence.

The default OpenRouter model is `minimax/minimax-m3:free`, which currently supports tool calling on OpenRouter's free endpoint. If you select a different model, verify that the model supports tools.
