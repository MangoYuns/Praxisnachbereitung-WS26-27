from datetime import datetime
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DeviceCreate(InputModel):
    serial_number: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    device_type_id: int = Field(gt=0)
    location_id: int = Field(gt=0)
    status: Literal["ready", "maintenance", "retired"] = "ready"
    note: str | None = None


class Device(DeviceCreate):
    device_id: int


class AssignmentCreate(InputModel):
    device_id: int = Field(gt=0)
    person_id: int = Field(gt=0)
    issued_at: AwareDatetime | None = None


class AssignmentReturn(InputModel):
    returned_at: AwareDatetime | None = None


class Assignment(BaseModel):
    assignment_id: int
    device_id: int
    person_id: int
    issued_at: datetime
    returned_at: datetime | None
