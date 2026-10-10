from __future__ import annotations

from dataclasses import dataclass, field

from .budget import BudgetEnvelope
from .ir import (
    EffectNode,
    ExecutionPlan,
    IfTypedNode,
    Node,
    ParallelBoundedNode,
    ReadNode,
    RequestJudgmentNode,
)
from .models import AuthorityEnvelope
from .policy import DefaultPolicyKernel
from .zero_cost import ZeroCostGuard
from .errors import AuthorizationError


@dataclass(frozen=True)
class PlanStats:
    nodes: int = 0
    reads: int = 0
    effects: int = 0
    judgments: int = 0
    maximum_parallel_branches: int = 1


@dataclass
class AdmissionReport:
    admitted: bool
    reasons: list[str] = field(default_factory=list)
    stats: PlanStats = field(default_factory=PlanStats)

    def require(self) -> None:
        if not self.admitted:
            from .errors import AdmissionError

            raise AdmissionError("; ".join(self.reasons))


def _walk(nodes: list[Node]) -> list[Node]:
    flattened: list[Node] = []
    for node in nodes:
        flattened.append(node)
        if isinstance(node, IfTypedNode):
            flattened.extend(_walk(node.then_nodes))
            flattened.extend(_walk(node.else_nodes))
        elif isinstance(node, ParallelBoundedNode):
            for branch in node.branches:
                flattened.extend(_walk(branch))
    return flattened


class PlanAdmitter:
    def __init__(
        self, policy: DefaultPolicyKernel | None = None, zero_cost: ZeroCostGuard | None = None
    ) -> None:
        self.policy = policy or DefaultPolicyKernel()
        self.zero_cost = zero_cost

    def inspect(self, plan: ExecutionPlan) -> PlanStats:
        flat = _walk(plan.nodes)
        return PlanStats(
            nodes=len(flat),
            reads=sum(isinstance(n, ReadNode) for n in flat),
            effects=sum(isinstance(n, EffectNode) for n in flat),
            judgments=sum(isinstance(n, RequestJudgmentNode) for n in flat),
            maximum_parallel_branches=max(
                [1]
                + [
                    len(n.branches)
                    for n in flat
                    if isinstance(n, ParallelBoundedNode)
                ]
            ),
        )

    def admit(
        self, plan: ExecutionPlan, authority: AuthorityEnvelope, budget: BudgetEnvelope
    ) -> AdmissionReport:
        reasons: list[str] = []
        flat = _walk(plan.nodes)
        if self.zero_cost is not None:
            try:
                self.zero_cost.require_budget(budget)
            except AuthorizationError as exc:
                reasons.append(str(exc))
            for node in flat:
                try:
                    if isinstance(node, ReadNode):
                        self.zero_cost.require_operation("READ", node.tool, node.args)
                    elif isinstance(node, EffectNode):
                        self.zero_cost.require_operation("EFFECT", node.tool, node.args)
                    elif isinstance(node, RequestJudgmentNode):
                        self.zero_cost.require_no_model()
                except AuthorizationError as exc:
                    reasons.append(f"{node.id}: {exc}")
        ids = [node.id for node in flat]
        if len(ids) != len(set(ids)):
            reasons.append("node ids must be globally unique")

        stats = self.inspect(plan)
        if stats.reads > budget.max_reads:
            reasons.append("static read upper bound exceeds budget")
        if stats.effects > budget.max_effects:
            reasons.append("static effect upper bound exceeds budget")
        if stats.judgments > budget.max_model_calls:
            reasons.append("static judgment upper bound exceeds model-call budget")
        if stats.maximum_parallel_branches > budget.max_parallelism:
            reasons.append("parallel branch bound exceeds budget")

        for node in flat:
            if isinstance(node, ReadNode):
                required = frozenset(set(node.required_capabilities) | {f"tool:{node.tool}"})
                decision = self.policy.authorize_capabilities(authority, required)
                if not decision.allowed:
                    reasons.append(f"{node.id}: {decision.reason}")
            elif isinstance(node, EffectNode):
                decision = self.policy.authorize_effect(
                    authority, node.tool, node.effect_class, node.required_capabilities
                )
                if not decision.allowed:
                    reasons.append(f"{node.id}: {decision.reason}")

        return AdmissionReport(admitted=not reasons, reasons=reasons, stats=stats)
