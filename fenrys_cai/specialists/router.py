from __future__ import annotations

from collections.abc import Mapping

from .base import Specialist, SpecialistRequest, SpecialistResponse

_DOMAIN_SIGNALS: dict[str, tuple[str, ...]] = {
    "recon": ("recon", "discover", "enumerate", "target", "attack surface"),
    "network": ("host", "port", "service", "tcp", "udp", "smb", "ssh", "network"),
    "web": ("http", "web", "endpoint", "cookie", "login", "form", "url"),
    "api": ("api", "graphql", "rest", "swagger", "openapi", "token"),
    "credentials": ("password", "credential", "hash", "token", "secret", "login"),
    "pwn": ("pwn", "binary", "overflow", "rce", "exploit", "shellcode"),
    "reverse": ("reverse", "disassemble", "decompile", "elf", "pe", "firmware"),
    "crypto": ("crypto", "cipher", "rsa", "aes", "hash", "encoding", "jwt"),
    "forensics": ("forensic", "pcap", "memory", "disk", "artifact", "timeline"),
    "privesc": ("privilege", "privesc", "root", "sudo", "suid", "capability"),
    "verification": ("verify", "verification", "confirm", "provenance", "flag"),
}


class SpecialistRouter:
    """Data-driven specialist selector; it never maps tools or mandates phases."""
    def __init__(self, specialists: Mapping[str, Specialist], *, max_depth: int = 2) -> None:
        self.specialists = dict(specialists)
        self.max_depth = max_depth

    def select(self, request: SpecialistRequest) -> str:
        text = " ".join([
            request.objective,
            request.phase,
            str(request.context.get("findings", [])),
            str(request.context.get("hypotheses", [])),
            str(request.context.get("evidence", [])),
            " ".join(capability for tool in request.tools for capability in (*tool.capabilities, *tool.target_types)),
        ]).lower()
        scores = {domain: sum(1 for signal in signals if signal in text) for domain, signals in _DOMAIN_SIGNALS.items() if domain in self.specialists}
        selected = max(scores, key=scores.get, default="verification")
        return selected if scores.get(selected, 0) else request.domain

    def reason(self, request: SpecialistRequest) -> SpecialistResponse:
        if request.depth > self.max_depth:
            return SpecialistResponse(request.domain, __import__("fenrys_cai.specialists.base", fromlist=["SpecialistDecision"]).SpecialistDecision("stop", "Specialist depth limit reached", confidence=0.0))
        domain = self.select(request)
        specialist = self.specialists.get(domain) or self.specialists[request.domain]
        return specialist.reason(SpecialistRequest(domain, request.objective, request.scope, request.phase, request.context, request.tools, request.depth))
