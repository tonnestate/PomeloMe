from pathlib import Path

from pomelome import AuthorityEnvelope, BudgetEnvelope, EffectGateway, ExecutionPlan, PomeloRuntime
from pomelome.adapters.local import LocalTools, ScriptedModel
from pomelome.store import SqliteEffectStore


def test_deterministic_nodes_do_not_spend_model_calls(tmp_path: Path) -> None:
    plan = ExecutionPlan.model_validate(
        {
            "plan_id": "p",
            "nodes": [
                {"id": "r", "op": "READ", "tool": "rows", "output": "rows"},
                {
                    "id": "f",
                    "op": "FILTER",
                    "input_ref": "rows",
                    "conditions": [{"left_ref": "item.ok", "operator": "eq", "right": True}],
                    "output": "ok_rows",
                },
                {"id": "s", "op": "SELECT", "input_ref": "ok_rows", "fields": ["id"], "output": "ids"},
                {"id": "ret", "op": "RETURN", "refs": ["ids"]},
            ],
        }
    )
    tools = LocalTools({"rows": lambda _: [{"id": 1, "ok": True}, {"id": 2, "ok": False}]})
    model = ScriptedModel(judgments=[])
    runtime = PomeloRuntime(
        tools=tools,
        effects=EffectGateway(SqliteEffectStore(tmp_path / "db.sqlite"), {}),
        model=model,
    )
    authority = AuthorityEnvelope(
        authority_id="a", principal="p", capabilities=frozenset({"tool:rows"})
    )
    result = runtime.run("run", plan, authority, BudgetEnvelope(max_model_calls=0))
    assert result.returned["ids"] == [{"id": 1}]
    assert result.model_calls == 0
    assert model.calls == 0
