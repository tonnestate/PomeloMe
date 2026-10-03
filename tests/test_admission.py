from pomelome import AuthorityEnvelope, BudgetEnvelope, EffectClass, ExecutionPlan, PlanAdmitter


def test_plan_admission_requires_irreversible_capability() -> None:
    plan = ExecutionPlan.model_validate(
        {
            "plan_id": "p",
            "nodes": [
                {
                    "id": "charge",
                    "op": "EFFECT",
                    "tool": "charge_card",
                    "effect_class": EffectClass.IRREVERSIBLE,
                }
            ],
        }
    )
    authority = AuthorityEnvelope(
        authority_id="a",
        principal="p",
        capabilities=frozenset({"tool:charge_card"}),
    )
    report = PlanAdmitter().admit(plan, authority, BudgetEnvelope())
    assert not report.admitted
    assert any("effect:irreversible" in reason for reason in report.reasons)


def test_plan_admission_catches_duplicate_ids_recursively() -> None:
    plan = ExecutionPlan.model_validate(
        {
            "plan_id": "p",
            "nodes": [
                {
                    "id": "branch",
                    "op": "IF_TYPED",
                    "condition": {"left_ref": "x", "operator": "truthy"},
                    "then_nodes": [{"id": "dup", "op": "RETURN", "refs": []}],
                    "else_nodes": [{"id": "dup", "op": "RETURN", "refs": []}],
                }
            ],
        }
    )
    authority = AuthorityEnvelope(authority_id="a", principal="p")
    report = PlanAdmitter().admit(plan, authority, BudgetEnvelope())
    assert not report.admitted
