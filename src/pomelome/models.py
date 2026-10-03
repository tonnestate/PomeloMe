from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class EffectClass(StrEnum):
    READ = "READ"
    IDEMPOTENT_WRITE = "IDEMPOTENT_WRITE"
    COMPENSATABLE = "COMPENSATABLE"
    IRREVERSIBLE = "IRREVERSIBLE"


class ReceiptKind(StrEnum):
    EFFECT_OBSERVATION = "EFFECT_OBSERVATION"
    EXECUTION_RECEIPT = "EXECUTION_RECEIPT"
    ARTIFACT_RECEIPT = "ARTIFACT_RECEIPT"
    TERMINAL_RECEIPT = "TERMINAL_RECEIPT"


class AuthorityEnvelope(BaseModel):
    authority_id: str
    principal: str
    capabilities: frozenset[str] = Field(default_factory=frozenset)
    expires_at: datetime | None = None
    constraints: dict[str, Any] = Field(default_factory=dict)

    @field_validator("expires_at")
    @classmethod
    def ensure_tz(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("expires_at must be timezone-aware")
        return value

    def is_expired(self, now: datetime | None = None) -> bool:
        if self.expires_at is None:
            return False
        now = now or datetime.now(timezone.utc)
        return now >= self.expires_at
