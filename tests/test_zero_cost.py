"""Zero-cost policy and integration tests: no external provider required."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from pomelome import (
    AuthorityEnvelope, BudgetEnvelope, EffectClass, EffectGateway, ExecutionPlan,
    PlanAdmitter, PomeloRuntime, ZeroCostGuard,
)
from pomelome.adapters.local import LocalTools, ScriptedModel
from pomelome.effects import EffectIntent, EffectObservation
from pomelome.errors import AdmissionError, AuthorizationError
from pomelome.ir import Ref
from pomelome.store import SqliteEffectStore


@pytest.fixture
def guard() -> ZeroCostGuard:
    return ZeroCostGuard(
        local_read_tools=frozenset({"local.media.inspect"}),
        local_effect_tools=frozenset({"local.media.render"}),
    )


@pytest.fixture
def authority() -> AuthorityEnvelope:
    return AuthorityEnvelope(
        authority_id="guarded", principal="test",
        capabilities=frozenset({
            "tool:local.media.inspect", "tool:local.media.render",
            "tool:google.flow",
        }),
    )


def plan(*nodes: dict) -> ExecutionPlan:
    return ExecutionPlan.model_validate({"plan_id": "media", "nodes": list(nodes)})


def effect(tool: str, args: dict | None = None) -> dict:
    return {
        "id": "render", "op": "EFFECT", "tool": tool,
        "effect_class": EffectClass.IDEMPOTENT_WRITE, "args": args or {},
    }


class CountingAdapter:
    def __init__(self) -> None:
        self.calls = 0

    def dispatch(self, intent: EffectIntent) -> EffectObservation:
        self.calls += 1
        return EffectObservation(success=True, data={"ok": True})

    def probe(self, intent: EffectIntent) -> EffectObservation | None:
        self.calls += 1
        return None


def gateway(tmp_path: Path, guard: ZeroCostGuard, adapter=None) -> EffectGateway:
    adapters = {"local.media.render": adapter} if adapter else {}
    return EffectGateway(SqliteEffectStore(tmp_path / "db.sqlite"), adapters, zero_cost=guard)


@pytest.mark.parametrize("amount", [1.0, 0.00001, float("nan"), -1.0, None])
def test_unknown_or_nonzero_budget_denied(guard, amount):
    with pytest.raises(AuthorizationError, match="max_cost_usd"):
        guard.require_budget(SimpleNamespace(max_cost_usd=amount))


def test_zero_budget_allowed(guard):
    guard.require_budget(BudgetEnvelope(max_cost_usd=0))


def test_allowlisted_local_operation(guard):
    guard.require_operation("EFFECT", "local.media.render", {"file": "/local/in.png"})


@pytest.mark.parametrize("tool", ["google.flow", "free-tier", "other"])
def test_unapproved_provider_denied(guard, tool):
    with pytest.raises(AuthorizationError, match="unapproved"):
        guard.require_operation("EFFECT", tool, {"price": 0})


def test_read_not_implicitly_free(guard):
    with pytest.raises(AuthorizationError):
        guard.require_operation("READ", "remote.catalog", {})


def test_wrong_operation_kind_denied(guard):
    with pytest.raises(AuthorizationError):
        guard.require_operation("READ", "local.media.render", {})


@pytest.mark.parametrize("args", [
    {"api_key": "foo"}, {"billing_account": "x"},
    {"x": [{"access-token": "foo"}]}, {"endpoint": "local"},
    {"payload": "https://example.org"}, {"file": "gs://bucket/key"},
    {"url": "file:///tmp"}, {"nested": {"my_api_key": "foo"}}, {"proxy": "x"},
    {"ref": "unresolved"},
])
def test_network_billing_payload_denied(guard, args):
    with pytest.raises(AuthorizationError, match="ZERO_COST_DENIED"):
        guard.require_operation("EFFECT", "local.media.render", args)


def test_deep_payload_denied(guard):
    x = {"x": 1}
    for _ in range(35):
        x = {"x": x}
    with pytest.raises(AuthorizationError, match="nesting"):
        guard.require_operation("EFFECT", "local.media.render", x)


def test_bad_operator_tool_name_denied():
    with pytest.raises(ValueError):
        ZeroCostGuard(local_effect_tools=frozenset({"google.flow"}))


def test_plan_denies_paid_operation_and_default_budget(guard, authority):
    rejected = PlanAdmitter(zero_cost=guard).admit(
        plan(effect("google.flow")), authority, BudgetEnvelope(max_cost_usd=0)
    )
    assert not rejected.admitted
    assert any("ZERO_COST_DENIED" in r for r in rejected.reasons)
    rejected_budget = PlanAdmitter(zero_cost=guard).admit(
        plan(effect("local.media.render")), authority, BudgetEnvelope()
    )
    assert not rejected_budget.admitted


def test_nested_branch_cannot_hide_model_call(guard, authority):
    p = plan({
        "id": "branch", "op": "IF_TYPED",
        "condition": {"left_ref": "x", "operator": "truthy"},
        "then_nodes": [{
            "id": "judge", "op": "REQUEST_JUDGMENT",
            "purpose": "fallback", "output": "out",
        }],
        "else_nodes": [{"id": "done", "op": "RETURN", "refs": []}],
    })
    report = PlanAdmitter(zero_cost=guard).admit(p, authority, BudgetEnvelope(max_cost_usd=0))
    assert not report.admitted
    assert any("unverified model route" in x for x in report.reasons)


def test_direct_gateway_denies_without_persist_or_dispatch(tmp_path, guard, authority):
    adapter = CountingAdapter()
    eg = gateway(tmp_path, guard, adapter)
    intent = EffectIntent(
        run_id="r", effect_id="e", tool="google.flow",
        effect_class=EffectClass.IDEMPOTENT_WRITE,
    )
    with pytest.raises(AuthorizationError, match="ZERO_COST_DENIED"):
        eg.execute(intent, authority)
    assert adapter.calls == 0
    assert eg.store.get_effect("e") is None


def test_direct_gateway_denies_secret(tmp_path, guard, authority):
    adapter = CountingAdapter()
    eg = gateway(tmp_path, guard, adapter)
    intent = EffectIntent(
        run_id="r", effect_id="e", tool="local.media.render",
        effect_class=EffectClass.IDEMPOTENT_WRITE,
        args={"api_key": "hidden"},
    )
    with pytest.raises(AuthorizationError):
        eg.execute(intent, authority)
    assert adapter.calls == 0


def test_guard_mismatch_denied(tmp_path, guard):
    eg = gateway(tmp_path, guard)
    with pytest.raises(ValueError, match="mismatch"):
        PomeloRuntime(tools=LocalTools({}), effects=eg)
    with pytest.raises(ValueError, match="mismatch"):
        PomeloRuntime(tools=LocalTools({}), effects=eg, zero_cost=ZeroCostGuard())


def test_local_read_allowed_and_not_model_billed(tmp_path, guard, authority):
    calls = []
    tools = LocalTools({
        "local.media.inspect": lambda args: calls.append(args) or {"ok": True}
    })
    rt = PomeloRuntime(tools=tools, effects=gateway(tmp_path, guard), zero_cost=guard)
    p = plan(
        {"id": "r", "op": "READ", "tool": "local.media.inspect",
         "args": {"file": "/local/in.png"}, "output": "result"},
        {"id": "ret", "op": "RETURN", "refs": ["result"]},
    )
    out = rt.run("run", p, authority, BudgetEnvelope(max_cost_usd=0))
    assert out.returned["result"] == {"ok": True}
    assert out.model_calls == 0
    assert len(calls) == 1


def test_runtime_denies_remote_read_without_call(tmp_path, guard, authority):
    calls = []
    rt = PomeloRuntime(
        tools=LocalTools({"remote.catalog": lambda args: calls.append(args)}),
        effects=gateway(tmp_path, guard), zero_cost=guard,
    )
    with pytest.raises(AdmissionError, match="ZERO_COST_DENIED"):
        rt.run(
            "run", plan({"id": "read", "op": "READ", "tool": "remote.catalog", "output": "x"}),
            authority, BudgetEnvelope(max_cost_usd=0),
        )
    assert not calls


def test_dynamic_ref_denies_credential_before_effect(tmp_path, guard, authority):
    adapter = CountingAdapter()
    rt = PomeloRuntime(
        tools=LocalTools({"local.media.inspect": lambda _: {"api_key": "hidden"}}),
        effects=gateway(tmp_path, guard, adapter), zero_cost=guard,
    )
    p = plan(
        {"id": "read", "op": "READ", "tool": "local.media.inspect", "output": "data"},
        effect("local.media.render"),
    )
    # The in-memory IR Ref is distinct from an unvalidated serialized dict.
    p.nodes[1].args["inputs"] = Ref(ref="data")
    with pytest.raises(AuthorizationError, match="ZERO_COST_DENIED"):
        rt.run("run", p, authority, BudgetEnvelope(max_cost_usd=0))
    assert adapter.calls == 0


def test_unverified_model_cannot_be_fallback(tmp_path, guard, authority):
    model = ScriptedModel(judgments=["fallback"])
    rt = PomeloRuntime(
        tools=LocalTools({}), effects=gateway(tmp_path, guard),
        model=model, zero_cost=guard,
    )
    p = plan({"id": "model", "op": "REQUEST_JUDGMENT",
              "purpose": "fallback", "output": "result"})
    with pytest.raises(AdmissionError, match="ZERO_COST_DENIED"):
        rt.run("run", p, authority, BudgetEnvelope(max_cost_usd=0))
    assert model.calls == 0


def test_local_effect_still_executes(tmp_path, guard, authority):
    adapter = CountingAdapter()
    rt = PomeloRuntime(
        tools=LocalTools({}), effects=gateway(tmp_path, guard, adapter), zero_cost=guard
    )
    out = rt.run("run", plan(effect("local.media.render")),
                 authority, BudgetEnvelope(max_cost_usd=0))
    assert adapter.calls == 1
    assert out.model_calls == 0

def test_host_mandate_denies_unwired_plan(guard, authority):
    authority.constraints["zero_cost_required"] = True
    p = plan(effect("local.media.render"))
    report = PlanAdmitter().admit(p, authority, BudgetEnvelope(max_cost_usd=0))
    assert not report.admitted
    assert any("required guard not installed" in r for r in report.reasons)


def test_host_mandate_denies_unwired_direct_gateway(tmp_path, authority):
    authority.constraints["zero_cost_required"] = True
    adapter = CountingAdapter()
    eg = EffectGateway(
        SqliteEffectStore(tmp_path / "unguarded.sqlite"),
        {"local.media.render": adapter},
    )
    intent = EffectIntent(
        run_id="r", effect_id="e", tool="local.media.render",
        effect_class=EffectClass.IDEMPOTENT_WRITE,
    )
    with pytest.raises(AuthorizationError, match="required guard not installed"):
        eg.execute(intent, authority)
    assert adapter.calls == 0
    assert eg.store.get_effect("e") is None


def test_malformed_mandatory_constraint_denied(guard, authority):
    authority.constraints["zero_cost_required"] = "false"
    report = PlanAdmitter(zero_cost=guard).admit(
        plan(effect("local.media.render")), authority, BudgetEnvelope(max_cost_usd=0)
    )
    assert not report.admitted
    assert any("malformed authority constraint" in r for r in report.reasons)
