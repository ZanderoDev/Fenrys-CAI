from __future__ import annotations

import json
import re
import time
from typing import Any

import httpx

from fenrys.evidence.manager import EvidenceManager
from fenrys.models import NormalizedToolResult
from .mcp import StdioMCPClient

# ANSI escape sequences (colour/reset) that HexStrike's ModernVisualEngine injects
# into stdout. The LLM must never see these: they are pure terminal noise and
# waste context on every scan. Strip CSI + OSC + two-byte SGR sequences.
_ANSI_RE = re.compile(
    r"\x1b\[[0-9;:]*[A-Za-z]"
    r"|\x1b\][^\x07]*(?:\x07|\x1b\\)"
    r"|\x1b[()][0-9A-B]"
)

# Response keys that carry the primary text payload of a HexStrike result,
# tried in priority order. `stdout` first because execute_command returns it.
_TEXT_KEYS = ("stdout", "output", "result", "message", "analysis", "error")


def strip_ansi(text: str) -> str:
    """Remove ANSI control sequences from terminal output."""
    return _ANSI_RE.sub("", text)


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value, indent=2, default=str, ensure_ascii=False)
    return str(value)


def _truncate(text: str, limit: int = 6000) -> str:
    """Hard cap so a single tool result can never overflow the LLM context."""
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n[...truncated {len(text) - limit} chars by Fenrys...]"


def extract_output(body: dict[str, Any]) -> tuple[str, bool, int | None]:
    """Pull clean, ANSI-free text out of a HexStrike JSON response.

    Returns (text, success, exit_code). Handles three response families:
      1. execute_command style: {stdout, stderr, success, return_code}
      2. structured analyzers: {success, analysis:{...}, cve_monitoring:{...}}
      3. plain wrappers: {success, result/output/message}
    stderr is merged only when stdout is empty, so failures are never silent.
    """
    body = body or {}

    # stderr is evidence of failure; always surface it if there's no stdout.
    stdout = body.get("stdout")
    stderr = body.get("stderr")
    error = body.get("error")

    success = bool(body.get("success", True))
    exit_code = None
    for key in ("return_code", "returncode", "exit_code"):
        if body.get(key) is not None:
            exit_code = body[key]
            break
    if exit_code is not None:
        try:
            exit_code = int(exit_code)
        except (TypeError, ValueError):
            exit_code = None

    parts: list[str] = []
    if stdout not in (None, ""):
        parts.append(strip_ansi(_stringify(stdout)))
    if stderr not in (None, ""):
        parts.append("[stderr]\n" + strip_ansi(_stringify(stderr)))
    if not parts:
        # No stdout/stderr: structured result. Prefer nested analysis blocks,
        # falling back to a compact dump of the whole body (minus metadata).
        nested = None
        for key in _TEXT_KEYS:
            value = body.get(key)
            if value not in (None, ""):
                nested = value
                break
        if nested is None:
            filtered = {k: v for k, v in body.items()
                        if k not in {"timestamp", "success"}}
            nested = filtered or body
        parts.append(strip_ansi(_stringify(nested)))
    if error and error not in (None, "") and not success:
        parts.append("[error]\n" + strip_ansi(_stringify(error)))

    return _truncate("\n".join(parts).strip()), success, exit_code


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
    # NOTE: /api/tools/sherlock and /api/tools/recon-ng DO NOT EXIST on the
    # upstream server (verified 404). Route both through the generic command
    # endpoint so the OSINT agent stays functional.
    "sherlock": "/api/command",
    "recon-ng": "/api/command",

    # ─── Reporting ───
    "create_scan_summary": "/api/visual/summary-report",

    # ─── CTF Auto-Solvers (upstream /api/ctf/*) ───
    "ctf_cryptography_solver": "/api/ctf/cryptography-solver",
    "ctf_forensics_analyzer": "/api/ctf/forensics-analyzer",
    "ctf_binary_analyzer": "/api/ctf/binary-analyzer",
    "ctf_auto_solve_challenge": "/api/ctf/auto-solve-challenge",
    "ctf_suggest_tools": "/api/ctf/suggest-tools",
    "ctf_team_strategy": "/api/ctf/team-strategy",

    # ─── Intelligence Planning (upstream /api/intelligence/*) ───
    "intel_analyze_target": "/api/intelligence/analyze-target",
    "intel_select_tools": "/api/intelligence/select-tools",
    "intel_optimize_parameters": "/api/intelligence/optimize-parameters",
    "intel_create_attack_chain": "/api/intelligence/create-attack-chain",
    "intel_smart_scan": "/api/intelligence/smart-scan",
    "intel_technology_detection": "/api/intelligence/technology-detection",

    # ─── Bug Bounty Workflows (upstream /api/bugbounty/*) ───
    "bugbounty_recon": "/api/bugbounty/reconnaissance-workflow",
    "bugbounty_vuln_hunt": "/api/bugbounty/vulnerability-hunting-workflow",
    "bugbounty_business_logic": "/api/bugbounty/business-logic-workflow",
    "bugbounty_osint": "/api/bugbounty/osint-workflow",
    "bugbounty_file_upload": "/api/bugbounty/file-upload-testing",
    "bugbounty_comprehensive": "/api/bugbounty/comprehensive-assessment",
}

# Tools whose ONLY upstream capability is a raw shell command (no dedicated
# endpoint). invoke() wraps these by shell-quoting the tool's natural argument.
# Key = fenrys tool name, value = template with a {0} placeholder for the target.
_COMMAND_TOOL_TEMPLATES: dict[str, str] = {
    "sherlock": "sherlock {0}",
    "recon-ng": "recon-ng {0}",
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
                is_error = bool(result.get("isError"))
                low = output.lower()
                # MCP bridges often answer "Unknown tool" for tools they do not
                # serve without raising or setting isError. Those tools may still
                # exist on the HexStrike REST API, so fall back instead of giving up.
                if not is_error and ("unknown tool" in low or "tool not found" in low
                                     or "not registered" in low):
                    is_error = True
                if is_error:
                    raise RuntimeError(output[:200])
                self.transport = "mcp"  # transport aktual yang berhasil dipakai
                return self._normalize(tool, output, True, started, session_id)
            except Exception as exc:
                msg = str(exc).lower()
                # "Unknown tool" means this bridge doesn't serve the tool but the
                # REST API may; keep MCP alive for its own tools and fall through.
                if "unknown tool" not in msg and "tool not found" not in msg and "not registered" not in msg:
                    await self.mcp.close()
                    self.mcp = None  # fatal: jangan coba MCP lagi, pakai REST
                self.transport = "rest"

        # Fallback to REST API
        endpoint = TOOL_ENDPOINTS.get(tool)
        if not endpoint:
            error = f"Tool '{tool}' not registered in HexStrike. Available: {list(TOOL_ENDPOINTS.keys())[:5]}..."
            return self._normalize(tool, "", False, started, session_id, error=error)

        try:
            async with httpx.AsyncClient(timeout=300) as client:
                if endpoint == "/api/command":
                    # Generic shell execution, or a command-template tool
                    # (sherlock/recon-ng) that has no dedicated upstream endpoint.
                    command = arguments.get("command") or self._command_from_template(
                        tool, arguments
                    )
                    if not command:
                        return self._normalize(
                            tool, "", False, started, session_id,
                            error="command is required",
                        )
                    response = await client.post(
                        f"{self.base_url}{endpoint}", json={"command": command}
                    )
                else:
                    response = await client.post(f"{self.base_url}{endpoint}", json=arguments)
                response.raise_for_status()
                try:
                    body = response.json()
                except Exception:
                    text = (response.text or "").strip()
                    body = {"stdout": text[:4000] or "(empty non-JSON response)",
                            "success": True}

            output, success, exit_code = extract_output(body)
            # A non-2xx JSON error body may still be `success: False`; the
            # raise_for_status above already covers hard HTTP errors.
            if output == "" and success is False:
                output = body.get("error") or "(tool returned no output)"

            return self._normalize(tool, output, success, started, session_id,
                                   exit_code=exit_code)
        except httpx.HTTPStatusError as exc:
            # Extract the server's own error message when present.
            detail = ""
            try:
                detail = str(exc.response.json().get("error", ""))[:200]
            except Exception:
                detail = str(exc)[:200]
            return self._normalize(tool, "", False, started, session_id,
                                   error=f"HTTP {exc.response.status_code}: {detail}")
        except Exception as exc:
            return self._normalize(tool, "", False, started, session_id,
                                   error=f"{type(exc).__name__}: {str(exc)[:200]}")

    def _command_from_template(self, tool: str, arguments: dict[str, Any]) -> str:
        """Build a shell command for command-template tools (sherlock/recon-ng)."""
        template = _COMMAND_TOOL_TEMPLATES.get(tool)
        if not template:
            return ""
        # Sherlock wants a username; recon-ng a module or command.
        if tool == "sherlock":
            target = arguments.get("username") or arguments.get("target") or ""
            extra = arguments.get("additional_args") or ""
        else:
            target = arguments.get("command") or arguments.get("module") or ""
            extra = arguments.get("additional_args") or ""
        if not target:
            return ""
        return f"{template.format(target)} {extra}".strip()

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
