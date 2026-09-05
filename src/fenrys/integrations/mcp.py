from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx


class MCPClient:
    """Minimal JSON-RPC-over-HTTP client used by the HexStrike adapter."""

    def __init__(self, base_url: str, timeout: float = 15):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(self.base_url, json={"jsonrpc": "2.0", "id": 1,
                                                               "method": method, "params": params or {}})
            response.raise_for_status()
            return response.json()

    async def list_tools(self) -> list[dict[str, Any]]:
        data = await self.request("tools/list")
        return ((data.get("result") or {}).get("tools") or [])


class StdioMCPClient:
    """Small MCP stdio transport for the upstream hexstrike_mcp.py process."""

    def __init__(self, command: list[str], startup_timeout: float = 15):
        self.command = command
        self.startup_timeout = startup_timeout
        self.process: asyncio.subprocess.Process | None = None
        self._request_id = 0
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        if self.process and self.process.returncode is None:
            return
        async with self._lock:
            if self.process and self.process.returncode is None:
                return
            self.process = await asyncio.create_subprocess_exec(
                *self.command, stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            await self._request_unlocked("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "fenrys-cai", "version": "0.0.1"},
            })
            await self.notify("notifications/initialized", {})

    async def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        if not self.process or not self.process.stdin:
            raise RuntimeError("MCP process is not started")
        self.process.stdin.write((json.dumps({"jsonrpc": "2.0", "method": method,
                                               "params": params or {}}) + "\n").encode())
        await self.process.stdin.drain()

    async def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        async with self._lock:
            if method != "initialize":
                if not self.process or self.process.returncode is not None:
                    await self._start_unlocked()
            return await self._request_unlocked(method, params)

    async def _start_unlocked(self) -> None:
        self.process = await asyncio.create_subprocess_exec(
            *self.command, stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        await self._request_unlocked("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "fenrys-cai", "version": "0.0.1"},
        })
        await self.notify("notifications/initialized", {})

    async def _request_unlocked(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.process or not self.process.stdin or not self.process.stdout:
            raise RuntimeError("MCP process is not started")
        self._request_id += 1
        request_id = self._request_id
        self.process.stdin.write((json.dumps({"jsonrpc": "2.0", "id": request_id,
                                               "method": method, "params": params or {}}) + "\n").encode())
        await self.process.stdin.drain()
        while True:
            line = await asyncio.wait_for(self.process.stdout.readline(), self.startup_timeout)
            if not line:
                raise RuntimeError("MCP process closed stdout")
            message = json.loads(line.decode())
            if message.get("id") == request_id:
                if message.get("error"):
                    raise RuntimeError(str(message["error"]))
                return message

    async def list_tools(self) -> list[dict[str, Any]]:
        data = await self.request("tools/list")
        return ((data.get("result") or {}).get("tools") or [])

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        data = await self.request("tools/call", {"name": name, "arguments": arguments})
        return (data.get("result") or {})

    async def close(self) -> None:
        if self.process and self.process.returncode is None:
            self.process.terminate()
            await self.process.wait()
        self.process = None
