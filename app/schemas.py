from typing import Literal
from pydantic import BaseModel, ConfigDict


class DeadlineTool(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Literal["deadline"]
    start: str
    days: int
    business: bool


class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str
    law: Literal["BOE-A-2015-11430", "BOE-A-1995-24292", "BOE-A-2015-11724"] | None
    tool: DeadlineTool | None


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str
    quote: str


class Draft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claims: list[Claim]
    insufficient: bool
