from pathlib import Path

import pytest

from pomelome import AuthorityEnvelope, EffectClass, EffectGateway
from pomelome.effects import EffectIntent, EffectObservation
from pomelome.errors import SimulatedCrash
from pomelome.fsm import EffectState
from pomelome.store import SqliteEffectStore


class IrreversibleExternalSystem:
    def __init__(self) -> None:
        self.dispatches = 0
        self.done: set[str] = set()

    def dispatch(self, intent: EffectIntent) -> EffectObservation:
        self.dispatches += 1
        self.done.add(intent.effect_id)
        return EffectObservation(success=True, external_ref=f"ext:{intent.effect_id}")

    def probe(self, intent: EffectIntent) -> EffectObservation | None:
        if intent.effect_id in self.done:
            return EffectObservation(success=True, external_ref=f"ext:{intent.effect_id}")
        return None


def test_release_gate_0_no_duplicate_irreversible_effect_after_crash(tmp_path: Path) -> None:
    store_path = tmp_path / "effect-ledger.sqlite"
    external = IrreversibleExternalSystem()
    authority = AuthorityEnvelope(
        authority_id="auth",
        principal="tester",
        capabilities=frozenset({"tool:wire_money", "effect:irreversible"}),
    )
    intent = EffectIntent(
        run_id="run-1",
        effect_id="effect-1",
        tool="wire_money",
        effect_class=EffectClass.IRREVERSIBLE,
        args={"amount": 100},
    )

    gateway_before_crash = EffectGateway(SqliteEffectStore(store_path), {"wire_money": external})
    with pytest.raises(SimulatedCrash):
        gateway_before_crash.execute(intent, authority, crash_after_dispatch=True)

    assert external.dispatches == 1
    after_crash = SqliteEffectStore(store_path).get_effect("effect-1")
    assert after_crash is not None
    assert after_crash["state"] == EffectState.DISPATCHED

    # New gateway instance represents a restarted process. It MUST probe; it MUST NOT dispatch again.
    gateway_after_restart = EffectGateway(SqliteEffectStore(store_path), {"wire_money": external})
    result = gateway_after_restart.execute(intent, authority)

    assert result.state is EffectState.RECONCILED
    assert external.dispatches == 1
    assert SqliteEffectStore(store_path).count_receipts() == 1


def test_effect_identity_collision_fails_closed(tmp_path: Path) -> None:
    store = SqliteEffectStore(tmp_path / "collision.sqlite")
    first = EffectIntent(
        run_id="run-1",
        effect_id="same-id",
        tool="wire_money",
        effect_class=EffectClass.IRREVERSIBLE,
        args={"amount": 100},
    )
    store.put_intent("run-1", "same-id", "wire_money", "IRREVERSIBLE", first.model_dump(mode="json"))
    second = first.model_copy(update={"args": {"amount": 200}})
    with pytest.raises(ValueError, match="effect identity collision"):
        store.put_intent("run-1", "same-id", "wire_money", "IRREVERSIBLE", second.model_dump(mode="json"))


def test_concurrent_duplicate_irreversible_effect_is_dispatched_once(tmp_path: Path) -> None:
    """Both callers read INTENDED before either claims the effect."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier, Lock
    from pomelome.policy import DefaultPolicyKernel

    entered = Barrier(2, timeout=10)

    class ConcurrentPolicy(DefaultPolicyKernel):
        def require_effect(self, authority, tool, effect_class, required):
            super().require_effect(authority, tool, effect_class, required)
            entered.wait()

    class CountedExternal(IrreversibleExternalSystem):
        def __init__(self):
            super().__init__()
            self.lock = Lock()

        def dispatch(self, intent):
            with self.lock:
                return super().dispatch(intent)

    store = SqliteEffectStore(tmp_path / "concurrent.sqlite")
    external = CountedExternal()
    gateway = EffectGateway(store, {"wire_money": external}, policy=ConcurrentPolicy())
    auth = AuthorityEnvelope(
        authority_id="auth", principal="tester",
        capabilities=frozenset({"tool:wire_money", "effect:irreversible"}),
    )
    intent = EffectIntent(
        run_id="run", effect_id="one-effect", tool="wire_money",
        effect_class=EffectClass.IRREVERSIBLE, args={"amount": 100},
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(gateway.execute, intent, auth)
        b = pool.submit(gateway.execute, intent, auth)
        results = (a.result(timeout=12), b.result(timeout=12))

    assert sum(r.dispatched for r in results) == 1
    assert external.dispatches == 1
    assert store.get_effect("one-effect")["dispatch_count"] == 1
    assert store.count_receipts() == 1
