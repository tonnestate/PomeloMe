from __future__ import annotations

from typing import Any, Protocol

from .ir import ExecutionPlan
from .models import AuthorityEnvelope


class AuthorityProvider(Protocol):
    def get_authority(self, run_id: str) -> AuthorityEnvelope: ...


class ReceiptSink(Protocol):
    def publish(self, receipt: dict[str, Any]) -> None: ...


class ReferenceResolver(Protocol):
    def resolve(self, ref: str, fields: list[str] | None = None) -> Any: ...


class ToolRuntime(Protocol):
    def read(self, tool: str, args: dict[str, Any]) -> Any: ...


class ModelRuntime(Protocol):
    def propose_plan(self, task: str, refs: list[str]) -> ExecutionPlan: ...

    def judge(
        self,
        *,
        purpose: str,
        inputs: dict[str, Any],
        model_tier: str,
        max_output_tokens: int,
    ) -> Any: ...


class SandboxBackend(Protocol):
    def create(self, run_id: str) -> str: ...

    def exec(self, sandbox_ref: str, command: list[str]) -> tuple[int, str, str]: ...

    def terminate(self, sandbox_ref: str) -> None: ...
