from pathlib import Path
from tempfile import TemporaryDirectory

from pomelome import AuthorityEnvelope, BudgetEnvelope, EffectClass, EffectGateway, ExecutionPlan, PomeloRuntime
from pomelome.adapters.local import LocalTools, ScriptedModel
from pomelome.effects import EffectIntent, EffectObservation
from pomelome.store import SqliteEffectStore


class ReminderAdapter:
    def dispatch(self, intent: EffectIntent) -> EffectObservation:
        return EffectObservation(success=True, data={"sent": True}, external_ref="reminder-42")

    def probe(self, intent: EffectIntent) -> EffectObservation | None:
        return EffectObservation(success=True, data={"sent": True}, external_ref="reminder-42")


plan = ExecutionPlan.model_validate(
    {
        "plan_id": "overdue-reminders",
        "nodes": [
            {
                "id": "read",
                "op": "READ",
                "tool": "list_invoices",
                "output": "invoices",
            },
            {
                "id": "filter",
                "op": "FILTER",
                "input_ref": "invoices",
                "conditions": [{"left_ref": "item.overdue", "operator": "eq", "right": True}],
                "output": "overdue",
            },
            {
                "id": "judge",
                "op": "REQUEST_JUDGMENT",
                "purpose": "Choose whether the overdue set warrants one reminder batch.",
                "input_refs": ["overdue"],
                "output": "decision",
                "model_tier": "SMALL",
            },
            {"id": "ret", "op": "RETURN", "refs": ["overdue", "decision"]},
        ],
    }
)

with TemporaryDirectory() as tmp:
    store = SqliteEffectStore(Path(tmp) / "effects.db")
    gateway = EffectGateway(store, {"send_reminder": ReminderAdapter()})
    tools = LocalTools({"list_invoices": lambda _: [{"id": 1, "overdue": True}, {"id": 2, "overdue": False}]})
    model = ScriptedModel(judgments=[{"send": True}])
    runtime = PomeloRuntime(tools=tools, effects=gateway, model=model)
    authority = AuthorityEnvelope(
        authority_id="demo",
        principal="local",
        capabilities=frozenset({"tool:list_invoices", "tool:send_reminder"}),
    )
    result = runtime.run("run-1", plan, authority, BudgetEnvelope(max_model_calls=1))
    print(result.returned)
    print("model_calls=", result.model_calls)
