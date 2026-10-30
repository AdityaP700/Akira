"""Pydantic schemas for Balances and Settle-up endpoints."""

from pydantic import BaseModel, ConfigDict, Field


class UserRefOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str


class PairDebtOut(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_user: UserRefOut = Field(alias="from", serialization_alias="from")
    to: UserRefOut
    amount: str


class UserNetOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user: UserRefOut
    net: str


class GroupBalancesOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    balances: dict[str, dict[str, dict[str, str]]]
    pairs: list[PairDebtOut]
    net: list[UserNetOut]


class GroupSummaryOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str


class SingleGroupBalanceSummaryOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group: GroupSummaryOut
    balances: dict[str, dict[str, dict[str, str]]]
    pairs: list[PairDebtOut]
    net: list[UserNetOut]


class AllGroupsBalancesOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    groups: list[SingleGroupBalanceSummaryOut]


class SettleUpTransferOut(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_user: UserRefOut = Field(alias="from", serialization_alias="from")
    to: UserRefOut
    amount: str


class SettleUpOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transfers: list[SettleUpTransferOut]
    count: int
    note: str = "suggestion only; greedy, may not be the minimum possible"
