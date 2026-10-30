"""Pydantic schemas for User request and response models."""

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

VPA_REGEX = re.compile(r"^[a-zA-Z0-9.\-_]{2,256}@[a-zA-Z]{2,64}$")


class UserIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=100, description="User display name")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        stripped = v.strip()
        if not (1 <= len(stripped) <= 100):
            raise ValueError("Name cannot be empty or solely whitespace, length 1..100")
        return stripped


class UserOut(BaseModel):
    id: str = Field(..., description="Opaque public user ID (usr_...)")
    name: str
    created_at: datetime
    vpa_masked: str | None = None


class UserVpaIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vpa: str = Field(..., min_length=5, max_length=256, description="Virtual Payment Address")

    @field_validator("vpa")
    @classmethod
    def validate_vpa(cls, v: str) -> str:
        stripped = v.strip()
        if not VPA_REGEX.match(stripped):
            raise ValueError("Invalid VPA format. Expected format like username@handle")
        return stripped


class UserVpaOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vpa_masked: str = Field(..., description="Masked VPA")


class UserRegistrationOut(BaseModel):
    user: UserOut
    api_token: str = Field(..., description="API bearer token, shown only once")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def id(self) -> str:
        return self.user.id

    @computed_field  # type: ignore[prop-decorator]
    @property
    def name(self) -> str:
        return self.user.name

    @computed_field  # type: ignore[prop-decorator]
    @property
    def created_at(self) -> datetime:
        return self.user.created_at


class TokenRotateOut(BaseModel):
    api_token: str = Field(..., description="New API bearer token")


class UserListOut(BaseModel):
    items: list[UserOut]
    next_cursor: str | None = None
