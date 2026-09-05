from __future__ import annotations

import ipaddress
from urllib.parse import urlparse


class ScopeChecker:
    def __init__(self, scope: dict):
        self.scope = scope

    def is_allowed(self, target: str) -> bool:
        candidates = set(self.scope.get("targets", [])) | set(self.scope.get("hostnames", [])) | set(self.scope.get("urls", []))
        if target in candidates:
            return True
        try:
            address = ipaddress.ip_address(target)
            return any(address in ipaddress.ip_network(cidr) for cidr in self.scope.get("cidrs", []))
        except ValueError:
            parsed = urlparse(target)
            host = parsed.hostname or target
            return host in candidates

    def require_allowed(self, target: str) -> None:
        if not self.is_allowed(target):
            raise PermissionError(f"target is outside configured scope: {target}")
