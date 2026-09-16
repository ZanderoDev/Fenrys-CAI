# Fenrys-CAI Architecture

Fenrys-CAI is terminal-first and intended only for authorized CTF, HTB, and lab work.

`fenrys_cai.cli` constructs the local runtime, provider-neutral registry, SQLite LangGraph checkpointer, and `FenrysGraph`. `FenrysGraph` is a compiled LangGraph `StateGraph` with `reason -> act -> reason` edges. A `Reasoner` is invoked by the graph's `reason` node on every loop iteration; the initial CLI uses a harmless offline demonstration reasoner. `JSONHTTPReasoner` is a provider-neutral adapter configured with `FENRYS_LLM_ENDPOINT` and optionally `FENRYS_LLM_API_KEY`.

The public local surface is `read_file`, `write_file`, and `execute`. `LocalTerminalRuntime` owns subprocesses, session CWD/environment, process IDs, timeouts, output bounds, resource limits, and termination. Graph code never starts subprocesses.

`ToolRegistry` normalizes provider discovery and invocation. `fenrys_cai.mcp.MCPProvider` is an optional generic `ToolProvider`; servers are configured externally through `MCPServerConfig` and never identified by product name. The provider owns MCP lifecycle: it starts a stdio subprocess or opens a Streamable HTTP session, initializes one reusable `ClientSession`, discovers tools, invokes calls, detects failures, and closes transport resources. LangGraph and the LLM layer never import MCP protocol modules.

MCP discovery converts each remote tool into a normal `ToolSpec` with provider provenance, MCP execution mode, schema-derived capabilities, and the original JSON input schema. Invocation converts MCP text/structured content into a bounded `ToolResult`; MCP errors are normalized to provider-visible states such as `timeout`, `tool_not_found`, `invocation_failure`, `startup_failure`, `malformed_response`, or `transport_failure`. Parent-process environment values that look like credentials are not forwarded to stdio servers unless explicitly configured.

`CyberState` retains bounded evidence metadata and artifact references, while terminal and MCP output stay in normalized results.

LangGraph's `SqliteSaver` is the authoritative persistent checkpoint store for the CLI. `CyberState` is converted to a `TypedDict` graph state whose append-only evidence, attempts, artifacts, and history fields use LangGraph reducers.

## Terminal Session Continuity And Streaming

The terminal TUI remains a Node/Ink process connected to `fenrys_cai.tui.entry` through newline-delimited JSON on stdio; it has no HTTP or browser surface. `prompt.submit` continues a checkpointed LangGraph thread rather than invoking a fresh exported `CyberState` on every message.

`FenrysGraph.continue_session` and `stream_turn` use the same input builder. A first turn receives a complete `CyberState`; later turns submit only a delta containing a tagged `user_directive:` history entry and reset per-turn runtime bounds (`iteration_count`, `tool_call_count`, `started_at`, provider retry state, and specialist depth). Omitted graph keys retain checkpointed values, so objective, phase, evidence, attempts, hypotheses, verifications, dead ends, typed targets, and artifacts remain cumulative. The full retained attempt history continues to enforce duplicate-action prevention across turns.

`stream_turn` consumes LangGraph `stream_mode="updates"` and exposes one structured update per visited graph node. The gateway emits reasoning, tool, specialist, and verification events immediately, then emits the unchanged closing `turn.complete` state payload. Ink appends those events as they arrive and derives phase/evidence/hypothesis status from the final state without another IPC request.

## Specialist Reasoning

Specialists are Fenrys-native reasoning components, not independent runtimes. They share the same `ToolRegistry`, terminal runtime, and `CyberState` as the primary graph. The architecture is:

```
                 Fenrys Runtime
                      |
                 CyberState
                      |
          +-----------+-----------+
          |   Shared ToolRegistry |
          +-----------+-----------+
                      |
              Specialist Reasoning
                      |
       +------+------+------+------+
      web   recon   crypto   pwn   ...
```

The graph includes an optional `specialist` node that is only entered when the main `reason` node returns a `__specialist__` decision. The specialist node:

1. Builds a bounded `SpecialistRequest` from `CyberState` (max 5 evidence items, 10 history entries — raw terminal output is never included).
2. Routes to one of 11 domains via `SpecialistRouter` using signal-based scoring on objective, phase, findings, hypotheses, evidence, and tool capabilities — never a hardcoded tool catalog.
3. Invokes a `PromptedSpecialist` that reads a Fenrys-native prompt from `prompts/specialists/<domain>.md` and calls an injected decision builder.
4. Returns a `SpecialistDecision` with kind (`tool`, `delegate`, `continue`, `stop`), rationale, confidence, and verification requirements.
5. If the decision is a tool call, it is converted to a normal `Decision` and executed through the existing `act` node.
6. If the decision is a delegation, the graph routes to another specialist with depth tracking; delegation beyond `max_depth` terminates cleanly.

Specialists never own terminals, tool registries, or checkpoints. The 11 domains are: `recon`, `network`, `web`, `api`, `credentials`, `pwn`, `reverse`, `crypto`, `forensics`, `privesc`, `verification`.

### Unified LLM Architecture

Primary reasoning and specialist reasoning share a single provider-neutral `LLMProvider` in `fenrys_cai/llm/provider.py`. There is no separate HTTP implementation for primary vs specialist reasoning.

```
Primary REASON ─┐
                ├── LLMProvider (httpx, Anthropic/OpenAI-compatible)
Specialists ────┘
```

`PrimaryReasoner` in `fenrys_cai/llm/primary.py` builds bounded context from `CyberState`, calls `LLMProvider.complete_json()`, and validates the response into `PrimaryDecision` with kinds `tool`, `specialist`, `continue`, `stop`. Validation rejects unknown tools, invalid specialist domains, malformed arguments, and missing decisions. The graph's `reason` node converts `PrimaryDecision` into graph routing: `tool → act`, `specialist → specialist node`, `stop → END`, `continue → END` (avoids infinite loop).

`LLMSpecialistDecisionBuilder` in `fenrys_cai/specialists/llm_decision.py` uses the same `LLMProvider` for specialist decisions. Both paths share configuration from `FENRYS_LLM_ENDPOINT`, `FENRYS_LLM_API_KEY`, `FENRYS_LLM_MODEL`, with fallback to `ANTHROPIC_BASE_URL`/`OPENAI_API_KEY`.

### LLM-Powered Specialist Reasoning

Specialist decisions are driven by `LLMSpecialistDecisionBuilder`, which uses the same provider-neutral HTTP LLM interface as the primary reasoning loop. The flow is:

```
SpecialistRequest
    → LLMSpecialistDecisionBuilder
    → provider endpoint (Anthropic/OpenAI-compatible)
    → strict JSON validation
    → SpecialistDecision (continue|tool|delegate|stop)
    → LangGraph act/specialist node
```

The builder constructs bounded `ChatRequest`-compatible messages containing the specialist prompt, bounded context, and a compact tool capability summary (max 15 tools with schema summaries). The LLM must return only valid JSON matching the decision schema. Validation rejects malformed JSON, missing decisions, invalid types, unknown tools, invalid domains, and non-dict arguments — malformed output never reaches `ToolRegistry`.

Configuration uses `FENRYS_SPECIALIST_LLM_ENDPOINT`, `FENRYS_SPECIALIST_LLM_API_KEY`, and `FENRYS_SPECIALIST_LLM_MODEL`, falling back to the primary LLM environment variables. No provider SDK is imported; the builder uses plain `httpx` with format detection for Anthropic vs OpenAI response shapes.

## NyxStrike as External MCP Server

NyxStrike `1.9.0` is validated as an external MCP server through the generic `MCPProvider`. Fenrys core contains no NyxStrike imports, tool lists, or provider-specific branches. The relationship is:

```
Fenrys MCPProvider
      ↓ stdio
NyxStrike MCP bridge (nyxstrike_mcp.py)
      ↓ HTTP
NyxStrike API server (port 8888)
```

The bridge exposes `classify_task` and `run_tool` gateway tools. Fenrys discovers these dynamically, normalizes them into `ToolSpec`, registers them with `ToolRegistry`, and invokes them like any other tool. The graph sees only `ToolSpec`/`ToolResult` with MCP provenance.

## Hypothesis And Verification

Fenrys separates observations from claims through a state-machine-controlled lifecycle:

```
Observation -> Hypothesis -> Evidence references -> Verification -> State transition
```

`HypothesisEngine` is the only supported transition boundary. Hypotheses move through `proposed`, `testing`, `supported`, `confirmed`, `refuted`, `inconclusive`, and `superseded` according to an explicit transition table. Historical hypotheses are retained; supersession does not delete old reasoning. Hypotheses contain bounded evidence IDs rather than duplicated raw output.

Verification records move through `pending`, `in_progress`, then `confirmed`, `failed`, or `inconclusive`. A confirmation requires supporting evidence references. Exit code zero, HTTP 200, `ToolResult.status == success`, or model confidence never changes a hypothesis status automatically.

The primary LLM can emit validated `hypothesis` and `verify` decisions. The graph conditionally routes `verify` to a verification node which creates an in-progress record and returns to reasoning. It does not infer a conclusion before expected and actual observations are compared. Specialists can return hypothesis statements; graph code converts these through `HypothesisEngine` instead of allowing direct state mutation. Active hypotheses and pending verifications are bounded in primary and specialist context.

## Autonomous Loop And Anti-Loop

The LangGraph loop is now genuinely autonomous and bounded:

```
REASON
  |-- tool -> ACT -> REASON
  |-- specialist -> SPECIALIST -> REASON
  |-- hypothesis -> state update -> REASON
  |-- verify -> VERIFY -> REASON
  |-- continue -> REASON
  `-- stop/limit/dead-end -> END
```

`LoopConfig` centralizes `max_iterations`, `max_tool_calls`, `max_repeated_attempts`, and `max_runtime_seconds`. Counters and start time are checkpointed. The graph checks limits before each reasoning/tool action.

Attempt identity hashes normalized objective, target, tool, sorted parameters, normalized strategy, and optional hypothesis ID. It is distinct from hypothesis identity. A retry is accepted when parameters, target, strategy, hypothesis, or deterministic progress token changes. A repeated identity without state progress is blocked and recorded as a persistent `DeadEnd` containing blocked attempts, evidence references, related hypotheses, and suggested alternatives.

Progress signatures are deterministic hashes of semantic evidence descriptors, artifacts, findings, hypothesis transitions, and verification transitions. A successful command with no new semantic state is not itself progress.

## Verification Matchers

`verification.match_observation` supports explicit `exact_text`, `substring`, `regex`, `json_field_exists`, `json_field_equals`, and numeric comparison matchers. Generic `success`, HTTP 200, and exit code zero have no implicit semantics. A matcher conclusion updates `Verification` and then passes through `HypothesisEngine.conclude`; confirmation still requires a supporting evidence ID and a valid state transition.

## Runtime Hardening

`LocalArtifactStore` securely stores oversized terminal/tool output below a dedicated artifact root. State receives an `Artifact` reference containing ID, kind, safe basename, size, content type, SHA-256, source, tool, timestamp, provenance, and retention metadata rather than unlimited content. Reads are range-bounded and artifact IDs cannot encode paths. Runtime and registry spill thresholds and maximum artifact sizes are configurable.

`Redactor` is the centralized persistence/result boundary for secrets. It redacts credential-shaped mapping keys, bearer tokens, password/token assignments, environments, exceptions, `ToolResult.to_dict()`, and `CyberState.export()`. Stdio MCP child environments exclude secret-shaped parent variables unless explicitly configured.

Background process records include process record ID, PID, command fingerprint, session/workspace, start state, and a runtime owner identity injected into the child environment. Resume/recovery considers a process reattachable only when `/proc/<pid>/environ` proves the same Fenrys runtime identity. Missing, inaccessible, or reused PIDs become `disappeared`; Fenrys does not signal them.

`CyberState` now contains typed `Host`, `Service`, and `Endpoint` collections plus technologies. Upserts use stable semantic identities (address; host/port/protocol; method/URL), merge evidence references, and avoid duplicate entities. These collections participate in deterministic progress signatures and checkpoint serialization.

Deterministic verification remains preferred. `LLMVerifier` is a bounded fallback when deterministic matching returns unknown. It uses the existing `LLMProvider`, validates `confirmed|refuted|inconclusive`, rejects nonexistent evidence references, and returns a decision object; only `HypothesisEngine` may perform lifecycle transitions.

File-system boundaries resolve paths before access, reject workspace and artifact-root escapes (including symlinks), and extract ZIP archives only after validating traversal, absolute paths, symlinks, total size, and file count.

## End-To-End Execution

The deterministic local CTF harness validates the integrated path:

```
Natural-language objective
  -> PrimaryReasoner
  -> LangGraph REASON
  -> ToolRegistry / LocalProvider
  -> bounded observations + artifact spill
  -> adaptive specialist
  -> typed hypothesis
  -> hypothesis-linked tool actions
  -> anti-loop block + reconsideration
  -> evidence-backed deterministic verification
  -> confirmed hypothesis and synthetic flag
  -> STOP
```

The harness uses a disposable session workspace containing a manifest, a large decoy, an encoded candidate, and an independent SHA-256. It intentionally interrupts after the first action and resumes through a new graph instance backed by the same SQLite checkpointer. All later decisions use restored attempts, evidence, progress counters, hypotheses, and dead ends.

Anti-loop normally terminates on a duplicate. For recoverable engagements, `max_anti_loop_reconsiderations` permits a bounded number of blocked duplicates to return to `REASON`; the tool is still not executed and a `DeadEnd` is always retained. The next decision must use a materially different strategy.

## LLM Reliability

Core local tools expose valid Fenrys JSON Schema contracts rather than informal type strings. `read_file` and `write_file` require workspace-relative `path` and `session_id`; `execute` documents only its implemented command, process-management, timeout, PTY, stdin, and environment fields. The primary prompt explicitly requires schema-compliant workspace paths, hypothesis/verification for non-trivial claims, and evidence-backed CTF completion.

Transient `LLMError` categories (`timeout`, `connection_failure`, `provider_error`, `rate_limited`) use a bounded `LoopConfig.max_provider_retries` retry path. The checkpointed state contains only retry count and error category, never credentials. Authentication, malformed response, invalid schema, and invalid decision errors are terminal and are not retried.

Custom OpenAI-compatible providers use the existing `LLMProvider` with no provider-specific client. Configure `FENRYS_LLM_ENDPOINT`, `FENRYS_LLM_MODEL`, `FENRYS_LLM_API_KEY`, and `FENRYS_LLM_PROTOCOL=openai`. The provider appends `/chat/completions` exactly once, normalizes the OpenAI `choices[0].message.content` response, and is shared by primary reasoning and specialists.
