from __future__ import annotations

import shutil
from dataclasses import asdict, dataclass
from typing import Any

from fenrys.models import ToolSpec

AGENT_TOOL_NAMES = {
    "recon": ["nmap_scan", "rustscan_fast_scan", "amass_scan", "httpx_probe"],
    "web": ["katana_crawl", "ffuf_scan", "nuclei_scan", "sqlmap_scan", "dalfox_xss_scan"],
    "network": ["smbmap_scan", "enum4linux_ng_advanced", "netexec_scan"],
    "pwn": ["checksec_analyze", "gdb_analyze", "pwntools_exploit", "ropper_gadget_search"],
    "forensics": ["binwalk_analyze", "exiftool_extract", "volatility3_analyze", "zsteg"],
    "osint": ["amass_scan", "sherlock", "theharvester", "spiderfoot"],
    "vulnintel": ["nuclei_scan", "searchsploit", "monitor_cve_feeds"],
    "crypto": ["python", "sympy", "z3"],
    "misc": ["python", "sympy", "z3"],
}


@dataclass(slots=True)
class ToolAvailability:
    mcp_registered: bool = False
    backend_registered: bool = False
    binary_detected: bool = False


class ToolRegistry:
    def __init__(self):
        self.tools: dict[str, ToolAvailability] = {}
        self.specs: dict[str, ToolSpec] = {}

    def sync(self, tools: list[dict[str, Any]] | list[str], backend_registered: bool | None = None) -> None:
        for item in tools:
            if isinstance(item, str):
                name, description = item, "Registered security tool"
                mcp_registered = False
                item_backend = backend_registered
            else:
                name, description = item.get("name", ""), item.get("description", "")
                mcp_registered = bool(item.get("mcp_registered", False))
                item_backend = item.get("backend_registered", backend_registered)
            if not name:
                continue
            availability = self.tools.setdefault(name, ToolAvailability())
            if mcp_registered:
                availability.mcp_registered = True
            if item_backend is not None:
                availability.backend_registered = bool(item_backend)
            self.tools[name].binary_detected = bool(shutil.which(name))
            self.specs[name] = ToolSpec(name, description or "Registered security tool")

    def detect_binaries(self, names: list[str] | None = None) -> None:
        for name in names or list(self.tools):
            self.tools.setdefault(name, ToolAvailability()).binary_detected = bool(shutil.which(name))

    def profile_for(self, agent: str) -> list[ToolSpec]:
        return [self.specs[name] for name in AGENT_TOOL_NAMES.get(agent, []) if name in self.specs]

    def status(self) -> dict[str, dict[str, bool]]:
        return {name: asdict(value) for name, value in sorted(self.tools.items())}
