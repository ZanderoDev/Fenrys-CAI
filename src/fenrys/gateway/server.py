from __future__ import annotations

import asyncio
import json
import sys
import uuid
from typing import Any

from fenrys.agents.runtime import InvestigationRuntime
from fenrys.config import ConfigManager
from fenrys.state import StateStore


class GatewayServer:
    """JSON-RPC 2.0 server over stdio for Fenrys backend.

    Protocol:
        Request:  {"jsonrpc":"2.0","id":1,"method":"prompt","params":{"text":"scan"}}
        Response: {"jsonrpc":"2.0","id":1,"result":{...}}
        Event:    {"jsonrpc":"2.0","method":"event","params":{"type":"token","delta":"..."}}
    """

    def __init__(self, config: ConfigManager):
        self.config = config
        cfg = config.load("config.yaml")
        self.store = StateStore(cfg["database_path"])
        self.runtimes: dict[str, InvestigationRuntime] = {}
        self._active_session: str | None = None

    async def run(self) -> None:
        """Main loop: read JSON-RPC requests from stdin, write to stdout."""
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        loop = asyncio.get_event_loop()
        await loop.connect_read_pipe(lambda: protocol, sys.stdin.buffer)

        writer_transport, writer_protocol = await loop.connect_write_pipe(
            asyncio.streams.FlowControlMixin, sys.stdout.buffer
        )
        writer = asyncio.StreamWriter(writer_transport, writer_protocol, None, loop)

        self._writer = writer

        while True:
            try:
                line = await reader.readline()
                if not line:
                    break
                line = line.decode().strip()
                if not line:
                    continue

                request = json.loads(line)
                response = await self._handle(request)

                if response is not None:
                    data = json.dumps(response) + "\n"
                    writer.write(data.encode())
                    await writer.drain()
            except json.JSONDecodeError as exc:
                error_resp = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": f"Parse error: {exc}"}
                }
                writer.write((json.dumps(error_resp) + "\n").encode())
                await writer.drain()
            except Exception as exc:
                error_resp = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32603, "message": f"Internal error: {exc}"}
                }
                writer.write((json.dumps(error_resp) + "\n").encode())
                await writer.drain()

    async def _handle(self, request: dict[str, Any]) -> dict[str, Any] | None:
        """Route JSON-RPC request to handler."""
        method = request.get("method", "")
        params = request.get("params", {})
        req_id = request.get("id")

        handlers = {
            "session.new": self._session_new,
            "session.list": self._session_list,
            "session.get": self._session_get,
            "session.delete": self._session_delete,
            "prompt": self._prompt,
            "ping": self._ping,
            "health": self._health,
        }

        handler = handlers.get(method)
        if not handler:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"}
            }

        try:
            result = await handler(params)
            if result is None:
                return None  # Async method, events sent separately
            return {"jsonrpc": "2.0", "id": req_id, "result": result}
        except KeyError as exc:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32602, "message": f"Invalid params: {exc}"}
            }
        except Exception as exc:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32603, "message": f"Server error: {type(exc).__name__}: {str(exc)[:200]}"}
            }

    # ─── Session Methods ───────────────────────────────────────────────────

    async def _session_new(self, params: dict[str, Any]) -> dict[str, Any]:
        """Create a new investigation session."""
        target = params.get("target", "")
        mode = params.get("mode", "CTF")
        scope = self.config.load("scope.yaml")

        session_id = self.store.create_session(mode, target, scope)
        runtime = InvestigationRuntime(self.config, self.store)
        self.runtimes[session_id] = runtime
        self._active_session = session_id

        return {
            "session_id": session_id,
            "target": target,
            "mode": mode,
        }

    async def _session_list(self, params: dict[str, Any]) -> dict[str, Any]:
        """List all sessions."""
        sessions = self.store.list_sessions()
        return {"sessions": sessions}

    async def _session_get(self, params: dict[str, Any]) -> dict[str, Any]:
        """Get session details."""
        session_id = params.get("session_id") or self._active_session
        if not session_id:
            raise KeyError("session_id")
        session = self.store.get_session(session_id)
        if not session:
            raise KeyError(f"Session not found: {session_id}")
        return {"session": session}

    async def _session_delete(self, params: dict[str, Any]) -> dict[str, Any]:
        """Delete a session."""
        session_id = params.get("session_id") or self._active_session
        if not session_id:
            raise KeyError("session_id")
        self.store.delete_session(session_id)
        self.runtimes.pop(session_id, None)
        if self._active_session == session_id:
            self._active_session = None
        return {"deleted": session_id}

    # ─── Prompt Method ─────────────────────────────────────────────────────

    async def _prompt(self, params: dict[str, Any]) -> None:
        """Process a prompt with streaming events. Returns None (async)."""
        text = params.get("text", "")
        session_id = params.get("session_id") or self._active_session

        if not session_id:
            self._emit_error("No active session. Call session.new first.")
            return

        runtime = self.runtimes.get(session_id)
        if not runtime:
            self._emit_error(f"Runtime not found for session: {session_id}")
            return

        async def on_token(delta: str) -> None:
            self._emit({"type": "token", "delta": delta})

        async def on_event(kind: str, payload: str) -> None:
            if kind == "tool":
                self._emit({"type": "tool.start", "tool": payload})
            elif kind == "result":
                self._emit({"type": "tool.end", "result": payload})
            elif kind == "delegate":
                self._emit({"type": "delegate", "info": payload})
            elif kind == "error":
                self._emit({"type": "error", "message": payload})
            else:
                self._emit({"type": kind, "message": payload})

        async def on_usage(usage: dict[str, Any]) -> None:
            self._emit({"type": "usage", **usage})

        try:
            result = await runtime.run_chat_streaming(
                session_id, text,
                on_token=on_token,
                on_event=on_event,
                on_usage=on_usage,
            )
            self._emit({
                "type": "response.done",
                "content": result.summary,
                "provider": result.provider,
                "model": result.model,
                "tool_calls": result.tool_calls,
            })
        except Exception as exc:
            self._emit_error(f"Prompt failed: {type(exc).__name__}: {str(exc)[:300]}")

    # ─── Utility Methods ───────────────────────────────────────────────────

    async def _ping(self, params: dict[str, Any]) -> dict[str, Any]:
        """Health check ping."""
        return {"pong": True, "sessions": len(self.runtimes)}

    async def _health(self, params: dict[str, Any]) -> dict[str, Any]:
        """Detailed health status."""
        from fenrys.integrations import HexStrikeAdapter
        adapter = HexStrikeAdapter(self.config.load("config.yaml")["hexstrike_url"])
        healthy, info = await adapter.health()
        return {
            "fenrys": True,
            "hexstrike": healthy,
            "hexstrike_info": info,
            "active_sessions": len(self.runtimes),
            "active_session": self._active_session,
        }

    # ─── Event Emission ────────────────────────────────────────────────────

    def _emit(self, event: dict[str, Any]) -> None:
        """Write event to stdout and flush."""
        msg = {"jsonrpc": "2.0", "method": "event", "params": event}
        data = json.dumps(msg) + "\n"
        self._writer.write(data.encode())
        # Schedule drain in the event loop
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(self._writer.drain())

    def _emit_error(self, message: str) -> None:
        """Emit an error event."""
        self._emit({"type": "error", "message": message})


def main():
    """Entry point for `python -m fenrys.gateway`."""
    import argparse
    parser = argparse.ArgumentParser(description="Fenrys Gateway Server")
    parser.add_argument("--config-dir", default=None, help="Config directory path")
    args = parser.parse_args()

    config = ConfigManager(args.config_dir)
    server = GatewayServer(config)
    asyncio.run(server.run())


if __name__ == "__main__":
    main()
