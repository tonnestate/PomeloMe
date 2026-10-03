from __future__ import annotations

from dataclasses import dataclass

from .errors import AuthorizationError
from .models import AuthorityEnvelope, EffectClass


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str


class DefaultPolicyKernel:
    """Small deterministic deny-by-default semantic policy kernel.

    This is deliberately not a general policy language. Cedar/OPA can be added behind
    a policy backend later without changing the core execution semantics.
    """

    def authorize_capabilities(
        self, authority: AuthorityEnvelope, required: frozenset[str]
    ) -> PolicyDecision:
        if authority.is_expired():
            return PolicyDecision(False, "authority expired")
        missing = sorted(required.difference(authority.capabilities))
        if missing:
            return PolicyDecision(False, f"missing capabilities: {', '.join(missing)}")
        return PolicyDecision(True, "capabilities satisfied")

    def authorize_effect(
        self,
        authority: AuthorityEnvelope,
        tool: str,
        effect_class: EffectClass,
        required: frozenset[str],
    ) -> PolicyDecision:
        tool_cap = f"tool:{tool}"
        required_all = set(required)
        required_all.add(tool_cap)
        if effect_class is EffectClass.IRREVERSIBLE:
            required_all.add("effect:irreversible")
        decision = self.authorize_capabilities(authority, frozenset(required_all))
        return decision

    def require_effect(
        self,
        authority: AuthorityEnvelope,
        tool: str,
        effect_class: EffectClass,
        required: frozenset[str],
    ) -> None:
        decision = self.authorize_effect(authority, tool, effect_class, required)
        if not decision.allowed:
            raise AuthorizationError(decision.reason)
