# FENRYS-CAI

**Terminal-first autonomous cybersecurity agent for CTF, Hack The Box & authorized security testing.**

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-%3E%3D3.11-blue)
![Node](https://img.shields.io/badge/node-%3E%3D18-green)
![Platform](https://img.shields.io/badge/platform-linux-lightgrey)

Fenrys-CAI takes a natural-language objective (e.g. *"solve this pwn challenge and get the flag"*) and works it autonomously: recon → enumerate → hypothesize → act → verify evidence → pivot when stuck → stop when done. No fixed scripts, no wizards — an adaptive reason/act loop with guardrails.

> ⚠️ **Responsible use.** Only run Fenrys-CAI against targets you are explicitly authorized to test: CTF platforms, HTB machines, your own labs, or engagements with written permission. Never use it on systems you don't own or lack authorization for.

---

## ✨ Features

| Area | What you get |
|---|---|
| 🧠 Autonomous loop | LangGraph `StateGraph`: `reason → act → specialist → verify`, with iteration/tool-call budgets |
| 🖥️ Two interfaces | Headless `fenrys` CLI + rich Ink/React TUI (animated status bar, activity tree, multi-session, state panel) |
| 🔒 Safe local runtime | Session-isolated working dirs, CPU/memory/file-size limits, bounded output, secret redaction everywhere |
| 🧪 Evidence-backed | Hypothesis lifecycle (`proposed → testing → confirmed/refuted`) + deterministic observation matchers — exit-code-0 is **not** proof |
| 🔁 Anti-loop | Attempt fingerprints + progress signatures; repeated dead-ends are blocked and recorded |
| 🕵️ 11 specialists | `recon · network · web · api · credentials · pwn · reverse · crypto · forensics · privesc · verification` |
| 🔌 MCP providers | Generic MCP client (stdio / Streamable HTTP) for external tool servers |
| 💾 Sessions | SQLite checkpoints — resume any session, continue across turns |

---

## 🚀 Quickstart

**Prerequisites:** Python ≥ 3.11, Node.js ≥ 18, Git — plus an LLM endpoint (Anthropic or any OpenAI-compatible API).

```bash
# 1. Clone & install the Python core
git clone https://github.com/ZanderoDev/Fenrys-CAI.git
cd Fenrys-CAI
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"        # dev extras; add ",mcp" for MCP support

# 2. Install the TUI
cd fenrys-tui && npm install && cd ..

# 3. Configure your model provider
export FENRYS_LLM_ENDPOINT="https://api.anthropic.com"  # or OpenAI-compatible URL
export FENRYS_LLM_API_KEY="sk-..."
export FENRYS_LLM_MODEL="claude-sonnet-4-20250514"
export FENRYS_LLM_PROTOCOL="anthropic"                  # or "openai"
```

Then either run headless:

```bash
fenrys "Enumerate this target and capture the flag" --session ctf-01 --specialist
```

…or launch the interactive TUI:

```bash
cd fenrys-tui && npm start
```

---

## ⌨️ CLI reference (`fenrys`)

```bash
fenrys "YOUR OBJECTIVE" [options]
```

| Option | Default | Description |
|---|---|---|
| `goal` | demo run | Natural-language objective for this session |
| `--session ID` | `default` | Session id (= LangGraph thread id, checkpointed) |
| `--workspace DIR` | `./.fenrys-workspaces` | Root for session workdirs & artifacts |
| `--state-dir DIR` | `./.fenrys-state` | SQLite checkpoint directory |
| `--resume` | off | Resume a session from its last checkpoint instead of starting a new turn |
| `--specialist` | off | Enable the 11-domain specialist router (recommended) |

The CLI prints the final state snapshot as JSON. For live streaming output, use the TUI.

## 🖥️ TUI commands

Inside the TUI, type a message to start a turn, or use slash commands:

| Command | Description |
|---|---|
| `/help` | Show help overlay |
| `/new [name]` | Start a new session (unique id, or your own name) |
| `/session <id>` | Switch session (continues from checkpoint) |
| `/resume [id]` | Resume a session from its last checkpoint |
| `/sessions` | List known sessions |
| `/status` | Toggle state panel (flags · hosts · services · hypotheses · dead-ends) |
| `/clear` | Clear the screen log |
| `/exit` | Quit |

Shortcuts: `↑/↓` input history · `PgUp/PgDn` scroll · `Ctrl+C` cancel turn (safe: session stays checkpointed) / quit when idle.

---

## ⚙️ Configuration

| Env var | Purpose |
|---|---|
| `FENRYS_LLM_ENDPOINT` | Base URL of the LLM API |
| `FENRYS_LLM_API_KEY` | API key (never logged, redacted in artifacts) |
| `FENRYS_LLM_MODEL` | Model name |
| `FENRYS_LLM_PROTOCOL` | `anthropic` or `openai` |
| `FENRYS_PYTHON` | (TUI) Python interpreter override for the gateway |

The TUI spawns `python -m fenrys_cai.tui.entry` from the repo root and talks to it over newline-delimited JSON-RPC on stdio. **The UI never contains agent logic** — TypeScript owns the screen, Python owns sessions, tools and model calls.

---

## 🧠 How it works

```
 goal (natural language)
   │
   ▼
 FenrysGraph (LangGraph StateGraph, SQLite-checkpointed)
   │  ┌───────────┐
   ├──▶  reason   │  PrimaryReasoner → next decision (tool / specialist /
   │  └─────┬─────┘  hypothesis / verify / stop)
   │        ▼
   │  ┌───────────┐     ┌──────────────┐
   ├──▶    act    │────▶│ ToolRegistry │──▶ local tools (read_file, write_file,
   │  └─────┬─────┘     │  + MCP tools │    execute) or external MCP servers
   │        ▼           └──────────────┘
   │  ┌──────────────┐   ┌──────────────────┐
   ├──▶ specialist   │   │ HypothesisEngine │  typed lifecycle, evidence-linked
   │  └─────┬────────┘   └──────────────────┘
   │        ▼
   │  ┌───────────┐
   └──▶  verify   │  deterministic matchers (+ LLM fallback)
      └───────────┘
```

Key design rules: verification requires evidence (no implicit success), duplicate attempts without new progress are blocked (anti-loop), large outputs spill to content-addressed artifacts instead of state, and secrets are redacted at every serialization boundary.

---

## 🗂️ Project structure

```
Fenrys-CAI/
├── fenrys_cai/            # Python core (LangGraph agent)
│   ├── cli.py             # `fenrys` entry point
│   ├── graph.py           # FenrysGraph — the autonomous loop
│   ├── state.py           # CyberState — central agent state
│   ├── runtime.py         # sandboxed terminal runtime (limits, PTY, spill)
│   ├── tools.py           # ToolRegistry + local provider
│   ├── hypotheses.py      # hypothesis/verification state machine
│   ├── verification.py    # deterministic observation matchers
│   ├── security.py        # secret redaction
│   ├── artifacts.py       # content-addressed artifact store
│   ├── llm/               # provider-neutral LLM layer (httpx, no vendor SDK)
│   ├── mcp/               # generic MCP client (stdio / HTTP)
│   ├── specialists/       # 11-domain specialist router
│   └── tui/entry.py       # `fenrys-gateway` — NDJSON gateway for the TUI
├── fenrys-tui/            # Ink + React 19 terminal UI (TypeScript)
│   └── src/               # gateway client, store, theme, components, slash cmds
├── prompts/               # system prompts (primary + 11 specialists)
├── tests/                 # pytest suite incl. deterministic end-to-end CTF harness
├── ARCHITECTURE.md        # implementation architecture notes
├── DECISIONS.md           # recorded technical decisions
└── MIGRATION_PLAN.md      # milestone status & roadmap
```

Runtime-generated dirs (`.venv/`, `node_modules/`, `.fenrys-state/`, `.fenrys-workspaces/`) are git-ignored and never committed.

---

## 🧪 Testing

```bash
source .venv/bin/activate
pytest -q                     # full Python suite (incl. deterministic E2E CTF)
cd fenrys-tui && npm run build  # TypeScript typecheck (tsc --noEmit)
```

---

## 🤝 Contributing

Issues and merge requests are welcome. Please:

1. Keep the core/TUI boundary clean (no agent logic in `fenrys-tui/`, no rendering logic in `fenrys_cai/`).
2. Add or update tests for behavior changes (`pytest`, plus `tsc --noEmit` for TUI changes).
3. Never commit secrets, checkpoints, workspaces, or `node_modules` — the `.gitignore` already excludes them, and CI secret-detection will flag leaks.
4. Note that contributions fall under the project's AGPL-3.0-or-later license.

## 📄 License

Fenrys-CAI is free software licensed under the **GNU Affero General Public License v3 or later (AGPL-3.0-or-later)** — see [LICENSE](LICENSE). If you run a modified version as a network service, the AGPL requires you to offer its source to users.

## 🙏 Acknowledgments

Built on [LangGraph](https://github.com/langchain-ai/langgraph), [Ink](https://github.com/vadimdemedes/ink) + [React](https://react.dev), [httpx](https://www.python-httpx.org), and the [Model Context Protocol](https://modelcontextprotocol.io).
