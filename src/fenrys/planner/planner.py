from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(slots=True)
class PlanStep:
    agent: str
    objective: str
    priority: int


def _has(text: str, pattern: str) -> bool:
    """Regex-substring dengan word boundary agar 'smb' tidak match 'dismantle'."""
    return re.search(pattern, text) is not None


class DeterministicPlanner:
    """Cheap classification before any model is consulted."""

    def classify(self, objective: str) -> str:
        text = objective.lower()
        if _has(text, r"\b(web|http|url|xss|sql)\b"):
            return "web"
        if _has(text, r"\b(binary|binaries|pwn|elf|reverse|exploit dev|rop|shellcode)\b"):
            return "pwn"
        # pcap tetap forensik; cek sebelum cabang misc/file di bawah
        if _has(text, r"\b(pcap|memory|forensic|forensics|disk|volatility|malware)\b"):
            return "forensics"
        if _has(text, r"\b(smb|rpc|netbios|nbt|share|shares|smbmap|enum4linux|active directory|adfs|kerberos|ldap)\b"):
            return "network"
        if "domain intel" in text or _has(text, r"\b(osint|username|usernames|social|twitter|linkedin|github|dox|sherlock)\b"):
            return "osint"
        if _has(text, r"\b(crypto|cipher|ciphers|encode|encoding|hash|hashes|password|crack|cracking|rsa|aes)\b"):
            return "crypto"
        if _has(text, r"\b(steg|stego|steganography|hidden|file|files|image|png|jpg|jpeg|wav|mp3|zip|carve)\b"):
            return "misc"
        if _has(text, r"\b(cve|vulnerability|vulnerabilities|exploit|cvss|nuclei)\b"):
            return "vulnintel"
        return "recon"

    def make_plan(self, objective: str) -> list[PlanStep]:
        primary = self.classify(objective)
        if primary == "recon":
            # Satu langkah reconverbatim: dua langkah (generik + verbatim)
            # membuat run_investigation membuang objective asli saat dedup.
            return [PlanStep("recon", objective, 90)]
        return [PlanStep("recon", f"Establish passive scope and surface for: {objective}", 90),
                PlanStep(primary, objective, 80)]
