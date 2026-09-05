from __future__ import annotations

import time
from typing import Any

import httpx

from fenrys.evidence.manager import EvidenceManager
from fenrys.models import NormalizedToolResult
from .mcp import StdioMCPClient


# The upstream project exposes a Flask REST API. These aliases map Fenrys'
# stable agent tool names to the upstream endpoint names without pretending
# that the upstream server implements MCP JSON-RPC at /.
TOOL_ENDPOINTS = {
    "nmap_scan": "/api/tools/nmap",
    "rustscan_fast_scan": "/api/tools/rustscan",
    "amass_scan": "/api/tools/amass",
    "httpx_probe": "/api/tools/httpx",
    "katana_crawl": "/api/tools/katana",
    "ffuf_scan": "/api/tools/ffuf",
    "nuclei_scan": "/api/tools/nuclei",
    "sqlmap_scan": "/api/tools/sqlmap",
    "dalfox_xss_scan": "/api/tools/dalfox",
    "smbmap_scan": "/api/tools/smbmap",
    "enum4linux_ng_advanced": "/api/tools/enum4linux-ng",
    "netexec_scan": "/api/tools/netexec",
    "checksec_analyze": "/api/tools/checksec",
    "gdb_analyze": "/api/tools/gdb",
    "pwntools_exploit": "/api/tools/pwntools",
    "ropper_gadget_search": "/api/tools/ropper",
    "binwalk_analyze": "/api/tools/binwalk",
    "exiftool_extract": "/api/tools/exiftool",
    "volatility3_analyze": "/api/tools/volatility",
    "zsteg": "/api/tools/zsteg",
    "sherlock": "/api/tools/sherlock",
    "theharvester": "/api/tools/theharvester",
    "spiderfoot": "/api/tools/spiderfoot",
    "searchsploit": "/api/tools/searchsploit",
}


class HexStrikeAdapter:
    """Adapter for https://github.com/0x4m4/hexstrike-ai's REST server."""

    def __init__(self, base_url: str, evidence: EvidenceManager | None = None,
                 mcp_command: list[str] | None = None):
        self.base_url = base_url.rstrip("/")
        self.evidence = evidence
        self.mcp = StdioMCPClient(mcp_command) if mcp_command else None
        self.registry: list[dict[str, Any]] | None = None
        self.transport = "unavailable"

    async def health(self) -> tuple[bool, str]:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.base_url}/health")
                response.raise_for_status()
                body = response.json()
            return bool(body.get("status") == "healthy"), (
                f"HexStrike {body.get('version', 'unknown')} — "
                f"{body.get('total_tools_available', 0)}/{body.get('total_tools_count', 0)} tools detected"
            )
        except Exception as exc:
            return False, type(exc).__name__ + ": " + str(exc)[:160]

    async def sync_registry(self, force: bool = False) -> list[dict[str, Any]]:
        """Cache tools/list from MCP; REST health remains a separate backend check."""
        if self.registry is not None and not force:
            return self.registry
        backend_status: dict[str, bool] = {}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{self.base_url}/health")
                response.raise_for_status()
                body = response.json()
            backend_status = body.get("tools_status") or {}
        except Exception:
            backend_status = {}
        if self.mcp:
            try:
                tools = await self.mcp.list_tools()
                self.registry = [
                    {"name": item.get("name", ""), "description": item.get("description", ""),
                     "mcp_registered": True,
                     "backend_registered": backend_status.get(item.get("name", ""), False)}
                    for item in tools if item.get("name")
                ]
                self.transport = "mcp"
                return self.registry
            except Exception:
                await self.mcp.close()
        self.registry = []
        self.transport = "rest-health-only"
        return self.registry

    async def invoke(self, tool: str, arguments: dict[str, Any],
                     session_id: str | None = None) -> NormalizedToolResult:
        started = time.perf_counter()
        endpoint = TOOL_ENDPOINTS.get(tool)
        if self.mcp:
            try:
                result = await self.mcp.call_tool(tool, arguments)
                output = result.get("content") or result
                if not isinstance(output, str):
                    output = str(output)
                return self._normalize(tool, output, not bool(result.get("isError")),
                                       started, session_id)
            except Exception:
                # Keep the server usable when MCP process startup fails; the
                # fallback is explicit REST, not a false MCP registration.
                await self.mcp.close()
        if not endpoint:
            error = f"HexStrike REST mapping unavailable for tool: {tool}"
            return self._normalize(tool, "", False, started, session_id, error=error)
        try:
            async with httpx.AsyncClient(timeout=300) as client:
                response = await client.post(f"{self.base_url}{endpoint}", json=arguments)
                body = response.json()
                response.raise_for_status()
            output = body.get("output") or body.get("stdout") or body.get("result") or body
            if not isinstance(output, str):
                output = str(output)
            success = bool(body.get("success", True))
            return self._normalize(tool, output, success, started, session_id,
                                   exit_code=body.get("returncode") or body.get("exit_code"))
        except Exception as exc:
            return self._normalize(tool, "", False, started, session_id,
                                   error=type(exc).__name__ + ": " + str(exc)[:180])

    def _normalize(self, tool: str, output: str, success: bool, started: float,
                   session_id: str | None, exit_code: int | None = None,
                   error: str | None = None) -> NormalizedToolResult:
        duration = round((time.perf_counter() - started) * 1000)
        if self.evidence:
            return self.evidence.normalize(tool, output, success, duration, session_id,
                                           exit_code=exit_code, error=error)
        return NormalizedToolResult(tool, success, duration, output, exit_code=exit_code, error=error)