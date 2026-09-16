# Fenrys-CAI — Master Build Prompt

You are the lead architect and principal implementation engineer for a new project called **Fenrys-CAI**.

This is a fresh Claude Code session. Do not assume any prior conversation exists. Everything needed to understand the project is specified below.

---

# 1. PROJECT

I want to build **Fenrys-CAI**, an autonomous cybersecurity AI agent focused on:

- Hack The Box (HTB)
- CTF competitions
- offline CTF challenges
- authorized security testing environments

Fenrys-CAI should feel like a modern autonomous coding/terminal agent, but its reasoning, tools, and workflows are specialized for cybersecurity.

The user should be able to provide a high-level natural-language objective such as:

> Analyze and solve this HTB target.

or:

> Analyze this pwn challenge and obtain the flag.

The agent should independently:

1. understand the objective;
2. inspect current state;
3. reason about possible approaches;
4. select an appropriate specialist or tool;
5. execute actions;
6. inspect the results;
7. update its understanding of the target;
8. verify important findings;
9. pivot or retry when appropriate;
10. continue until the objective is achieved or the agent is genuinely stuck.

This must be an adaptive agent, not a fixed wizard.

---

# 2. REFERENCE REPOSITORIES

The working directory contains two reference archives:

```text
~/Dokumen/claude/hermes-agent-main.zip
~/Dokumen/claude/nyxstrike-master.zip
```

They are **reference implementations**, not templates to copy wholesale.

You must inspect the actual source code before making architectural or implementation decisions.

## Hermes reference

Use Hermes primarily as a reference for mature execution/runtime behavior, especially:

- terminal execution
- foreground execution
- background execution
- process lifecycle
- PTY
- persistent session state
- persistent CWD
- environment handling
- terminal result normalization
- execution lifecycle
- relevant tool registry patterns
- relevant delegation patterns

Do NOT reproduce the entire Hermes application.

The majority of Hermes is outside the scope of Fenrys-CAI.

Do not bring unnecessary Hermes functionality such as:

- unrelated messaging integrations
- bots
- cron systems
- desktop integrations
- generic productivity systems
- unrelated coding-agent integrations
- unrelated LLM provider wrappers
- unrelated enterprise adapters
- unrelated frontend/UI systems
- unrelated skills
- unrelated evaluation infrastructure

Hermes is a **runtime reference**, not Fenrys's product architecture.

Prefer Fenrys-native implementations over copying Hermes module-by-module.

## NyxStrike reference

Use NyxStrike primarily as a reference for cybersecurity domain knowledge and MCP/tool integration concepts.

Useful areas include:

- HTB/CTF specialist prompts
- cybersecurity domain reasoning
- attack-state concepts
- semantic phases
- anti-loop rules
- state/memory schema concepts
- tool prioritization concepts
- evidence/artifact concepts
- MCP integration
- tool metadata concepts

IMPORTANT:

Do not assume NyxStrike's apparent autonomous CTF runtime is a production autonomous agent.

Inspect the actual source.

If orchestration contains placeholders or simulated execution, do not copy it into Fenrys.

Do not make Fenrys dependent on NyxStrike's Flask/dashboard architecture.

Do not copy NyxStrike's hardcoded security-tool catalog into Fenrys's orchestration layer.

NyxStrike should be usable as an **optional MCP/tool provider**.

---

# 3. CORE ARCHITECTURAL DECISION

The final Fenrys architecture is:

```text
                        USER
                         |
                         v
                 +---------------+
                 |  Fenrys CLI   |
                 +-------+-------+
                         |
                         v
               +---------------------+
               |    LangGraph        |
               |  Control Plane      |
               |                     |
               | state               |
               | checkpointing       |
               | routing             |
               | branching           |
               | parallelism         |
               | recovery            |
               | delegation          |
               +----------+----------+
                          |
                          v
               +---------------------+
               | Agent Reasoning     |
               |       Layer         |
               |                     |
               | LLM reasoning       |
               | next-action choice  |
               | specialist routing  |
               | hypothesis updates  |
               +----------+----------+
                          |
                          v
               +---------------------+
               |    Tool Registry    |
               +----------+----------+
                          |
               +----------+----------+
               |                     |
               v                     v
       +---------------+     +----------------+
       | Local Runtime |     | MCP Providers  |
       +-------+-------+     +-------+--------+
               |                     |
               |                     +--> NyxStrike
               |                     +--> Future MCP
               |
               v
       +-----------------------+
       | Fenrys Terminal       |
       | Runtime               |
       |                       |
       | shell                 |
       | process               |
       | PTY                   |
       | CWD                   |
       | environment           |
       | timeout               |
       | output                |
       +-----------+-----------+
                   |
                   v
              OBSERVATION
                   |
                   v
             VERIFICATION
                   |
                   v
               CYBER STATE
                   |
                   +-------> next decision
```

This separation is mandatory.

---

# 4. LANGGRAPH ROLE

LangGraph is the **orchestration/control plane**.

IMPLEMENTATION NOTE ON THE SECTION 3 DIAGRAM:

The boxes in the Section 3 diagram represent conceptual layers, not separate runtime processes called once in strict top-to-bottom sequence. In practice, the LLM reasoning call must be implemented as a node (or a small set of nodes) *inside* the LangGraph graph itself, and the graph loops back into that node repeatedly:

```text
OBSERVE -> REASON (LLM node) -> ACT -> OBSERVE -> REASON (LLM node) -> ...
```

Do NOT implement "LangGraph" and "Agent Reasoning Layer" as two separate systems that hand off to each other once per turn. LangGraph owns the loop, its state, and its edges; the LLM reasoning step is simply one of the nodes LangGraph invokes and re-invokes. If this distinction is unclear during implementation, resolve it before writing the first vertical slice, since it affects how checkpointing and recovery work.

Use LangGraph for:

- state
- reducers
- checkpointing
- routing
- branching
- loops
- parallel execution
- recovery
- delegation
- lifecycle coordination

Do NOT turn LangGraph into a rigid attack script.

Do NOT create a permanently fixed graph such as:

```text
RECON -> ENUM -> EXPLOIT -> PRIVESC -> FLAG
```

where the graph forces the agent through these stages in one direction.

CTF and HTB reasoning is non-linear.

The agent must be able to do things such as:

```text
RECON
  -> ENUM
  -> WEB
  -> failed hypothesis
  -> RECON again
  -> different enumeration
  -> BINARY
  -> return to WEB
  -> new exploit hypothesis
  -> FOOTHOLD
```

Semantic phases may exist in state:

```text
RECON
ENUM
FOOTHOLD
PRIVESC
FLAG
```

but phases are **context and semantic state**, not hard barriers.

The graph should provide the execution structure while the LLM decides the next meaningful action.

---

# 5. LLM REASONING ROLE

The LLM is responsible for adaptive reasoning.

The LLM should determine:

- what to investigate;
- whether more reconnaissance is needed;
- which specialist is useful;
- which available tool is relevant;
- which hypothesis is worth testing;
- whether to retry;
- whether to pivot;
- whether an observation is meaningful;
- whether a result should be verified;
- when the objective is sufficiently satisfied.

Do not encode specific attack chains in Python.

Do not write logic such as:

```python
if web:
    run_ffuf()
elif smb:
    run_enum4linux()
```

Security-tool selection must come through capabilities and runtime-discovered tools.

---

# 6. LOCAL EXECUTION IS PRIMARY

Fenrys should run naturally on a Linux host and interact directly with environments such as an HTB VPN.

Local execution is the primary execution path.

MCP is an extensibility/provider path.

Do NOT force every shell command through MCP.

Architecture:

```text
Fenrys
 |
 +--> Local Terminal Runtime
 |
 +--> MCP Provider
        |
        +--> NyxStrike
        +--> other MCP servers
```

NyxStrike must not be required for Fenrys to boot.

Fenrys must still operate using local execution and built-in primitives when no MCP provider is configured.

---

# 7. PUBLIC TOOL SURFACE

Keep the public Fenrys tool surface intentionally small.

Core tools:

```text
read_file
write_file
execute
```

Do not create a huge collection of overlapping tools.

Do not expose separate versions of:

- shell_run
- command_run
- terminal_exec
- execute_shell
- search_files
- list_files
- create_file
- append_file
- edit_file
- patch_file
- copy_file

unless a genuine architectural reason is discovered later.

The goal is a small, coherent interface.

---

# 8. EXECUTE TOOL

`execute` is the primary runtime primitive.

It should support, directly or through a clean internal process API:

- foreground execution
- background execution
- PTY
- process/session IDs
- stdin
- stdout
- stderr
- current working directory
- environment
- timeout
- process polling
- waiting
- termination
- output capture
- artifact capture
- bounded model-facing output

Conceptually:

```text
execute(command)
execute(command, background=true)
execute(command, pty=true, background=true)
```

Long-running processes must not block the entire agent.

Interactive commands must be able to use PTY when supported.

---

# 9. TERMINAL RUNTIME

Create a Fenrys-native terminal runtime inspired by the useful Hermes behavior.

The terminal runtime must be separate from agent reasoning.

The runtime owns:

- process execution
- process lifecycle
- PTY
- session
- CWD
- environment
- output
- timeout
- artifacts
- cleanup

The LangGraph layer must NOT contain subprocess or PTY implementation details.

Start with local execution.

Design extension points for Docker/SSH later, but do not build complex unused backend systems before the local runtime is correct.

---

# 10. SESSION AND CWD

Persistent session state is important.

A terminal session should remember its working directory.

Example:

```text
execute("mkdir exploit")
execute("cd exploit")
execute("pwd")
```

The next command should continue in the session's correct CWD.

Do not solve this by blindly prepending:

```text
cd /some/path &&
```

to every command.

CWD is runtime/session state.

Session isolation must prevent one session from accidentally inheriting another session's state.

---

# 11. PROCESS MANAGEMENT

Background execution must be a first-class runtime capability.

Conceptually:

```text
execute(background=true)
      |
      v
   process_id
      |
      +--> poll
      +--> log
      +--> wait
      +--> stdin/input
      +--> terminate
```

Do not make long-running processes opaque.

The agent should be able to launch a server, scanner, listener, or other bounded/interactive process and continue reasoning.

The process manager should handle cleanup and stale-process recovery appropriately.

---

# 12. PTY

PTY support is important for commands that expect a real terminal.

Examples may include:

- interactive shells
- gdb
- ssh
- interactive CLI utilities
- terminal-driven tools

PTY implementation must be isolated inside the runtime.

Do not make the LangGraph graph understand PTY internals.

---

# 13. FILE SYSTEM PRIMITIVES

## read_file

`read_file` should support:

- path
- optional offset/range
- bounded reads
- useful metadata
- large-file handling
- text/binary awareness where appropriate

Do not put huge files directly into LLM context unnecessarily.

## write_file

`write_file` should support a coherent set of operations such as:

- create
- overwrite
- append
- patch/edit

Use one public write interface instead of many overlapping file tools.

Use safe/atomic behavior where appropriate.

---

# 14. TOOL REGISTRY

Implement a provider-neutral Tool Registry.

Define clear contracts for:

```text
ToolSpec
ToolProvider
ToolDiscovery
ToolInvocation
ToolResult
```

The registry should be able to:

- discover tools;
- validate/normalize schemas;
- expose capabilities;
- determine availability;
- identify provider;
- invoke the correct provider;
- normalize results;
- preserve provenance.

A security tool must be represented as metadata, not as a hardcoded branch in orchestration code.

A discovered NyxStrike MCP tool should look to the reasoning layer like a normal Fenrys tool.

A future MCP server should work through the same interface.

---

# 15. DYNAMIC TOOL DISCOVERY

"Dynamic" means:

**extensible without source-code modification.**

Do NOT maintain a hardcoded catalog such as:

```text
nmap -> recon
ffuf -> web
sqlmap -> SQLi
hashcat -> password cracking
```

inside Python orchestration logic.

Instead, tool information should come from providers/discovery.

Tool metadata should support fields conceptually similar to:

```text
name
description
input_schema
capabilities
target_types
provider
availability
execution_mode
timeout
artifact_behavior
risk/policy metadata
```

The model should not receive all available tools blindly.

Implement capability-aware filtering so the model sees tools that are relevant to its current state/objective.

This reduces hallucination and context waste.

---

# 16. MCP ARCHITECTURE

MCP is a generic provider layer.

Implement a generic MCP client/provider abstraction capable of:

- server configuration
- tool discovery
- schema normalization
- invocation
- errors
- timeouts
- availability
- result normalization
- provenance

NyxStrike is one provider.

Do not hardcode:

```text
if provider == nyxstrike:
```

throughout the agent.

Provider-specific implementation belongs inside the provider layer.

---

# 17. NYXSTRIKE ROLE

NyxStrike should be configurable as an optional MCP provider.

Conceptually:

```text
MCP Provider
   |
   +--> NyxStrike
```

Do NOT embed NyxStrike's Flask application or dashboard as a core Fenrys dependency.

Do NOT import NyxStrike internal Python modules into Fenrys's core just to get security tools.

Use the MCP boundary.

The most valuable NyxStrike material for Fenrys is primarily:

- domain knowledge
- CTF/HTB specialist prompt structure
- attack-state semantics
- anti-loop concepts
- tool prioritization concepts
- evidence concepts
- MCP integration patterns

Any NyxStrike source code that is placeholder/simulated should not be copied.

Respect NyxStrike's AGPLv3 license. Prefer consuming it as an external provider instead of copying its implementation into Fenrys.

---

# 18. CYBERSTATE

Create a strongly typed LangGraph-compatible `CyberState`.

It should contain concepts such as:

```text
session
target
scope
goal

phase
objectives

hosts
ports
services
technologies
endpoints

vulnerabilities
credentials
shells

hypotheses
attack_paths
attempts
dead_ends

tool_runs
processes

artifacts
evidence
findings

flags
report metadata

history
confidence
provenance
```

Do not put unlimited raw terminal output into state.

Large outputs should become artifacts/references with bounded summaries or selected views.

State should be designed with reducers and concurrency in mind.

---

# 19. CHECKPOINTING

LangGraph checkpointing should be the runtime persistence mechanism.

The system must be recoverable after interruption.

A resumed session should be able to restore:

- current state
- current objective
- relevant findings
- attempts
- hypotheses
- process/session metadata where recoverable
- phase/history

Do not use `state.json` as the primary source of runtime truth.

A JSON export can exist for debugging/reporting, but LangGraph state + persistence is authoritative.

---

# 20. SPECIALIST AGENTS

Create Fenrys-native specialist reasoning components for cybersecurity domains such as:

```text
recon
network/service enumeration
web
api
credentials
pwn/binary
reverse engineering
crypto
forensics
privesc
verification
```

Specialists should NOT each contain their own duplicated agent runtime.

They should operate through the common Fenrys system.

Each specialist should receive relevant:

- objective
- current state
- evidence
- hypotheses
- prior attempts
- available capabilities/tools

Each specialist should return structured results such as:

```text
status
observations
findings
hypotheses
recommended_actions
evidence
artifacts
confidence
```

Do not hardcode large tool lists inside specialists.

---

# 21. ADAPTIVE REASONING LOOP

The core execution pattern should be approximately:

```text
START
  |
  v
OBSERVE CURRENT STATE
  |
  v
REASON / PLAN
  |
  v
SELECT NEXT ACTION
  |
  +---- specialist
  +---- tool
  +---- terminal
  +---- verification
  |
  v
EXECUTE
  |
  v
OBSERVE RESULT
  |
  v
UPDATE STATE
  |
  v
VERIFY WHEN REQUIRED
  |
  +---- goal achieved --> FINISH
  |
  +---- more evidence --> REASON AGAIN
  |
  +---- pivot needed --> NEW HYPOTHESIS
  |
  +---- retry justified --> NEW STRATEGY
  |
  +---- blocked --> RECOVERY
```

Do not force a fixed number of phases.

The LLM should adapt to evidence.

---

# 22. SEMANTIC PHASES

It is useful to maintain semantic phases:

```text
RECON
ENUM
FOOTHOLD
PRIVESC
FLAG
LOOT
DONE
```

but these are metadata and decision context.

They must NOT prevent valid transitions.

For example:

```text
FOOTHOLD -> RECON
ENUM -> RECON
PRIVESC -> ENUM
WEB -> BINARY
BINARY -> WEB
```

must remain possible whenever evidence justifies the pivot.

---

# 23. HYPOTHESES

Introduce explicit hypothesis handling.

A useful conceptual lifecycle is:

```text
hypothesis
    |
    v
testable action
    |
    v
observation
    |
    +--> supported
    +--> weakened
    +--> rejected
    +--> inconclusive
```

This is preferable to pretending that every tool output is a definitive finding.

---

# 24. VERIFICATION

Verification must be an explicit part of the architecture.

Important claims should not become "confirmed" simply because a command exited with code 0.

Use states such as:

```text
suspected
probable
confirmed
failed
```

Examples:

```text
possible SQLi
   -> verify

possible RCE
   -> verify

possible shell
   -> verify

possible privilege escalation
   -> verify

possible flag
   -> verify provenance
```

Verification should produce structured evidence.

---

# 25. ANTI-LOOP

Anti-loop must be enforced by the system, not only by prompt text.

Record meaningful attempts using information such as:

```text
objective
target
tool
normalized_parameters
strategy
result
timestamp
```

Avoid repeating materially identical actions automatically.

A retry can be justified when:

- new evidence exists;
- parameters materially changed;
- strategy materially changed;
- target state changed;
- a new hypothesis requires the test.

Do not implement only a simplistic string comparison.

---

# 26. EVIDENCE AND ARTIFACTS

Important actions should produce provenance.

Track:

```text
execution
tool
command
target
timestamp
artifact
observation
finding
confidence
source/provenance
```

Artifacts may include:

- command output
- scan results
- generated scripts
- exploit files
- extracted data
- reports
- screenshots when later supported

Do not store huge raw outputs directly in graph state.

Store references and bounded summaries.

A useful evidence chain may use hashing or another provenance mechanism, inspired by NyxStrike, but implement it cleanly and independently.

---

# 27. NORMALIZED RESULTS

All tools and terminal executions should produce a stable result structure.

Conceptually:

```json
{
  "status": "success",
  "tool": "example",
  "execution_id": "exec_...",
  "exit_code": 0,
  "stdout": "...",
  "stderr": "",
  "cwd": "/workspace",
  "duration_ms": 1000,
  "process_id": null,
  "artifacts": [],
  "observations": [],
  "error": null,
  "provenance": {}
}
```

The exact schema may be improved after source inspection and implementation constraints are understood.

The important requirement is consistency.

---

# 28. ERROR HANDLING AND RECOVERY

Handle at least:

- command failure
- command not found
- timeout
- PTY failure
- process termination
- process disappearance
- MCP unavailable
- MCP timeout
- invalid tool input
- provider error
- LLM/tool-call mismatch
- interrupted session
- checkpoint restore
- malformed model output

Failures must become structured information useful to the agent.

Do not silently convert errors into success.

Do not use broad exception handling that hides the root problem.

---

# 29. CONFIGURATION

Configuration should be Fenrys-native.

Separate:

```text
LLM configuration
MCP provider configuration
terminal configuration
session configuration
policy configuration
persistence configuration
```

Do not carry Hermes-specific environment/config naming into the final user-facing product unless there is a compelling technical reason.

Do not expose upstream provider secrets.

Never put real API keys into source code, prompts, tests, logs, or artifacts.

---

# 30. SECURITY BOUNDARY

Fenrys is intended for:

- CTF
- HTB
- authorized security testing
- owned/authorized systems

Execution policy must be implemented at runtime boundaries where appropriate.

Do not treat the LLM as the only security boundary.

Policy should be modular so the operator can configure execution behavior for local labs/CTF environments.

At minimum, the local execution boundary must address the following from the first vertical slice onward (do not defer these to the Step 6 hardening pass, since they affect core execution primitives):

- **Resource limits.** Anything launched via `execute` should have bounded CPU time, memory, and captured-output size. A runaway or output-flooding process must not be able to stall the agent loop or blow up model context.
- **Workspace isolation.** Each session should operate inside a dedicated working directory rather than an arbitrary filesystem root, unless the operator explicitly scopes it wider.
- **Network awareness, not a hidden firewall.** The runtime should be able to distinguish "target network" (e.g. an HTB VPN range) from the operator's general network for reporting/state purposes, but this must be observable and configurable policy, not a silent hardcoded block — the agent still needs real target connectivity to function.
- **Safe archive extraction.** Any archive extraction — including the two reference ZIPs in Section 2 and any CTF-provided archives — must validate entry paths and reject entries that would write outside the intended extraction directory (zip-slip), and should cap total extracted size. This applies to Step 1 (Inspect) as well as any runtime extraction Fenrys performs later.
- **Credential/secret handling.** Credentials discovered during an engagement (cracked passwords, tokens, session cookies, etc.) are evidence and belong in `CyberState`/evidence storage, not echoed in plaintext into logs, prompts, or artifacts beyond what is operationally necessary.

---

# 31. UI AND BRANDING

The final product name is:

**Fenrys-CAI**

The product should be terminal-first.

Do not carry Hermes or NousResearch branding into the user-facing application.

Remove/replace:

- Hermes logos
- Hermes splash screens
- Hermes names in CLI UI
- Hermes-specific product terminology
- Hermes user-facing configuration names
- Hermes user-facing help text

NyxStrike is an integration/provider and should not become Fenrys branding.

Fenrys must have its own CLI identity and terminology.

Respect upstream license requirements for retained/derived code.

Hermes and NyxStrike licensing must be handled correctly. Do not remove required copyright/license notices.

---

# 32. WHAT MUST BE REMOVED FROM HERMES

The final Fenrys core should NOT carry unrelated Hermes features such as:

```text
browser/web tooling
unnecessary generic search tooling
unnecessary generic file tooling
generic productivity features
desktop integrations
messaging
bots
cron
unrelated coding-agent wrappers
OpenHands integrations
Codex integrations
OpenCode integrations
Gemini-specific integrations
provider-specific unrelated features
enterprise account infrastructure
unrelated evaluation systems
```

Keep only execution/runtime capabilities that are truly useful to Fenrys.

If an existing Hermes module is too tightly coupled, rewrite it instead of dragging the coupling into Fenrys.

---

# 33. WHAT MUST NOT BE HARDcoded FROM NYXSTRIKE

Do NOT create hardcoded mappings such as:

```text
nmap -> recon
rustscan -> recon
ffuf -> web
sqlmap -> SQLi
hashcat -> crypto
```

inside the orchestration layer.

Do NOT copy a 200+ tool catalog into Fenrys.

Do NOT make the graph aware of NyxStrike's internal tool names.

Do NOT make specialist logic depend on NyxStrike Python internals.

Use dynamic provider discovery.

---

# 34. PROJECT STRUCTURE

Design toward a clean Fenrys-native structure similar in spirit to:

```text
fenrys-cai/
|
├── app/
│   └── cli/
|
├── core/
│   ├── agent/
│   ├── graph/
│   ├── state/
│   ├── routing/
│   └── verification/
|
├── specialists/
│   ├── recon/
│   ├── web/
│   ├── api/
│   ├── network/
│   ├── pwn/
│   ├── crypto/
│   ├── reverse/
│   ├── forensics/
│   ├── credentials/
│   └── privesc/
|
├── runtime/
│   ├── terminal/
│   ├── process/
│   ├── pty/
│   ├── session/
│   └── environments/
|
├── tools/
│   ├── registry/
│   ├── discovery/
│   ├── result/
│   └── providers/
│       ├── local/
│       └── mcp/
|
├── intelligence/
│   ├── hypotheses/
│   ├── attack_graph/
│   └── scoring/
|
├── persistence/
│   ├── checkpoint/
│   ├── sessions/
│   ├── artifacts/
│   └── evidence/
|
├── prompts/
│   ├── system/
│   └── specialists/
|
└── tests/
```

This is a target shape, not an excuse to create unnecessary abstraction.

Use the simplest structure that correctly satisfies the architecture.

---

# 35. IMPLEMENTATION STRATEGY

This is a real implementation task.

Do not stop after writing architecture documents.

Work incrementally.

## Step 1 — Inspect

First:

- inspect current working directory;
- inspect both ZIP archives;
- extract them safely (see Section 30 — validate entry paths, reject zip-slip, cap extracted size);
- verify contents/version;
- inspect relevant source files;
- confirm dependency assumptions.

Do not claim a module is understood without inspecting it.

## Step 2 — Establish project

Create the Fenrys-CAI codebase and native package structure.

## Step 3 — First vertical slice

Implement the smallest end-to-end working path:

```text
CLI
 -> LangGraph
 -> LLM reasoning
 -> Tool Registry
 -> read_file
 -> write_file
 -> execute
 -> Local Terminal Runtime
 -> normalized ToolResult
 -> CyberState
 -> checkpoint
```

Test this before adding broad functionality.

## Step 4 — MCP

Implement generic MCP provider/discovery.

Then integrate NyxStrike through that provider.

## Step 5 — Cyber intelligence

Add:

- specialists
- hypotheses
- semantic phases
- verification
- anti-loop
- evidence
- artifact handling
- adaptive routing

## Step 6 — Hardening

Add:

- recovery
- concurrency correctness
- process lifecycle edge cases
- session isolation
- output limits
- provider failures
- checkpoint recovery

## Step 7 — Cleanup

Only after replacements are working:

- remove obsolete Hermes-derived code;
- remove unnecessary dependencies;
- remove leftover Hermes branding;
- remove accidental NyxStrike hardcoding;
- simplify architecture where possible.

---

# 36. TESTING REQUIREMENTS

Write real tests for critical behavior.

At minimum:

```text
terminal execution
persistent CWD
session isolation
environment handling
foreground execution
background process
process polling
process wait
process termination
PTY
stdin
timeout
output bounds
artifact storage

read_file
write_file

ToolSpec validation
Tool Registry
provider discovery
MCP normalization
provider failure

CyberState reducers
LangGraph execution
checkpoint restore

hypothesis lifecycle
anti-loop enforcement
verification
evidence/provenance
recovery
```

Prefer local deterministic fixtures.

Do not require an actual HTB target for unit/integration tests of the core.

Add a harmless end-to-end demonstration task for the local runtime.

---

# 37. DOCUMENTATION

Maintain these project documents:

```text
ARCHITECTURE.md
DECISIONS.md
MIGRATION_PLAN.md
```

They should describe the actual implemented architecture.

Use them to record:

- important decisions;
- boundaries;
- migration reasoning;
- upstream source references;
- rejected alternatives.

Do not create excessive documentation files without a reason.

---

# 38. GIT / CHANGE MANAGEMENT

Work incrementally.

Create logical git commits/checkpoints after major coherent milestones when practical.

Before destructive changes:

- verify the replacement exists;
- run relevant tests;
- confirm dependencies;
- inspect the diff.

Do not wipe the reference archives.

Do not modify the reference ZIP files.

Keep source references isolated from the final Fenrys project.

---

# 39. IMPORTANT ENGINEERING RULES

1. Do not blindly copy code from Hermes.
2. Do not blindly copy code from NyxStrike.
3. Do not build a monolithic agent.
4. Do not build a rigid CTF phase pipeline.
5. Do not hardcode security tools into orchestration.
6. Do not make NyxStrike a core dependency.
7. Do not make MCP mandatory.
8. Do not make LangGraph responsible for subprocess internals.
9. Do not put giant raw outputs into graph state.
10. Do not trust command exit code as proof of success.
11. Do not rely only on prompts for anti-loop behavior.
12. Do not hide failures.
13. Do not add hypothetical infrastructure before it is needed.
14. Do not preserve unnecessary Hermes complexity.
15. Do not repeatedly ask the user for decisions already settled here.
16. When unspecified, inspect actual source and choose the simplest coherent implementation.
17. When source evidence conflicts with assumptions, trust the source and update the design.
18. Never fabricate tool availability, test results, integrations, or successful exploitation.
19. Never put API keys or credentials in source, prompts, logs, tests, or artifacts.
20. Keep Fenrys independent from any specific LLM provider and any specific security-tool provider.

---

# 40. DEFINITION OF DONE

Do not declare Fenrys-CAI complete until the following are genuinely working:

```text
Fenrys CLI starts
        |
        v
LLM agent loop works
        |
        v
LangGraph state/checkpoint works
        |
        v
Tool Registry works
        |
        +--> read_file
        +--> write_file
        +--> execute
        |
        v
Local terminal works
        |
        +--> foreground
        +--> background
        +--> PTY
        +--> process lifecycle
        +--> persistent CWD
        |
        v
Normalized results work
        |
        v
MCP discovery works
        |
        v
NyxStrike can be configured as optional provider
        |
        v
Specialists can reason from shared state
        |
        v
Adaptive loops/pivots work
        |
        v
Verification works
        |
        v
Anti-loop works
        |
        v
Evidence/artifacts work
        |
        v
Recovery/checkpoint restore works
        |
        v
Tests pass
```

Also verify:

- no accidental Hermes user-facing branding remains;
- no hardcoded NyxStrike tool catalog remains in orchestration;
- Fenrys can run without NyxStrike configured;
- no critical dependency on Hermes remains merely for branding or convenience;
- architecture remains understandable to a senior engineer.

---

# 41. OPERATING MODE

You are authorized to inspect, create, modify, move, delete, and test project files in the current working directory as required for this implementation.

Do not modify the two reference ZIP files themselves.

Use subagents only when parallel work provides real value, such as independent repository analysis or isolated review.

Do not spawn agents for trivial work.

Before claiming completion, test the actual implementation.

If an architectural assumption turns out to be wrong after source inspection:

1. identify the evidence;
2. update `DECISIONS.md` if necessary;
3. adjust the implementation;
4. continue.

Do not hide architectural changes.

---

# 42. START NOW

Start building Fenrys-CAI now.

Your first concrete actions must be:

1. Inspect `~/Dokumen/claude`.
2. Inspect and safely extract:
   - `hermes-agent-main.zip`
   - `nyxstrike-master.zip`
3. Verify actual repository contents and versions.
4. Inspect the relevant Hermes runtime/tool/process files and NyxStrike CTF/MCP/prompt files.
5. Establish the Fenrys-CAI project structure.
6. Create/update:
   - `ARCHITECTURE.md`
   - `DECISIONS.md`
   - `MIGRATION_PLAN.md`
7. Implement the first working vertical slice:
   - CLI
   - LangGraph
   - LLM
   - Tool Registry
   - read_file
   - write_file
   - execute
   - local terminal runtime
   - normalized result
   - CyberState
   - checkpointing
8. Run real tests.
9. Fix discovered problems.
10. Continue incrementally with MCP, NyxStrike provider, specialists, verification, anti-loop, evidence, recovery, and broader testing.
11. Only remove obsolete reference-derived code after Fenrys replacements are functioning.
12. Keep the final codebase Fenrys-native and minimal.

Do not merely describe what should be built.

**Build it.**
