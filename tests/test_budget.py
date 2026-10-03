import pytest

from pomelome import BudgetEnvelope, BudgetLedger
from pomelome.errors import BudgetExceeded


def test_child_budget_is_reserved_from_parent() -> None:
    parent = BudgetLedger(BudgetEnvelope(max_model_calls=4, max_children=2, max_cost_usd=4))
    child = parent.reserve_child(BudgetEnvelope(max_model_calls=2, max_cost_usd=1))
    assert child.envelope.max_model_calls == 2
    assert parent.usage.model_calls == 2
    assert parent.usage.cost_usd == 1


def test_child_cannot_multiply_parent_budget() -> None:
    parent = BudgetLedger(BudgetEnvelope(max_model_calls=2, max_children=2, max_cost_usd=1))
    parent.reserve_child(BudgetEnvelope(max_model_calls=2, max_cost_usd=1))
    with pytest.raises(BudgetExceeded):
        parent.reserve_child(BudgetEnvelope(max_model_calls=1, max_cost_usd=0))
