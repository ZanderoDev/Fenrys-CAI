from __future__ import annotations

import ipaddress
from urllib.parse import urlparse


class ScopeChecker:
    def __init__(self, scope: dict):
        self.scope = scope
        # Validasi CIDR di awal: abaikan entri rusak tanpa crash (fail-closed
        # untuk target, bukan untuk config).
        self._cidrs: list = []
        for cidr in self.scope.get("cidrs", []) or []:
            try:
                self._cidrs.append(ipaddress.ip_network(str(cidr).strip(), strict=False))
            except ValueError:
                continue

    @staticmethod
    def _norm(value: str) -> str:
        return str(value or "").strip().lower()

    def _candidates(self) -> set[str]:
        out: set[str] = set()
        for key in ("targets", "hostnames", "urls"):
            for item in self.scope.get(key, []) or []:
                normed = self._norm(item)
                if normed:
                    out.add(normed)
        return out

    def is_allowed(self, target: str) -> bool:
        target = self._norm(target)
        if not target:
            return False
        candidates = self._candidates()
        if target in candidates:
            return True
        # Host URL kandidat juga mengizinkan URL/path lain di host yang sama,
        # dan bare hostname kandidat mengizinkan URL di host itu.
        parsed_target = urlparse(target if "://" in target else f"//{target}")
        target_host = (parsed_target.hostname or target).lower()
        for candidate in candidates:
            parsed_cand = urlparse(candidate if "://" in candidate else f"//{candidate}")
            cand_host = (parsed_cand.hostname or candidate).lower()
            if target_host and target_host == cand_host:
                return True
        # host:port tanpa skema, mis. "10.0.0.5:445" (bukan IP murni)
        if "://" not in target:
            try:
                ipaddress.ip_address(target)
            except ValueError:
                if ":" in target and not target.startswith("["):
                    host_part = target.rsplit(":", 1)[0].strip("[]").lower()
                    if host_part in candidates or any(
                            (urlparse(c if "://" in c else f"//{c}").hostname or c).lower() == host_part
                            for c in candidates):
                        return True
                    try:
                        address = ipaddress.ip_address(host_part)
                        if any(address in cidr for cidr in self._cidrs):
                            return True
                    except ValueError:
                        pass
        try:
            address = ipaddress.ip_address(target_host if "://" in target else target)
            if any(address in cidr for cidr in self._cidrs):
                return True
        except ValueError:
            pass
        # CIDR sebagai target: diizinkan bila tercakup dalam CIDR scope
        try:
            net = ipaddress.ip_network(target, strict=False)
            if any(net.subnet_of(cidr) for cidr in self._cidrs):
                return True
        except ValueError:
            pass
        return False

    def require_allowed(self, target: str) -> None:
        if not self.is_allowed(target):
            raise PermissionError(f"target is outside configured scope: {target}")
