from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from .admission import PlanAdmitter
from .budget import BudgetEnvelope, BudgetLedger
from .effects import EffectGateway, EffectIntent
from .errors import ReplanRequired
from .fsm import RunState, transition_run
from .ir import (
    AssertNode,
    Condition,
    EffectNode,
    ExecutionPlan,
    FilterNode,
    IfTypedNode,
    Node,
    ParallelBoundedNode,
    ReadNode,
    Ref,
    RequestJudgmentNode,
    ReturnNode,
    SelectNode,
)
from .models import AuthorityEnvelope
from .ports import ModelRuntime, ReferenceResolver, ToolRuntime
from .zero_cost import ZeroCostGuard


@dataclass
class RunResult:
    run_id: str
    state: RunState
    outputs: dict[str, Any] = field(default_factory=dict)
    returned: dict[str, Any] = field(default_factory=dict)
    model_calls: int = 0


class PomeloRuntime:
    def __init__(
        self,
        *,
        tools: ToolRuntime,
        effects: EffectGateway,
        model: ModelRuntime | None = None,
        refs: ReferenceResolver | None = None,
        admitter: PlanAdmitter | None = None,
        zero_cost: ZeroCostGuard | None = None,
    ) -> None:
        if effects.zero_cost is not zero_cost:
            raise ValueError("zero-cost guard mismatch between runtime and gateway")
        if admitter is not None and admitter.zero_cost is not zero_cost:
            raise ValueError("zero-cost guard mismatch between runtime and admission")
        self.tools = tools
        self.effects = effects
        self.model = model
        self.refs = refs
        self.zero_cost = zero_cost
        self.admitter = admitter or PlanAdmitter(zero_cost=zero_cost)

    def run(
        self,
        run_id: str,
        plan: ExecutionPlan,
        authority: AuthorityEnvelope,
        budget: BudgetEnvelope,
    ) -> RunResult:
        report = self.admitter.admit(plan, authority, budget)
        report.require()
        state = transition_run(RunState.CREATED, RunState.AUTHORIZED)
        state = transition_run(state, RunState.QUEUED)
        state = transition_run(state, RunState.RUNNING)
        ledger = BudgetLedger(budget)
        ctx: dict[str, Any] = {}
        returned: dict[str, Any] = {}
        try:
            self._execute_nodes(run_id, plan.nodes, authority, ledger, ctx, returned)
        except ReplanRequired:
            state = transition_run(state, RunState.SUSPENDED)
            raise
        state = transition_run(state, RunState.COMPLETED)
        return RunResult(
            run_id=run_id,
            state=state,
            outputs=ctx,
            returned=returned,
            model_calls=ledger.usage.model_calls,
        )

    def _execute_nodes(
        self,
        run_id: str,
        nodes: list[Node],
        authority: AuthorityEnvelope,
        budget: BudgetLedger,
        ctx: dict[str, Any],
        returned: dict[str, Any],
    ) -> None:
        for node in nodes:
            if isinstance(node, ReadNode):
                args = self._resolve_args(node.args, ctx)
                if self.zero_cost is not None:
                    self.zero_cost.require_operation("READ", node.tool, args)
                budget.consume_read()
                ctx[node.output] = self.tools.read(node.tool, args)
            elif isinstance(node, EffectNode):
                budget.consume_effect()
                args = self._resolve_args(node.args, ctx)
                idempotency_key = self._resolve_value(node.idempotency_key, ctx)
                intent = EffectIntent(
                    run_id=run_id,
                    effect_id=f"{run_id}:{node.id}",
                    tool=node.tool,
                    effect_class=node.effect_class,
                    args=args,
                    required_capabilities=node.required_capabilities,
                    idempotency_key=str(idempotency_key) if idempotency_key is not None else None,
                )
                result = self.effects.execute(intent, authority)
                if node.output:
                    ctx[node.output] = (
                        result.observation.data if result.observation is not None else None
                    )
            elif isinstance(node, SelectNode):
                source = ctx[node.input_ref]
                if isinstance(source, dict):
                    ctx[node.output] = {field: source.get(field) for field in node.fields}
                else:
                    ctx[node.output] = [
                        {field: item.get(field) for field in node.fields} for item in source
                    ]
            elif isinstance(node, FilterNode):
                source = list(ctx[node.input_ref])[: node.max_items]
                ctx[node.output] = [item for item in source if self._matches_all(item, node.conditions, ctx)]
            elif isinstance(node, AssertNode):
                if not self._evaluate(node.condition, ctx):
                    if node.on_fail == "FAIL":
                        raise AssertionError(node.message)
                    raise ReplanRequired(f"{node.id}: {node.message}")
            elif isinstance(node, IfTypedNode):
                branch = node.then_nodes if self._evaluate(node.condition, ctx) else node.else_nodes
                self._execute_nodes(run_id, branch, authority, budget, ctx, returned)
            elif isinstance(node, ParallelBoundedNode):
                # Branches are admitted as data-independent in v0.1. Each receives a snapshot
                # and merges disjoint outputs back into the parent context.
                snapshots = [dict(ctx) for _ in node.branches]
                with ThreadPoolExecutor(max_workers=min(node.max_children, len(node.branches))) as pool:
                    futures = []
                    for branch, branch_ctx in zip(node.branches, snapshots, strict=True):
                        branch_returned: dict[str, Any] = {}
                        futures.append(
                            pool.submit(
                                self._execute_nodes,
                                run_id,
                                branch,
                                authority,
                                budget,
                                branch_ctx,
                                branch_returned,
                            )
                        )
                    for future in futures:
                        future.result()
                for branch_ctx in snapshots:
                    for key, value in branch_ctx.items():
                        if key not in ctx:
                            ctx[key] = value
                        elif ctx[key] != value:
                            raise RuntimeError(f"parallel branch wrote conflicting ref: {key}")
            elif isinstance(node, RequestJudgmentNode):
                if self.zero_cost is not None:
                    self.zero_cost.require_no_model()
                if self.model is None:
                    raise ReplanRequired(f"{node.id}: model runtime required")
                budget.consume_model_call()
                inputs = {ref: self._materialize_for_model(ref, ctx) for ref in node.input_refs}
                ctx[node.output] = self.model.judge(
                    purpose=node.purpose,
                    inputs=inputs,
                    model_tier=node.model_tier,
                    max_output_tokens=node.max_output_tokens,
                )
            elif isinstance(node, ReturnNode):
                for ref in node.refs:
                    returned[ref] = ctx.get(ref)
            else:  # pragma: no cover - defensive exhaustiveness
                raise TypeError(f"unsupported node: {node!r}")

    def _resolve_value(self, value: Any, ctx: dict[str, Any]) -> Any:
        if isinstance(value, Ref):
            return ctx[value.ref]
        if isinstance(value, dict):
            return {k: self._resolve_value(v, ctx) for k, v in value.items()}
        if isinstance(value, list):
            return [self._resolve_value(v, ctx) for v in value]
        return value

    def _resolve_args(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        return {key: self._resolve_value(value, ctx) for key, value in args.items()}

    def _materialize_for_model(self, ref: str, ctx: dict[str, Any]) -> Any:
        if ref in ctx:
            return ctx[ref]
        if self.refs is not None:
            return self.refs.resolve(ref)
        raise KeyError(ref)

    def _evaluate(self, condition: Condition, ctx: dict[str, Any], item: dict[str, Any] | None = None) -> bool:
        left = self._lookup(condition.left_ref, ctx, item)
        right = self._resolve_value(condition.right, ctx)
        op = condition.operator
        if op == "truthy":
            return bool(left)
        if op == "falsy":
            return not bool(left)
        if op == "eq":
            return left == right
        if op == "ne":
            return left != right
        if op == "gt":
            return left > right
        if op == "gte":
            return left >= right
        if op == "lt":
            return left < right
        if op == "lte":
            return left <= right
        raise ValueError(op)

    def _lookup(self, ref: str, ctx: dict[str, Any], item: dict[str, Any] | None) -> Any:
        if item is not None and ref.startswith("item."):
            value: Any = item
            for part in ref.split(".")[1:]:
                value = value[part]
            return value
        value = ctx[ref.split(".")[0]]
        for part in ref.split(".")[1:]:
            value = value[part]
        return value

    def _matches_all(self, item: dict[str, Any], conditions: list[Condition], ctx: dict[str, Any]) -> bool:
        return all(self._evaluate(condition, ctx, item) for condition in conditions)
