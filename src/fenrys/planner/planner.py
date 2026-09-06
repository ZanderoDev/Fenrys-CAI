from __future__ import annotations

from dataclasses import dataclass

from fenrys.agents import AGENTS


@dataclass(slots=True)
class PlanStep:
    agent: str
    objective: str
    priority: int


class DeterministicPlanner:
    """Cheap classification before any model is consulted."""

    def classify(self, objective: str) -> str:
        text = objective.lower()
        if any(word in text for word in ("web", "http", "url", "xss", "sql")):
            return "web"
        if any(word in text for word in ("binary", "pwn", "elf", "reverse")):
            return "pwn"
        if any(word in text for word in ("pcap", "memory", "forensic", "disk")):
            return "forensics"
        if any(word in text for word in ("cve", "vulnerability", "exploit")):
            return "vulnintel"
        if any(word in text for word in ("crypto", "cipher", "encode")):
            return "crypto"
        return "recon"

    def make_plan(self, objective: str) -> list[PlanStep]:
        primary = self.classify(objective)
        return [PlanStep("recon", f"Establish passive scope and surface for: {objective}", 90),
                PlanStep(primary, objective, 80)]
