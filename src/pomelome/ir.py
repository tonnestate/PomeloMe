from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import EffectClass


class Ref(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ref: str


Value = Union[str, int, float, bool, None, list[Any], dict[str, Any], Ref]


class Condition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    left_ref: str
    operator: Literal["eq", "ne", "gt", "gte", "lt", "lte", "truthy", "falsy"]
    right: Value = None


class NodeBase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=128)


class ReadNode(NodeBase):
    op: Literal["READ"] = "READ"
    tool: str
    args: dict[str, Value] = Field(default_factory=dict)
    output: str
    required_capabilities: frozenset[str] = Field(default_factory=frozenset)


class EffectNode(NodeBase):
    op: Literal["EFFECT"] = "EFFECT"
    tool: str
    effect_class: EffectClass
    args: dict[str, Value] = Field(default_factory=dict)
    output: str | None = None
    required_capabilities: frozenset[str] = Field(default_factory=frozenset)
    idempotency_key: str | Ref | None = None


class SelectNode(NodeBase):
    op: Literal["SELECT"] = "SELECT"
    input_ref: str
    fields: list[str] = Field(min_length=1)
    output: str


class FilterNode(NodeBase):
    op: Literal["FILTER"] = "FILTER"
    input_ref: str
    conditions: list[Condition] = Field(min_length=1)
    output: str
    max_items: int = Field(default=1000, ge=1, le=100_000)


class AssertNode(NodeBase):
    op: Literal["ASSERT"] = "ASSERT"
    condition: Condition
    message: str = "assertion failed"
    on_fail: Literal["SUSPEND", "FAIL"] = "SUSPEND"


class RequestJudgmentNode(NodeBase):
    op: Literal["REQUEST_JUDGMENT"] = "REQUEST_JUDGMENT"
    purpose: str = Field(min_length=1, max_length=512)
    input_refs: list[str] = Field(default_factory=list)
    output: str
    model_tier: Literal["SMALL", "STRONG"] = "SMALL"
    max_output_tokens: int = Field(default=512, ge=1, le=16_384)


class ReturnNode(NodeBase):
    op: Literal["RETURN"] = "RETURN"
    refs: list[str] = Field(default_factory=list)


class IfTypedNode(NodeBase):
    op: Literal["IF_TYPED"] = "IF_TYPED"
    condition: Condition
    then_nodes: list["Node"] = Field(default_factory=list)
    else_nodes: list["Node"] = Field(default_factory=list)


class ParallelBoundedNode(NodeBase):
    op: Literal["PARALLEL_BOUNDED"] = "PARALLEL_BOUNDED"
    branches: list[list["Node"]] = Field(min_length=1)
    max_children: int = Field(ge=1, le=32)

    @model_validator(mode="after")
    def branch_bound(self) -> "ParallelBoundedNode":
        if len(self.branches) > self.max_children:
            raise ValueError("branch count exceeds max_children")
        return self


Node = Annotated[
    Union[
        ReadNode,
        EffectNode,
        SelectNode,
        FilterNode,
        AssertNode,
        RequestJudgmentNode,
        ReturnNode,
        IfTypedNode,
        ParallelBoundedNode,
    ],
    Field(discriminator="op"),
]


class ExecutionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["0.1"] = "0.1"
    plan_id: str = Field(min_length=1, max_length=128)
    nodes: list[Node] = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


IfTypedNode.model_rebuild()
ParallelBoundedNode.model_rebuild()
ExecutionPlan.model_rebuild()
