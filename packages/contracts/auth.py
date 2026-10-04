from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr

Role = Literal["storage_admin", "storage_operator", "auditor", "analyst", "viewer"]


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: Literal["local", "ldap"]
    username: str = Field(min_length=1, max_length=64)
    password: SecretStr = Field(min_length=1, max_length=1024)


class UserResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    username: str
    roles: list[Role] = Field(min_length=1, max_length=5)
