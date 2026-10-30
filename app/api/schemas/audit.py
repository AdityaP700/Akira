"""Audit schemas for tamper-evident ledger verification."""

from pydantic import BaseModel, ConfigDict


class AuditVerifyOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valid: bool
    entries: int | None = None
    head: str | None = None
    broken_at: int | None = None
    reason: str | None = None
