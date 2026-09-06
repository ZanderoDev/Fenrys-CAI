from __future__ import annotations

import time
from typing import Any

import httpx

from fenrys.evidence.manager import EvidenceManager
from fenrys.models import NormalizedToolResult
from .mcp import StdioMCPClient


# Hardcoded tool endpoint mapping from Fenrys tool names to HexStrike REST API
# This is the single source of truth for tool routing
TOOL_ENDPOINTS: dict[str, str] = {
    # ─── Network Scanning ───
    "nmap_scan": "/api/tools/nmap",
    "nmap_advanced_scan": "/api/tools/nmap-advanced",
    "rustscan_fast_scan": "/api/tools/rustscan",
    "masscan_high_speed": "/api/tools/masscan",
    "autorecon_comprehensive": "/api/tools/autorecon",
    "arp_scan_discovery": "/api/tools/arp-scan",
    "nbtscan_netbios": "/api/tools/nbtscan",

    # ─── Subdomain Enumeration ───
    "amass_scan": "/api/tools/amass",
    "subfinder_scan": "/api/tools/subfinder",
    "httpx_probe": "/api/tools/httpx",
    "dnsenum_scan": "/api/tools/dnsenum",
    "fierce_scan": "/api/tools/fierce",

    # ─── Web Security ───
    "katana_crawl": "/api/tools/katana",
    "ffuf_scan": "/api/tools/ffuf",
    "nuclei_scan": "/api/tools/nuclei",
    "sqlmap_scan": "/api/tools/sqlmap",
    "dalfox_xss_scan": "/api/tools/dalfox",
    "nikto_scan": "/api/tools/nikto",
    "dirsearch_scan": "/api/tools/dirsearch",
    "feroxbuster_scan": "/api/tools/feroxbuster",
    "wafw00f_scan": "/api/tools/wafw00f",
    "hakrawler_crawl": "/api/tools/hakrawler",
    "gau_discovery": "/api/tools/gau",
    "waybackurls_discovery": "/api/tools/waybackurls",
    "arjun_parameter_discovery": "/api/tools/arjun",
    "paramspider_mining": "/api/tools/paramspider",
    "dirb_scan": "/api/tools/dirb",
    "wfuzz_scan": "/api/tools/wfuzz",
    "xsser_scan": "/api/tools/xsser",
    "dotdotpwn_scan": "/api/tools/dotdotpwn",
    "jaeles_vulnerability_scan": "/api/tools/jaeles",

    # ─── Network Enumeration ───
    "smbmap_scan": "/api/tools/smbmap",
    "enum4linux_ng_advanced": "/api/tools/enum4linux-ng",
    "netexec_scan": "/api/tools/netexec",
    "rpcclient_enumeration": "/api/tools/rpcclient",
    "enum4linux_scan": "/api/tools/enum4linux",
    "responder_credential_harvest": "/api/tools/responder",

    # ─── Binary Analysis ───
    "checksec_analyze": "/api/tools/checksec",
    "gdb_analyze": "/api/tools/gdb",
    "pwntools_exploit": "/api/tools/pwntools",
    "ropper_gadget_search": "/api/tools/ropper",
    "radare2_analyze": "/api/tools/radare2",
    "objdump_analyze": "/api/tools/objdump",
    "binwalk_analyze": "/api/tools/binwalk",
    "xxd_hexdump": "/api/tools/xxd",
    "strings_extract": "/api/tools/strings",
    "ghidra_analysis": "/api/tools/ghidra",
    "angr_symbolic_execution": "/api/tools/angr",
    "ropgadget_search": "/api/tools/ropgadget",
    "one_gadget_search": "/api/tools/one-gadget",
    "libc_database_lookup": "/api/tools/libc-database",
    "pwninit_setup": "/api/tools/pwninit",

    # ─── Forensics ───
    "exiftool_extract": "/api/tools/exiftool",
    "volatility3_analyze": "/api/tools/volatility3",
    "foremost_carving": "/api/tools/foremost",
    "steghide_analysis": "/api/tools/steghide",
    "hashpump_attack": "/api/tools/hashpump",

    # ─── Password Cracking ───
    "hashcat_crack": "/api/tools/hashcat",
    "john_crack": "/api/tools/john",
    "hydra_attack": "/api/tools/hydra",

    # ─── Exploitation ───
    "metasploit_run": "/api/tools/metasploit",
    "msfvenom_generate": "/api/tools/msfvenom",

    # ─── Vulnerability Intelligence ───
    "monitor_cve_feeds": "/api/vuln-intel/cve-monitor",
    "generate_exploit_from_cve": "/api/vuln-intel/exploit-generate",
    "discover_attack_chains": "/api/vuln-intel/attack-chains",
    "correlate_threat_intelligence": "/api/vuln-intel/threat-feeds",

    # ─── Python Execution ───
    "execute_python_script": "/api/python/execute",
    "install_python_package": "/api/python/install",

    # ─── File Operations ───
    "create_file": "/api/files/create",
    "modify_file": "/api/files/modify",
    "list_files": "/api/files/list",

    # ─── General Execution ───
    "execute_command": "/api/command",

    # ─── OSINT ───
    "sherlock": "/api/tools/sherlock",

    # ─── Reporting ───
    "create_scan_summary": "/api/visual/summary-report",
}


class HexStrikeAdapter:
    """Adapter for HexStrike-AI REST server. Tools are hardcoded, no dynamic discovery."""

    def __init__(self, base_url: str, evidence: EvidenceManager | None = None,
                 mcp_command: list[str] | None = None):
        self.base_url = base_url.rstrip("/")
        self.evidence = evidence
        self.mcp = StdioMCPClient(mcp_command) if mcp_command else None
        self.transport = "rest"

    async def health(self) -> tuple[bool, str]:
        """Check HexStrike server health and tool availability."""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.base_url}/health")
                response.raise_for_status()
                body = response.json()
            tools_available = body.get("total_tools_available", 0)
            tools_total = body.get("total_tools_count", 0)
            status = body.get("status", "unknown")
            version = body.get("version", "unknown")
            return bool(status == "healthy"), f"HexStrike {version} — {tools_available}/{tools_total} tools"
        except Exception as exc:
            return False, f"HexStrike unreachable: {type(exc).__name__}"

    async def invoke(self, tool: str, arguments: dict[str, Any],
                     session_id: str | None = None) -> NormalizedToolResult:
        """Execute a tool via HexStrike REST API or MCP."""
        started = time.perf_counter()

        # Try MCP first if available
        if self.mcp:
            try:
                result = await self.mcp.call_tool(tool, arguments)
                output = result.get("content") or result
                if isinstance(output, list):
                    chunks = []
                    for item in output:
                        if isinstance(item, dict):
                            text = item.get("text")
                            if text is not None:
                                chunks.append(str(text))
                            elif item.get("data") is not None:
                                chunks.append(str(item.get("data")))
                            else:
                                chunks.append(str(item))
                        else:
                            chunks.append(str(item))
                    output = "\n".join(chunks)
                if not isinstance(output, str):
                    output = str(output)
                return self._normalize(tool, output, not bool(result.get("isError")),
                                       started, session_id)
            except Exception:
                await self.mcp.close()

        # Fallback to REST API
        endpoint = TOOL_ENDPOINTS.get(tool)
        if not endpoint:
            error = f"Tool '{tool}' not registered in HexStrike. Available: {list(TOOL_ENDPOINTS.keys())[:5]}..."
            return self._normalize(tool, "", False, started, session_id, error=error)

        try:
            async with httpx.AsyncClient(timeout=300) as client:
                if endpoint == "/api/command":
                    response = await client.post(f"{self.base_url}{endpoint}",
                                                 json={"command": arguments.get("command", "")})
                else:
                    response = await client.post(f"{self.base_url}{endpoint}", json=arguments)
                body = response.json()
                response.raise_for_status()

            output = body.get("output") or body.get("stdout") or body.get("result") or str(body)
            if not isinstance(output, str):
                output = str(output)
            success = bool(body.get("success", True))
            exit_code = body.get("returncode") or body.get("exit_code")

            return self._normalize(tool, output, success, started, session_id,
                                   exit_code=exit_code)
        except httpx.HTTPStatusError as exc:
            return self._normalize(tool, "", False, started, session_id,
                                   error=f"HTTP {exc.response.status_code}: {str(exc)[:200]}")
        except Exception as exc:
            return self._normalize(tool, "", False, started, session_id,
                                   error=f"{type(exc).__name__}: {str(exc)[:200]}")

    def _normalize(self, tool: str, output: str, success: bool, started: float,
                   session_id: str | None, exit_code: int | None = None,
                   error: str | None = None) -> NormalizedToolResult:
        """Normalize tool result with evidence tracking."""
        duration = round((time.perf_counter() - started) * 1000)
        if self.evidence:
            return self.evidence.normalize(tool, output, success, duration, session_id,
                                           exit_code=exit_code, error=error)
        return NormalizedToolResult(tool, success, duration, output,
                                    exit_code=exit_code, error=error)

    async def close(self) -> None:
        """Cleanup MCP connection if any."""
        if self.mcp:
            await self.mcp.close()
