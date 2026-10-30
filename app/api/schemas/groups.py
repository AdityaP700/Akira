"""Pydantic schemas for Group and Membership models."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class GroupIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=100, description="Group name")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        stripped = v.strip()
        if not (1 <= len(stripped) <= 100):
            raise ValueError("Group name cannot be empty or solely whitespace, length 1..100")
        return stripped


class GroupOut(BaseModel):
    id: str = Field(..., description="Opaque public group ID (grp_...)")
    name: str
    created_at: datetime


class MemberIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(..., description="Opaque public user ID (usr_...)")

    @field_validator("user_id")
    @classmethod
    def validate_user_id(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped.startswith("usr_"):
            raise ValueError("User ID must be a valid public ID starting with 'usr_'")
        return stripped


class GroupMemberOut(BaseModel):
    group_id: str = Field(..., description="Opaque public group ID (grp_...)")
    user_id: str = Field(..., description="Opaque public user ID (usr_...)")
    name: str
    joined_at: datetime
