from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, StringConstraints
from typing import Annotated

from src.constants.workflow import Decision

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(Request):
    email: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
    password: Annotated[str, StringConstraints(min_length=1, max_length=200)]


class Import(Request):
    name: Name
    csv: Annotated[str, StringConstraints(min_length=1, max_length=1_000_000)]


class RunRequest(Request):
    dataset_id: Annotated[str, StringConstraints(min_length=36, max_length=36)]
    label: Name
    parameter: FiniteFloat


class ReviewRequest(Request):
    decision: Decision
    samples: Annotated[list[Annotated[str, StringConstraints(min_length=1, max_length=120)]], Field(max_length=500)]
    note: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=1000)]


class CalibrationReading(Request):
    room: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    shift_at: Annotated[str, StringConstraints(strip_whitespace=True, min_length=16, max_length=16)]
    old_rh: FiniteFloat = Field(ge=0, le=100)
    new_rh: FiniteFloat = Field(ge=0, le=100)


class CalibrationRequest(Request):
    dataset_id: Annotated[str, StringConstraints(min_length=36, max_length=36)]
    label: Name
    note: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=1000)]
    readings: Annotated[list[CalibrationReading], Field(min_length=1, max_length=2000)]
