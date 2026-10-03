import json
from pathlib import Path

from pomelome.ir import ExecutionPlan


def test_exported_schema_matches_model() -> None:
    expected = ExecutionPlan.model_json_schema()
    path = Path(__file__).parents[1] / "schemas" / "execution_ir.schema.json"
    actual = json.loads(path.read_text(encoding="utf-8"))
    assert actual == expected
