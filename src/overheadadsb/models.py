from datetime import datetime
from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict


class AircraftCategory(StrEnum):
    HELI = "HELI"
    PLANE = "PLANE"


class Aircraft(BaseModel):
    icao: str
    registration: str | None = None
    aircraft_type: str | None = None
    category: AircraftCategory | None = None
    owner: str | None = None
    squawk: str | None = None
    squawk_meaning: str | None = None
    distance_km: float | None = None
    times_seen: int = 0


class Meta(BaseModel):
    as_of: datetime | None = None


class APIResponse(BaseModel):
    data: Aircraft | None
    meta: Meta


class ADSBFIResponseItem(BaseModel):
    """The handful of readsb fields the poller actually uses.

    Deliberately not the full readsb schema: every extra typed field is
    another way for one odd value on one aircraft to fail validation for the
    whole response and mark the poll as failed.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore")
    hex: str
    t: str | None = None  # ICAO type designator
    r: str | None = None  # registration
    squawk: str | None = None
    dst: float | None = None  # distance from the query point, nautical miles


class ADSBFIResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore")
    # Required on purpose: a response without `ac` is an API change or an
    # error body, and must not be read as "no aircraft in range".
    ac: list[ADSBFIResponseItem]


class HEXDBResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore")
    ModeS: str | None = None
    Registration: str | None = None
    Manufacturer: str | None = None
    ICAOTypeCode: str | None = None
    Type: str | None = None
    RegisteredOwners: str | None = None
    OperatorFlagCode: str | None = None


class HealthResponse(BaseModel):
    as_of: datetime | None = None
    poll_ok: bool
    last_error: str | None = None


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    """Wire format of every error: FastAPI wraps HTTPException detail."""

    detail: ErrorDetail
