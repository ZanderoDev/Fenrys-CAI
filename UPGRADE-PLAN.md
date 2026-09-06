# Fenrys-CAI Full-Stack Upgrade Plan

## Architecture Overview

```
Phase 1 (Python Prototype)     Phase 3 (Node.js TUI)
┌──────────────────────┐       ┌──────────────────────┐
│  Textual 2.x TUI     │  →→→  │  React Ink TUI       │
│  (in-process)         │       │  (stdio JSON-RPC)    │
└──────────┬───────────┘       └──────────┬───────────┘
           │                              │
           └──────────┬───────────────────┘
                      │
           ┌──────────▼───────────┐
           │  Python Backend      │
           │  (existing code)     │
           │  + streaming support │
           │  + gateway server    │
           └──────────────────────┘
```

---

## Phase 1: Python Prototype (Textual 2.x)

### Goal
Upgrade the existing TUI to support streaming, status bar, and tool visualization. All within Python.

### 1.1 Provider Streaming Support

**File: `src/fenrys/providers/base.py`**
```python
class ModelProvider(ABC):
    # Add streaming abstract method
    @abstractmethod
    async def stream(
        self,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        max_tokens: int = 1024,
        temperature: float | None = None,
    ) -> AsyncIterator[ModelStreamChunk]:
        raise NotImplementedError
```

**File: `src/fenrys/providers/openai_compatible_provider.py`**
```python
class OpenAICompatibleProvider(ModelProvider):
    async def stream(self, messages, tools=None, max_tokens=1024, temperature=None):
        payload = {
            "model": self.model,
            "messages": [...],
            "max_tokens": max_tokens,
            "stream": True,  # Enable SSE
        }
        if tools:
            payload["tools"] = [...]
            payload["tool_choice"] = "auto"

        async with httpx.AsyncClient(timeout=httpx.Timeout(300, read=300)) as client:
            async with client.stream("POST", f"{self.base_url}/chat/completions",
                                      json=payload, headers=self._headers()) as response:
                tool_calls_acc = {}
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data.strip() == "[DONE]":
                            break
                        chunk = json.loads(data)
                        delta = chunk["choices"][0]["delta"]

                        # Content delta
                        if delta.get("content"):
                            yield ModelStreamChunk(
                                content=delta["content"],
                                tool_calls=[],
                                finished=False,
                            )

                        # Tool call deltas
                        if delta.get("tool_calls"):
                            for tc in delta["tool_calls"]:
                                idx = tc.get("index", 0)
                                if idx not in tool_calls_acc:
                                    tool_calls_acc[idx] = {
                                        "id": tc.get("id", ""),
                                        "type": "function",
                                        "function": {"name": "", "arguments": ""}
                                    }
                                if tc.get("id"):
                                    tool_calls_acc[idx]["id"] = tc["id"]
                                if tc.get("function", {}).get("name"):
                                    tool_calls_acc[idx]["function"]["name"] = tc["function"]["name"]
                                if tc.get("function", {}).get("arguments"):
                                    tool_calls_acc[idx]["function"]["arguments"] += tc["function"]["arguments"]

                # Final assembled tool calls
                assembled = list(tool_calls_acc.values())
                yield ModelStreamChunk(
                    content="",
                    tool_calls=assembled,
                    finished=True,
                )
```

### 1.2 Orchestrator Streaming

**File: `src/fenrys/orchestrator/engine.py`**
```python
async def run_agent_loop_streaming(
    self,
    provider: Any,
    messages: list[Message],
    tools: list[ToolSpec],
    tool_handler: Callable,
    on_token: Callable[[str], Awaitable[None]] | None = None,
    on_tool_start: Callable[[str, dict], Awaitable[None]] | None = None,
    on_tool_end: Callable[[str, NormalizedToolResult], Awaitable[None]] | None = None,
    max_turns: int = 8,
    max_tokens: int = 1400,
) -> ModelResponse:
    full_content = ""
    all_tool_calls = []

    async for chunk in provider.stream(messages, tools, max_tokens):
        if chunk.content and on_token:
            full_content += chunk.content
            await on_token(chunk.content)

        if chunk.finished and chunk.tool_calls:
            all_tool_calls = chunk.tool_calls
            break

    if not all_tool_calls:
        return ModelResponse(full_content, provider.model, provider.name)

    # Handle tool calls (same logic as before)
    messages.append(Message("assistant", full_content, tool_calls=all_tool_calls))
    for raw_call in all_tool_calls:
        name, arguments = self._parts(raw_call)
        if on_tool_start:
            await on_tool_start(name, arguments)
        output, ok = await tool_handler(name, arguments)
        if on_tool_end:
            await on_tool_end(name, output)
        call_id = raw_call.get("id")
        messages.append(Message("tool", output, tool_call_id=call_id))

    # Continue loop
    return await self.run_agent_loop_streaming(
        provider, messages, tools, tool_handler,
        on_token, on_tool_start, on_tool_end,
        max_turns - 1, max_tokens
    )
```

### 1.3 Runtime Streaming

**File: `src/fenrys/agents/runtime.py`**
```python
async def run_chat_streaming(self, session_id, prompt, on_token=None, on_event=None):
    # ... setup code stays the same ...

    async def handle(name, arguments):
        # ... tool handling stays the same ...

    async def on_token_forward(delta):
        if on_token:
            await on_token(delta)

    orchestrator = Orchestrator(self.store, budget)
    response = await orchestrator.run_agent_loop_streaming(
        provider, messages, tools, handle,
        on_token=on_token_forward,
        on_tool_start=lambda n, a: on_event("tool", n) if on_event else None,
        on_tool_end=lambda n, r: on_event("result", f"{n} {'ok' if r.success else 'failed'}") if on_event else None,
        max_turns=...,
        max_tokens=...,
    )
    # ... persist + return ...
```

### 1.4 New TUI Components

**File: `src/fenrys/ui/components/status_bar.py`**
```python
class StatusBar(Widget):
    """Live status bar: model, tokens, context, cost."""
    model: str = "minimax/minimax-m3:free"
    tokens_used: int = 0
    tokens_max: int = 128000
    cost: float = 0.0
    context_bar: Static

    def compose(self) -> ComposeResult:
        yield Static(self._render(), id="status-text")

    def _render(self) -> str:
        pct = (self.tokens_used / self.tokens_max * 100) if self.tokens_max else 0
        filled = int(pct / 10)
        bar = "█" * filled + "░" * (10 - filled)
        return (
            f"⚕ {self.model} │ "
            f"{self.tokens_used:,}/{self.tokens_max:,} │ "
            f"[{bar}] {pct:.0f}% │ "
            f"${self.cost:.2f}"
        )

    def update_tokens(self, used: int, max_tokens: int = None):
        self.tokens_used = used
        if max_tokens:
            self.tokens_max = max_tokens
        self.query_one("#status-text").update(self._render())
```

**File: `src/fenrys/ui/components/tool_tree.py`**
```python
class ToolTree(Widget):
    """Visual tool execution tree."""
    tools: list[dict] = []

    def compose(self) -> ComposeResult:
        for tool in self.tools:
            status = "✓" if tool["success"] else "✗"
            time = f"{tool['duration_ms']}ms"
            yield Static(f"  {status} {tool['name']} {time}")
            if tool.get("findings"):
                for f in tool["findings"]:
                    yield Static(f"    └─ {f}")
```

**File: `src/fenrys/ui/components/streaming_chat.py`**
```python
class StreamingChat(Widget):
    """Chat pane with streaming token support."""
    content_buffer: str = ""

    def compose(self) -> ComposeResult:
        yield RichLog(id="chat", highlight=True, markup=True, wrap=True)

    def on_token(self, delta: str):
        """Append token to current response."""
        self.content_buffer += delta
        # RichLog supports incremental write
        log = self.query_one("#chat", RichLog)
        # Clear last line, write updated content
        log.write(delta, end="")

    def finish_response(self):
        """Finalize the current response."""
        self.content_buffer = ""
```

### 1.5 Upgraded Main App

**File: `src/fenrys/ui/app_v2.py`**
```python
class FenrysAppV2(App):
    TITLE = "Fenrys"
    CSS = NIGHTSHADE_CSS

    def compose(self) -> ComposeResult:
        yield Header()
        yield StatusBar(id="status")
        yield StreamingChat(id="chat")
        yield ToolTree(id="tools")
        yield Input(placeholder="› Ask Fenrys...", id="command")
        yield Footer()

    async def _run_prompt(self, prompt: str):
        status = self.query_one("#status", StatusBar)
        chat = self.query_one("#chat", StreamingChat)

        status.set_status("thinking")

        async def on_token(delta):
            chat.on_token(delta)
            status.update_tokens(...)  # from provider usage

        async def on_event(kind, payload):
            if kind == "tool":
                status.set_status(f"⚙ {payload}")
            elif kind == "result":
                status.set_status("● reasoning")

        result = await self.runtime.run_chat_streaming(
            self.session_id, prompt,
            on_token=on_token,
            on_event=on_event,
        )
        chat.finish_response()
        status.set_status("ready")
```

---

## Phase 2: Gateway Protocol (JSON-RPC stdio)

### Goal
Expose the Python backend as a JSON-RPC 2.0 server over stdio, so any TUI frontend can connect.

### 2.1 Protocol Spec

```json
// Request: Prompt
{"jsonrpc":"2.0","id":1,"method":"prompt","params":{"text":"scan target"}}

// Request: New session
{"jsonrpc":"2.0","id":2,"method":"session.new","params":{"target":"10.10.10.1","mode":"CTF"}}

// Request: List sessions
{"jsonrpc":"2.0","id":3,"method":"session.list","params":{}}

// Event: Token delta
{"jsonrpc":"2.0","method":"event","params":{"type":"token","delta":"Target has"}}

// Event: Tool start
{"jsonrpc":"2.0","method":"event","params":{"type":"tool.start","tool":"nmap_scan","args":{"target":"10.10.10.1"}}}

// Event: Tool end
{"jsonrpc":"2.0","method":"event","params":{"type":"tool.end","tool":"nmap_scan","success":true,"duration_ms":2300}}

// Event: Agent delegation
{"jsonrpc":"2.0","method":"event","params":{"type":"delegate","agent":"web","task":"enumerate web"}}

// Event: Final response
{"jsonrpc":"2.0","method":"event","params":{"type":"response.done","content":"Target has 2 open ports..."}}

// Response: Error
{"jsonrpc":"2.0","id":1,"error":{"code":-32600,"message":"Invalid session"}}
```

### 2.2 Gateway Server

**File: `src/fenrys/gateway/server.py`**
```python
import sys
import json
import asyncio
from typing import Any

class GatewayServer:
    """JSON-RPC 2.0 server over stdio for Fenrys backend."""

    def __init__(self, config: ConfigManager):
        self.config = config
        self.sessions: dict[str, InvestigationRuntime] = {}
        self._request_id = 0

    async def run(self):
        """Main loop: read requests from stdin, write responses to stdout."""
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, sys.stdin)

        while True:
            line = await reader.readline()
            if not line:
                break
            request = json.loads(line.decode())
            response = await self._handle(request)
            if response:
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()

    async def _handle(self, request: dict) -> dict | None:
        method = request.get("method")
        params = request.get("params", {})
        req_id = request.get("id")

        if method == "session.new":
            session_id = await self._session_new(params)
            return {"jsonrpc": "2.0", "id": req_id, "result": {"session_id": session_id}}

        elif method == "prompt":
            await self._prompt(params)
            return None  # Events are sent async

        elif method == "session.list":
            sessions = self._session_list()
            return {"jsonrpc": "2.0", "id": req_id, "result": {"sessions": sessions}}

        return {"jsonrpc": "2.0", "id": req_id,
                "error": {"code": -32601, "message": f"Unknown method: {method}"}}

    async def _prompt(self, params: dict):
        text = params["text"]
        session_id = params.get("session_id", "default")

        async def on_token(delta):
            self._emit({"type": "token", "delta": delta})

        async def on_event(kind, payload):
            self._emit({"type": kind, **payload})

        runtime = self.sessions.get(session_id)
        if runtime:
            await runtime.run_chat_streaming(session_id, text, on_token, on_event)

    def _emit(self, event: dict):
        msg = {"jsonrpc": "2.0", "method": "event", "params": event}
        sys.stdout.write(json.dumps(msg) + "\n")
        sys.stdout.flush()
```

---

## Phase 3: Node.js TUI (React Ink)

### Goal
Build a production-quality TUI frontend using React Ink, communicating with the Python gateway via JSON-RPC over stdio.

### 3.1 Project Structure

```
ui/
├── package.json
├── tsconfig.json
├── src/
│   ├── index.tsx              # Entry point
│   ├── app.tsx                # Root App component
│   ├── gateway/
│   │   ├── client.ts          # JSON-RPC stdio client
│   │   └── protocol.ts        # Message types
│   ├── components/
│   │   ├── AppLayout.tsx      # Main layout
│   │   ├── StatusBar.tsx      # Model, tokens, cost, context bar
│   │   ├── ChatPane.tsx       # Streaming message display
│   │   ├── ToolTree.tsx       # Tool execution visualization
│   │   ├── TextInput.tsx      # Multiline input editor
│   │   ├── SlashMenu.tsx      # Autocomplete dropdown
│   │   └── Approval.tsx       # Danger command modal
│   ├── hooks/
│   │   ├── useGateway.ts      # Gateway connection hook
│   │   ├── useStream.ts       # Streaming state hook
│   │   └── useSlashCommands.ts
│   ├── theme/
│   │   └── engine.ts          # Dark/light detection
│   └── types.ts
└── build/
```

### 3.2 Gateway Client

```typescript
// src/gateway/client.ts
import { spawn, ChildProcess } from 'child_process';
import { EventEmitter } from 'events';

export class GatewayClient extends EventEmitter {
    private process: ChildProcess;
    private requestId = 0;
    private pending = new Map<number, { resolve: Function, reject: Function }>();

    constructor(pythonPath: string, gatewayModule: string) {
        super();
        this.process = spawn(pythonPath, ['-m', gatewayModule], {
            stdio: ['pipe', 'pipe', 'pipe'],
        });

        this.process.stdout.on('data', (data) => {
            const lines = data.toString().split('\n').filter(Boolean);
            for (const line of lines) {
                const msg = JSON.parse(line);
                if (msg.id && this.pending.has(msg.id)) {
                    this.pending.get(msg.id)!.resolve(msg.result || msg.error);
                    this.pending.delete(msg.id);
                } else if (msg.method === 'event') {
                    this.emit('event', msg.params);
                }
            }
        });
    }

    async request(method: string, params: any = {}): Promise<any> {
        const id = ++this.requestId;
        return new Promise((resolve, reject) => {
            this.pending.set(id, { resolve, reject });
            this.process.stdin.write(JSON.stringify({ jsonrpc: '2.0', id, method, params }) + '\n');
        });
    }

    sendPrompt(text: string, sessionId?: string) {
        return this.request('prompt', { text, session_id: sessionId });
    }

    newSession(target?: string, mode?: string) {
        return this.request('session.new', { target, mode });
    }
}
```

### 3.3 React Ink Components

```tsx
// src/app.tsx
import React from 'react';
import { AppLayout } from './components/AppLayout';
import { useGateway } from './hooks/useGateway';
import { useStream } from './hooks/useStream';

export default function App() {
    const gateway = useGateway();
    const stream = useStream(gateway);

    return (
        <AppLayout
            messages={stream.messages}
            status={stream.status}
            toolCalls={stream.toolCalls}
            onsubmit={(text) => gateway.sendPrompt(text)}
        />
    );
}
```

---

## Phase 4: Integration & Testing

### 4.1 Test Matrix

| Test | Description | Priority |
|------|-------------|----------|
| Provider streaming | SSE parse, delta assembly, tool call accumulation | P0 |
| Orchestrator loop | Token relay, tool dispatch, max turns | P0 |
| Gateway protocol | JSON-RPC request/response, event emission | P0 |
| TUI rendering | Streaming text, tool tree, status bar | P1 |
| Session management | New, list, resume, delete | P1 |
| Error handling | Provider timeout, MCP failure, scope block | P1 |
| Slash commands | /help, /new, /status, /doctor, /clear | P2 |
| Theme detection | Dark/light auto-switch | P2 |
| Distribution | Bundle Python + Node, installer script | P3 |

### 4.2 Integration Test Script

```bash
# Test 1: Provider streaming
python -m fenrys.gateway.server &
echo '{"jsonrpc":"2.0","id":1,"method":"session.new","params":{}}' | nc -U /tmp/fenrys.sock
echo '{"jsonrpc":"2.0","id":2,"method":"prompt","params":{"text":"hello"}}' | nc -U /tmp/fenrys.sock

# Test 2: Full loop
cd ui && npm start  # Launches Node.js TUI
# Type "scan 10.10.10.1" → observe streaming, tool calls, findings
```

---

## Phase 5: Polish & Distribution

### 5.1 Theme Engine

```typescript
// Detect terminal background
async function detectTheme(): Promise<'dark' | 'light'> {
    // 1. Check env var
    if (process.env.FENRYS_THEME) return process.env.FENRYS_THEME as any;

    // 2. Check COLORFGBG
    if (process.env.COLORFGBG) {
        const parts = process.env.COLORFGBG.split(';');
        const bg = parseInt(parts[parts.length - 1]);
        return bg > 12 ? 'light' : 'dark';
    }

    // 3. OSC 11 probe (modern terminals)
    return 'dark'; // fallback
}
```

### 5.2 Distribution

```bash
# Option A: uv + npm
curl -fsSL https://fenrys-cai.local/install.sh | bash
# Installs: Python 3.13, uv, Node.js, fenrys-cai

# Option B: Docker
docker run -it --rm fenrys-cai

# Option C: Single binary (PyInstaller + pkg)
# Advanced: bundle Python + Node into single executable
```

---

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Textual 2.x breaking changes | Medium | Pin version, test incrementally |
| Provider SSE format differences | High | Test with OpenRouter, Anthropic, OpenAI |
| Node.js dependency for users | Medium | Provide Docker option |
| Gateway protocol stability | High | Version the protocol, backward compat |
| Streaming tool call accumulation | Medium | Reference Hermes implementation |

---

## Timeline Estimate

| Phase | Duration | Dependencies |
|-------|----------|--------------|
| Phase 1: Python Prototype | 2-3 weeks | None |
| Phase 2: Gateway Protocol | 1 week | Phase 1 |
| Phase 3: Node.js TUI | 3-4 weeks | Phase 2 |
| Phase 4: Integration | 1-2 weeks | Phase 3 |
| Phase 5: Polish | 2 weeks | Phase 4 |
| **Total** | **9-12 weeks** | |

---

## Success Criteria

- [ ] Token-by-token streaming works in Python TUI
- [ ] Status bar shows live model, tokens, cost
- [ ] Tool calls render as tree with duration/status
- [ ] Gateway protocol handles all session operations
- [ ] Node.js TUI connects to Python gateway
- [ ] Slash commands with autocomplete
- [ ] Dark/light theme auto-detection
- [ ] Distribution script works on clean system
