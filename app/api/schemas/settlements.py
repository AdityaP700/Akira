"""Pydantic schemas for Settlement requests and responses."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.schemas.balances import UserRefOut


class SettlementIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_user: str = Field(min_length=1, max_length=64, description="Debtor user public ID")
    to_user: str = Field(min_length=1, max_length=64, description="Creditor user public ID")
    amount: str = Field(description="Settlement rupee amount, formatted with up to 2 decimals")
    method: Literal["CASH", "OTHER"] = Field(
        default="OTHER", description="Payment method: CASH or OTHER"
    )

    @field_validator("from_user", mode="before")
    @classmethod
    def strip_from_user(cls, v: str) -> str:
        if isinstance(v, str):
            v = v.strip()
            if not v:
                raise ValueError("from_user cannot be blank")
        return v

    @field_validator("to_user", mode="before")
    @classmethod
    def strip_to_user(cls, v: str) -> str:
        if isinstance(v, str):
            v = v.strip()
            if not v:
                raise ValueError("to_user cannot be blank")
        return v

    @field_validator("amount", mode="before")
    @classmethod
    def strip_amount(cls, v: str) -> str:
        if isinstance(v, str):
            v = v.strip()
            if not v:
                raise ValueError("amount cannot be blank")
        return str(v)


class SettlementOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    group_id: str
    from_user: UserRefOut
    to_user: UserRefOut
    amount: str
    status: str
    method: str
    created_at: datetime


class SettlementListOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[SettlementOut]
    next_cursor: str | None = None
