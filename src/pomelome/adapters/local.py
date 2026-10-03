from __future__ import annotations

from typing import Any, Callable

from ..ir import ExecutionPlan


class LocalTools:
    def __init__(self, readers: dict[str, Callable[[dict[str, Any]], Any]]) -> None:
        self.readers = readers

    def read(self, tool: str, args: dict[str, Any]) -> Any:
        return self.readers[tool](args)


class DictReferenceResolver:
    def __init__(self, values: dict[str, Any]) -> None:
        self.values = values

    def resolve(self, ref: str, fields: list[str] | None = None) -> Any:
        value = self.values[ref]
        if fields is not None and isinstance(value, dict):
            return {field: value.get(field) for field in fields}
        return value


class ScriptedModel:
    def __init__(self, judgments: list[Any] | None = None, plan: ExecutionPlan | None = None) -> None:
        self.judgments = list(judgments or [])
        self.plan = plan
        self.calls = 0

    def propose_plan(self, task: str, refs: list[str]) -> ExecutionPlan:
        if self.plan is None:
            raise RuntimeError("no scripted plan configured")
        self.calls += 1
        return self.plan

    def judge(self, *, purpose: str, inputs: dict[str, Any], model_tier: str, max_output_tokens: int) -> Any:
        self.calls += 1
        if not self.judgments:
            raise RuntimeError("no scripted judgment configured")
        return self.judgments.pop(0)


class MemoryReceiptSink:
    def __init__(self) -> None:
        self.receipts: list[dict[str, Any]] = []

    def publish(self, receipt: dict[str, Any]) -> None:
        self.receipts.append(dict(receipt))
