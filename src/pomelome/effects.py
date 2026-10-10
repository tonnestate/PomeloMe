from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel, Field

from .errors import SimulatedCrash
from .fsm import EffectState
from .models import AuthorityEnvelope, EffectClass, ReceiptKind
from .policy import DefaultPolicyKernel
from .store import SqliteEffectStore
from .zero_cost import ZeroCostGuard


class EffectIntent(BaseModel):
    run_id: str
    effect_id: str
    tool: str
    effect_class: EffectClass
    args: dict[str, Any] = Field(default_factory=dict)
    required_capabilities: frozenset[str] = Field(default_factory=frozenset)
    idempotency_key: str | None = None


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
        zero_cost: ZeroCostGuard | None = None,
    ) -> None:
        self.store = store
        self.adapters = adapters
        self.policy = policy or DefaultPolicyKernel()
        self.zero_cost = zero_cost

    def execute(
        self,
        intent: EffectIntent,
        authority: AuthorityEnvelope,
        *,
        crash_after_dispatch: bool = False,
    ) -> EffectResult:
        # Check cost authority before persistent write, probe, recovery or dispatch.
        if self.zero_cost is not None:
            self.zero_cost.require_operation("EFFECT", intent.tool, intent.args)
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
        self.store.set_state(intent.effect_id, EffectState.AUTHORIZED)
        # Persist DISPATCHED before crossing the external boundary.
        self.store.set_state(intent.effect_id, EffectState.DISPATCHED, increment_dispatch=True)
        observation = adapter.dispatch(intent)
        if crash_after_dispatch:
            raise SimulatedCrash("fault injection: process lost after dispatch before durable observation")
        return self._commit_observation(intent, observation, dispatched=True)

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
