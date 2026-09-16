# Migration Plan

No Hermes or NyxStrike source is part of the Fenrys package. Reference archives remain under `references/`.

Completed milestones: local terminal runtime and process recovery identity, secure artifacts/redaction/archive boundaries, typed target state, SQLite LangGraph checkpoints, unified LLM reasoning, generic MCP and live NyxStrike validation, specialists, typed hypothesis/verification, autonomous anti-loop controls, and a deterministic multi-layer local CTF E2E that validates tools, specialist participation, hypothesis-linked attempts, duplicate blocking/reconsideration, artifact spill, interruption/resume, evidence-backed flag confirmation, and final completion.

Next milestones:

1. Persist active process records in a dedicated runtime database so recovery inspection can be initiated automatically on CLI startup.
2. Add tar archive support and artifact retention/garbage-collection policies.
3. Improve real-provider prompt/tool schemas so autonomous models consistently use `read_file` arguments and create hypothesis/verification decisions before exhausting tool limits.
4. Add constrained structured-output provider mode or repair/retry of malformed model JSON only after a reviewed safety design; current bounded retry deliberately excludes malformed output.
5. Continue real-LLM CTF reliability evaluation. The custom OpenAI-compatible LapakVIP validation passes harmless primary and specialist structured-tool paths, while full multi-step real CTF completion remains a separate reliability target.
