from __future__ import annotations

from pathlib import Path
from typing import Callable

from .base import SpecialistDecision, SpecialistRequest
from .llm_decision import LLMSpecialistDecisionBuilder, SpecialistLLMError
from .prompted import PromptedSpecialist
from .router import SpecialistRouter

DOMAINS = ("recon", "network", "web", "api", "credentials", "pwn", "reverse", "crypto", "forensics", "privesc", "verification")


def deterministic_decision(request: SpecialistRequest, prompt: str) -> SpecialistDecision:
    """Safe offline specialist behavior used when no specialist LLM is configured."""
    capabilities = {capability for tool in request.tools for capability in tool.capabilities}
    if "terminal" in capabilities and not request.context.get("attempts"):
        return SpecialistDecision("tool", f"{request.domain} specialist requests a bounded baseline observation", "execute", {"command": "pwd", "session_id": request.context.get("session_id", "default")}, confidence=0.4, verification_needed=True)
    return SpecialistDecision("continue", f"{request.domain} specialist reviewed bounded context; no new action justified", confidence=0.5)


def build_router(prompt_root: Path, decide: Callable[[SpecialistRequest, str], SpecialistDecision] | None = None, use_llm: bool = False) -> SpecialistRouter:
    if use_llm:
        llm_builder = LLMSpecialistDecisionBuilder()
        def builder(request: SpecialistRequest, prompt: str) -> SpecialistDecision:
            try:
                return llm_builder(request, prompt)
            except SpecialistLLMError as exc:
                return SpecialistDecision("stop", f"Specialist LLM failure: {exc.code}", confidence=0.0)
    else:
        builder = decide or deterministic_decision
    return SpecialistRouter({domain: PromptedSpecialist(domain, prompt_root, builder) for domain in DOMAINS})
