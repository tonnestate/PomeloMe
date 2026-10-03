from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock

from pydantic import BaseModel, Field

from .errors import BudgetExceeded


class BudgetEnvelope(BaseModel):
    max_model_calls: int = Field(default=2, ge=0)
    max_reads: int = Field(default=32, ge=0)
    max_effects: int = Field(default=8, ge=0)
    max_replans: int = Field(default=1, ge=0)
    max_children: int = Field(default=0, ge=0)
    max_parallelism: int = Field(default=4, ge=1)
    max_cost_usd: float = Field(default=1.0, ge=0.0)


@dataclass
class BudgetUsage:
    model_calls: int = 0
    reads: int = 0
    effects: int = 0
    replans: int = 0
    children: int = 0
    cost_usd: float = 0.0


@dataclass
class BudgetLedger:
    envelope: BudgetEnvelope
    usage: BudgetUsage = field(default_factory=BudgetUsage)
    _lock: RLock = field(default_factory=RLock, repr=False)

    def _check(self, field_name: str, delta: int | float, maximum: int | float) -> None:
        current = getattr(self.usage, field_name)
        if current + delta > maximum:
            raise BudgetExceeded(
                f"budget exceeded: {field_name} {current}+{delta} > {maximum}"
            )
        setattr(self.usage, field_name, current + delta)

    def consume_model_call(self, cost_usd: float = 0.0) -> None:
        with self._lock:
            self._check("model_calls", 1, self.envelope.max_model_calls)
            self._check("cost_usd", cost_usd, self.envelope.max_cost_usd)

    def consume_read(self) -> None:
        with self._lock:
            self._check("reads", 1, self.envelope.max_reads)

    def consume_effect(self) -> None:
        with self._lock:
            self._check("effects", 1, self.envelope.max_effects)

    def consume_replan(self) -> None:
        with self._lock:
            self._check("replans", 1, self.envelope.max_replans)

    def reserve_child(self, child: BudgetEnvelope) -> "BudgetLedger":
        with self._lock:
            self._check("children", 1, self.envelope.max_children)
            remaining_model = self.envelope.max_model_calls - self.usage.model_calls
            remaining_reads = self.envelope.max_reads - self.usage.reads
            remaining_effects = self.envelope.max_effects - self.usage.effects
            remaining_cost = self.envelope.max_cost_usd - self.usage.cost_usd
            if child.max_model_calls > remaining_model:
                raise BudgetExceeded("child model-call budget exceeds parent remainder")
            if child.max_reads > remaining_reads:
                raise BudgetExceeded("child read budget exceeds parent remainder")
            if child.max_effects > remaining_effects:
                raise BudgetExceeded("child effect budget exceeds parent remainder")
            if child.max_cost_usd > remaining_cost:
                raise BudgetExceeded("child cost budget exceeds parent remainder")
            # Reserve the child's full maxima up-front. Unused capacity is intentionally not
            # returned in v0.1; deterministic reservations make aggregate limits auditable.
            self.usage.model_calls += child.max_model_calls
            self.usage.reads += child.max_reads
            self.usage.effects += child.max_effects
            self.usage.cost_usd += child.max_cost_usd
            return BudgetLedger(child)
