"""Host-owned zero-incremental-billing gate for local-only media tools.

A zero estimate, free-tier label, or credit is never proof that execution
cannot incur a bill. The host must isolate billing identities and network egress.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .errors import AuthorizationError


_BLOCKED_KEYS = frozenset({
    "api_key", "apikey", "api_token", "access_token", "auth_token", "authorization",
    "bearer", "bearer_token", "secret", "client_secret", "password", "credential",
    "credentials", "billing", "billing_account", "payment", "payment_method",
    "credit_card", "subscription", "merchant", "endpoint", "base_url", "api_base",
    "provider", "proxy", "url", "webhook",
})


def _check_payload(value: Any, *, depth: int = 0) -> None:
    if depth > 32:
        raise AuthorizationError("ZERO_COST_DENIED: payload nesting limit")
    if isinstance(value, dict):
        if set(value) == {"ref"}:
            raise AuthorizationError("ZERO_COST_DENIED: ambiguous unresolved ref")
        for key, inner in value.items():
            if not isinstance(key, str):
                raise AuthorizationError("ZERO_COST_DENIED: invalid payload key")
            normalized = key.strip().lower().replace("-", "_")
            if normalized in _BLOCKED_KEYS or normalized.endswith(
                ("_api_key", "_secret", "_token", "_url")
            ):
                raise AuthorizationError(
                    "ZERO_COST_DENIED: credential/billing/network argument"
                )
            _check_payload(inner, depth=depth + 1)
    elif isinstance(value, (list, tuple)):
        for inner in value:
            _check_payload(inner, depth=depth + 1)
    elif isinstance(value, str):
        if "://" in value or value.lower().startswith(("data:", "mailto:")):
            raise AuthorizationError("ZERO_COST_DENIED: external/network reference")
    elif isinstance(value, (int, float, bool, type(None))):
        return
    elif hasattr(value, "ref") and isinstance(value.ref, str):
        # Pydantic IR Ref: resolved and inspected again at the real dispatch boundary.
        return
    else:
        raise AuthorizationError("ZERO_COST_DENIED: invalid payload type")


@dataclass(frozen=True)
class ZeroCostGuard:
    """Injected by the trusted host; never derived from planner/agent data.

    An explicitly audited local adapter only. No external API, free trial,
    unverified model, provider switch or paid fallback is permitted.
    """

    local_read_tools: frozenset[str] = field(default_factory=frozenset)
    local_effect_tools: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        for name in self.local_read_tools | self.local_effect_tools:
            if not isinstance(name, str) or not name.startswith("local.") or "://" in name:
                raise ValueError("invalid zero-cost local tool declaration")

    def require_budget(self, budget: Any) -> None:
        if type(budget.max_cost_usd) not in (int, float) or budget.max_cost_usd != 0:
            raise AuthorizationError("ZERO_COST_DENIED: max_cost_usd must equal 0")

    def require_operation(self, kind: str, tool: str, args: Any) -> None:
        allowed = (
            self.local_read_tools if kind == "READ"
            else self.local_effect_tools if kind == "EFFECT"
            else frozenset()
        )
        if tool not in allowed:
            raise AuthorizationError("ZERO_COST_DENIED: unapproved or external tool")
        _check_payload(args)

    def require_no_model(self) -> None:
        raise AuthorizationError("ZERO_COST_DENIED: unverified model route")

def require_mandatory_guard(authority: Any, guard: ZeroCostGuard | None) -> None:
    """Fail closed when host-minted authority mandates zero-cost execution."""
    constraints = authority.constraints
    if "zero_cost_required" not in constraints:
        return
    flag = constraints["zero_cost_required"]
    if type(flag) is not bool:
        raise AuthorizationError("ZERO_COST_DENIED: malformed authority constraint")
    if flag and guard is None:
        raise AuthorizationError("ZERO_COST_DENIED: required guard not installed")
