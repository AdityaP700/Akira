"""Pydantic schemas for Expense request and response models."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ExactSplitIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=64, description="Public user ID")
    amount: str = Field(description="Owed rupee amount, formatted with up to 2 decimals")

    @field_validator("user_id", mode="before")
    @classmethod
    def strip_user_id(cls, v: str) -> str:
        if isinstance(v, str):
            v = v.strip()
            if not v:
                raise ValueError("user_id cannot be blank")
        return v

    @field_validator("amount", mode="before")
    @classmethod
    def strip_amount(cls, v: str) -> str:
        if isinstance(v, str):
            v = v.strip()
            if not v:
                raise ValueError("amount cannot be blank")
        return str(v)


class ShareWeightIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=64, description="Public user ID")
    weight: int = Field(gt=0, description="Strictly positive integer weight")

    @field_validator("user_id", mode="before")
    @classmethod
    def strip_user_id(cls, v: str) -> str:
        if isinstance(v, str):
            v = v.strip()
            if not v:
                raise ValueError("user_id cannot be blank")
        return v


class ExpenseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paid_by: str = Field(min_length=1, max_length=64, description="Public ID of paying user")
    amount: str = Field(description="Total expense amount in rupees (e.g. '1200.00')")
    description: str = Field(min_length=1, max_length=200, description="Expense description")
    split_type: Literal["EQUAL", "EXACT", "SHARES"] = Field(
        description="Split type (EQUAL, EXACT, or SHARES)"
    )
    splits: list[ExactSplitIn] | None = Field(
        default=None, description="Exact shares (required for EXACT split)"
    )
    shares: list[ShareWeightIn] | None = Field(
        default=None, description="Weighted shares (required for SHARES split)"
    )
    group_id: str | None = Field(
        default=None, max_length=64, description="Group ID for POST /expenses alias"
    )

    @field_validator("paid_by", mode="before")
    @classmethod
    def strip_paid_by(cls, v: str) -> str:
        if isinstance(v, str):
            v = v.strip()
            if not v:
                raise ValueError("paid_by cannot be blank")
        return v

    @field_validator("description", mode="before")
    @classmethod
    def strip_description(cls, v: str) -> str:
        if isinstance(v, str):
            v = v.strip()
            if not v:
                raise ValueError("description cannot be blank")
        return v

    @field_validator("amount", mode="before")
    @classmethod
    def strip_amount(cls, v: str) -> str:
        if isinstance(v, str):
            v = v.strip()
            if not v:
                raise ValueError("amount cannot be blank")
        return str(v)


class ExpenseShareOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    name: str
    amount: str


class ExpenseUserOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str


class ExpenseOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    group_id: str
    description: str
    amount: str
    paid_by: ExpenseUserOut
    split_type: str
    created_at: datetime
    shares: list[ExpenseShareOut]
    warning: str | None = None


class ExpenseItemOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    description: str
    amount: str
    paid_by: ExpenseUserOut
    split_type: str
    created_at: datetime


class ExpenseListOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ExpenseItemOut]
    next_cursor: str | None = None
