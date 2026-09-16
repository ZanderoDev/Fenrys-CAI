from __future__ import annotations

import asyncio
import concurrent.futures
import json
import os
import time
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from fenrys_cai.models import ToolResult, ToolSpec
from fenrys_cai.tools import ToolProvider
from fenrys_cai.security import DEFAULT_REDACTOR

Transport = Literal["stdio", "http"]


@dataclass(frozen=True)
class MCPServerConfig:
    name: str
    transport: Transport
    command: str | None = None
    args: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)
    cwd: Path | None = None
    url: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    startup_timeout: float = 15.0
    request_timeout: float = 30.0

    def validate(self) -> None:
        if self.transport == "stdio" and not self.command:
            raise ValueError("stdio MCP server requires a command")
        if self.transport == "http" and not self.url:
            raise ValueError("http MCP server requires a URL")


class MCPProviderError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class _Loop:
    def __init__(self) -> None:
        import threading
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, daemon=True, name="fenrys-mcp")
    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()
    def start(self) -> None:
        self._thread.start()
    def call(self, func, *args, timeout: float | None = None):
        future = asyncio.run_coroutine_threadsafe(func(*args), self.loop)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError as exc:
            future.cancel()
            raise TimeoutError("MCP request timed out") from exc
    def stop(self) -> None:
        self.loop.call_soon_threadsafe(self.loop.stop)
        self._thread.join(timeout=5)
        self.loop.close()


class MCPProvider(ToolProvider):
    """Generic MCP ToolProvider. Transports and schemas remain provider-internal."""
    def __init__(self, config: MCPServerConfig, *, max_output_bytes: int = 64 * 1024) -> None:
        config.validate()
        self.config = config
        self.name = config.name
        self.max_output_bytes = max_output_bytes
        self._loop = _Loop()
        self._exit_stack = AsyncExitStack()
        self._session = None
        self._started = False
        self._specs: dict[str, ToolSpec] = {}

    def _sanitize_env(self) -> dict[str, str]:
        public = DEFAULT_REDACTOR.redact_environment(dict(os.environ))
        public.update(self.config.env)
        return public

    async def _connect_async(self):
        try:
            from mcp import ClientSession, StdioServerParameters
        except ImportError as exc:
            raise MCPProviderError("unavailable_server", "The optional 'mcp' package is not installed") from exc
        if self.config.transport == "stdio":
            from mcp.client.stdio import stdio_client
            parameters = StdioServerParameters(command=self.config.command or "", args=list(self.config.args), env=self._sanitize_env(), cwd=self.config.cwd)
            read, write = await self._exit_stack.enter_async_context(stdio_client(parameters))
        else:
            import httpx
            from mcp.client.streamable_http import streamable_http_client
            client = httpx.AsyncClient(headers=self.config.headers, timeout=self.config.request_timeout)
            await self._exit_stack.enter_async_context(client)
            read, write, _ = await self._exit_stack.enter_async_context(streamable_http_client(self.config.url or "", http_client=client))
        session = ClientSession(read, write)
        await self._exit_stack.enter_async_context(session)
        await session.initialize()
        return session

    def start(self) -> None:
        if self._started:
            return
        self._loop.start()
        try:
            self._session = self._loop.call(self._connect_async, timeout=self.config.startup_timeout)
        except MCPProviderError:
            self._cleanup_after_error()
            raise
        except BaseException as exc:
            self._cleanup_after_error()
            raise MCPProviderError("startup_failure", f"MCP server {self.name!r} failed to start") from exc
        self._started = True

    def _ensure(self) -> None:
        if not self._started:
            self.start()

    @staticmethod
    def _schema(tool: Any) -> dict[str, Any]:
        schema = getattr(tool, "inputSchema", None)
        if not isinstance(schema, dict):
            raise MCPProviderError("malformed_response", f"MCP tool {getattr(tool, 'name', '<unknown>')!r} has a malformed input schema")
        return schema

    @staticmethod
    def _capabilities(schema: dict[str, Any], description: str) -> tuple[str, ...]:
        capabilities = {"mcp"}
        text = f"{description} {' '.join(schema.get('properties', {}))}".lower()
        for marker in ("host", "url", "network", "port", "scan"):
            if marker in text:
                capabilities.add("network")
                break
        if any(marker in text for marker in ("file", "path", "artifact")):
            capabilities.add("filesystem")
        return tuple(sorted(capabilities))

    def discover(self) -> list[ToolSpec]:
        try:
            self._ensure()
            assert self._session is not None
            result = self._loop.call(self._session.list_tools, timeout=self.config.request_timeout)
            specs: list[ToolSpec] = []
            seen: set[str] = set()
            for tool in result.tools:
                if tool.name in seen:
                    raise MCPProviderError("malformed_response", f"MCP server exposed duplicate tool {tool.name!r}")
                seen.add(tool.name)
                description = tool.description or tool.title or "Dynamically discovered MCP tool"
                schema = self._schema(tool)
                specs.append(ToolSpec(name=tool.name, description=description, input_schema=schema,
                    capabilities=self._capabilities(schema, description), provider=self.name,
                    execution_mode="mcp", risk="operator-controlled"))
            self._specs = {spec.name: spec for spec in specs}
            return specs
        except MCPProviderError:
            raise
        except TimeoutError as exc:
            raise MCPProviderError("timeout", f"Timed out discovering tools from MCP server {self.name!r}") from exc
        except BaseException as exc:
            message = str(exc)
            if "validation error" in message or "inputSchema" in message:
                raise MCPProviderError("malformed_response", f"MCP server {self.name!r} returned a malformed tool schema") from exc
            raise MCPProviderError("connection_failure", f"Unable to discover tools from MCP server {self.name!r}") from exc

    @staticmethod
    def _content_text(content: list[Any], limit: int) -> str:
        parts: list[str] = []
        for item in content:
            if hasattr(item, "text"):
                parts.append(str(item.text))
            elif hasattr(item, "model_dump"):
                parts.append(json.dumps(item.model_dump(), sort_keys=True, default=str))
            else:
                parts.append(str(item))
        return "\n".join(parts)[:limit]

    def invoke(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        started = time.monotonic()
        try:
            self._ensure()
            if name not in self._specs:
                discovered = {spec.name for spec in self.discover()}
                if name not in discovered:
                    return ToolResult(status="error", tool=name, error="tool_not_found", provenance={"provider": self.name, "mcp": True})
            assert self._session is not None
            result = self._loop.call(self._session.call_tool, name, arguments, timeout=self.config.request_timeout)
            text = self._content_text(list(result.content or []), self.max_output_bytes)
            duration = int((time.monotonic() - started) * 1000)
            if result.isError:
                return ToolResult(status="error", tool=name, stderr=text, duration_ms=duration, error="invocation_failure", provenance={"provider": self.name, "mcp": True})
            return ToolResult(status="success", tool=name, stdout=text, duration_ms=duration,
                provenance={"provider": self.name, "mcp": True, "structured": result.structuredContent})
        except TimeoutError:
            return ToolResult(status="timeout", tool=name, duration_ms=int((time.monotonic()-started)*1000), error="timeout", provenance={"provider": self.name, "mcp": True})
        except MCPProviderError as exc:
            return ToolResult(status="error", tool=name, duration_ms=int((time.monotonic()-started)*1000), error=exc.code, provenance={"provider": self.name, "mcp": True})
        except BaseException:
            self.close()
            return ToolResult(status="error", tool=name, duration_ms=int((time.monotonic()-started)*1000), error="transport_failure", provenance={"provider": self.name, "mcp": True})

    def _reset(self) -> None:
        try:
            self._loop.stop()
        finally:
            self._loop = _Loop()
            self._exit_stack = AsyncExitStack()
            self._started = False
            self._session = None

    def _cleanup_after_error(self) -> None:
        self._loop.stop()
        self._loop = _Loop()
        self._exit_stack = AsyncExitStack()
        self._started = False
        self._session = None

    def close(self) -> None:
        if self._started:
            try:
                self._loop.call(self._exit_stack.aclose, timeout=5)
            except BaseException:
                pass
        self._loop.stop()
        self._started = False
        self._session = None

    def __enter__(self) -> MCPProvider:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
