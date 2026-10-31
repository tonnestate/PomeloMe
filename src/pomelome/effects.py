from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

from pydantic import BaseModel, Field, field_serializer

from .errors import SimulatedCrash
from .fsm import EffectState
from .models import AuthorityEnvelope, EffectClass, ReceiptKind
from .policy import DefaultPolicyKernel
from .store import SqliteEffectStore


class EffectIntent(BaseModel):
    run_id: str
    effect_id: str
    tool: str
    effect_class: EffectClass
    args: dict[str, Any] = Field(default_factory=dict)
    required_capabilities: frozenset[str] = Field(default_factory=frozenset)
    idempotency_key: str | None = None

    @field_serializer("required_capabilities")
    def _canonical_capabilities(self, value: frozenset[str]) -> list[str]:
        """Durable identity must not depend on PYTHONHASHSEED."""
        return sorted(value)


class EffectObservation(BaseModel):
    success: bool | None
    data: Any = None
    external_ref: str | None = None
    message: str | None = None


class EffectAdapter(Protocol):
    def dispatch(self, intent: EffectIntent) -> EffectObservation: ...

    def probe(self, intent: EffectIntent) -> EffectObservation | None: ...


@dataclass
class EffectResult:
    state: EffectState
    observation: EffectObservation | None
    dispatched: bool


class EffectGateway:
    def __init__(
        self,
        store: SqliteEffectStore,
        adapters: dict[str, EffectAdapter],
        policy: DefaultPolicyKernel | None = None,
        resolution_authorizer: Callable[[str, str, str, str], bool] | None = None,
    ) -> None:
        self.store = store
        self.adapters = adapters
        self.policy = policy or DefaultPolicyKernel()
        # Trusted host must install an independently enforced owner approval
        # boundary. Supplying just a resolver name does NOT authorize release.
        self.resolution_authorizer = resolution_authorizer

    def execute(
        self,
        intent: EffectIntent,
        authority: AuthorityEnvelope,
        *,
        crash_after_dispatch: bool = False,
    ) -> EffectResult:
        self.store.put_intent(
            intent.run_id,
            intent.effect_id,
            intent.tool,
            intent.effect_class,
            intent.model_dump(mode="json"),
        )
        existing = self.store.get_effect(intent.effect_id)
        assert existing is not None
        state = EffectState(existing["state"])

        if state is EffectState.RECONCILED:
            obs = EffectObservation.model_validate(existing["observation"]) if existing["observation"] else None
            return EffectResult(state, obs, dispatched=False)
        if state in {EffectState.KNOWN_SUCCESS, EffectState.KNOWN_FAILURE}:
            obs = EffectObservation.model_validate(existing["observation"])
            self.store.reconcile(intent.effect_id)
            return EffectResult(EffectState.RECONCILED, obs, dispatched=False)
        if state in {EffectState.DISPATCHED, EffectState.UNKNOWN, EffectState.PROBING}:
            return self._recover(intent)
        if state is EffectState.WAITING_APPROVAL:
            return EffectResult(state, None, dispatched=False)

        if intent.tool not in self.adapters:
            raise KeyError(f"no effect adapter registered for {intent.tool}")
        adapter = self.adapters[intent.tool]
        self.policy.require_effect(
            authority, intent.tool, intent.effect_class, intent.required_capabilities
        )
        # A single durable transaction owns the transition to DISPATCHED.
        # Otherwise two concurrent callers can both read INTENDED, both
        # authorize and dispatch the same irreversible effect.
        if not self.store.claim_dispatch(intent.effect_id):
            current = self.store.get_effect(intent.effect_id)
            assert current is not None
            # A competing caller may still be dispatching. Never probe or
            # redispatch from this failed claim; explicit later recovery uses
            # the existing DISPATCHED -> PROBING path.
            return EffectResult(EffectState(current["state"]), None, dispatched=False)
        observation = adapter.dispatch(intent)
        if crash_after_dispatch:
            raise SimulatedCrash("fault injection: process lost after dispatch before durable observation")
        return self._commit_observation(intent, observation, dispatched=True)

    def recover(self, intent: EffectIntent) -> EffectResult:
        """Explicit observation/reconciliation of a previously claimed effect.

        It never calls dispatch and never needs current dispatch authority.
        The persisted intent identity must match exactly, including arguments.
        """
        entry = self.store.get_effect(intent.effect_id)
        if entry is None or self.store.canonical_intent(entry["intent"]) != self.store.canonical_intent(intent.model_dump(mode="json")):
            raise ValueError("EFFECT_NOT_FOUND_OR_IDENTITY_MISMATCH")
        state = EffectState(entry["state"])
        if state in (EffectState.INTENDED, EffectState.AUTHORIZED):
            raise ValueError("EFFECT_NOT_DISPATCHED")
        if state is EffectState.RECONCILED:
            obs = (EffectObservation.model_validate(entry["observation"])
                   if entry["observation"] is not None else None)
            return EffectResult(state, obs, dispatched=False)
        if state in (EffectState.KNOWN_SUCCESS, EffectState.KNOWN_FAILURE):
            obs = EffectObservation.model_validate(entry["observation"])
            self.store.reconcile(intent.effect_id)
            return EffectResult(EffectState.RECONCILED, obs, dispatched=False)
        if state is EffectState.WAITING_APPROVAL:
            return EffectResult(state, None, dispatched=False)
        return self._recover(intent)

    def resolve_waiting(self, effect_id: str, outcome: str, *,
                        resolver: str, evidence_ref: str) -> EffectResult:
        """Host-authorized settlement; never invokes effect adapters.

        The owner may attest success, failure, or UNKNOWN_CLOSED. The final
        option permits organizational continuation without pretending an
        uncertain effect failed or succeeded.
        """
        if outcome not in ("CONFIRMED_SUCCESS", "CONFIRMED_FAILURE", "UNKNOWN_CLOSED"):
            raise ValueError("INVALID_RESOLUTION_OUTCOME")
        if not isinstance(resolver, str) or not resolver.strip():
            raise ValueError("RESOLVER_REQUIRED")
        if not isinstance(evidence_ref, str) or not evidence_ref.strip():
            raise ValueError("RESOLUTION_EVIDENCE_REQUIRED")
        if self.resolution_authorizer is None or self.resolution_authorizer(
            effect_id, outcome, resolver.strip(), evidence_ref.strip()
        ) is not True:
            from .errors import AuthorizationError
            raise AuthorizationError("HOST_EFFECT_RESOLUTION_AUTHORITY_REQUIRED")
        observation = self.store.resolve_waiting(
            effect_id, outcome=outcome, resolver=resolver, evidence_ref=evidence_ref
        )
        return EffectResult(
            EffectState.RECONCILED,
            EffectObservation.model_validate(observation),
            dispatched=False,
        )

    def _recover(self, intent: EffectIntent) -> EffectResult:
        adapter = self.adapters[intent.tool]
        self.store.set_state(intent.effect_id, EffectState.PROBING)
        observation = adapter.probe(intent)
        if observation is None or observation.success is None:
            self.store.set_state(intent.effect_id, EffectState.WAITING_APPROVAL)
            return EffectResult(EffectState.WAITING_APPROVAL, observation, dispatched=False)
        return self._commit_observation(intent, observation, dispatched=False)

    def _commit_observation(
        self, intent: EffectIntent, observation: EffectObservation, *, dispatched: bool
    ) -> EffectResult:
        state = EffectState.KNOWN_SUCCESS if observation.success else EffectState.KNOWN_FAILURE
        receipt_id = f"effect:{intent.effect_id}:observation"
        receipt = {
            "kind": ReceiptKind.EFFECT_OBSERVATION,
            "run_id": intent.run_id,
            "effect_id": intent.effect_id,
            "effect_class": intent.effect_class,
            "tool": intent.tool,
            "success": observation.success,
            "external_ref": observation.external_ref,
        }
        self.store.commit_observation_and_receipt(
            intent.effect_id,
            state,
            observation.model_dump(mode="json"),
            receipt_id,
            receipt,
        )
        self.store.reconcile(intent.effect_id)
        return EffectResult(EffectState.RECONCILED, observation, dispatched=dispatched)
