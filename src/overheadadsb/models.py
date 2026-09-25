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
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore")
    hex: str
    type: str | None = None
    flight: str | None = None
    r: str | None = None
    t: str | None = None
    desc: str | None = None
    alt_baro: int | float | str | None = None
    alt_geom: int | float | None = None
    gs: float | None = None
    ias: int | float | None = None
    tas: int | float | None = None
    mach: float | None = None
    wd: int | float | None = None
    ws: int | float | None = None
    oat: int | float | None = None
    tat: int | float | None = None
    track: float | None = None
    track_rate: float | None = None
    roll: float | None = None
    mag_heading: float | None = None
    true_heading: float | None = None
    baro_rate: int | float | None = None
    geom_rate: int | float | None = None
    squawk: str | None = None
    emergency: str | None = None
    category: str | None = None
    nav_qnh: float | None = None
    nav_altitude_mcp: int | float | None = None
    lat: float | None = None
    lon: float | None = None
    nic: int | None = None
    rc: int | None = None
    seen_pos: float | None = None
    gpsOkBefore: float | None = None
    gpsOkLat: float | None = None
    gpsOkLon: float | None = None
    version: int | None = None
    nic_baro: int | None = None
    nac_p: int | None = None
    nac_v: int | None = None
    sil: int | None = None
    sil_type: str | None = None
    gva: int | None = None
    sda: int | None = None
    alert: int | None = None
    spi: int | None = None
    mlat: list[str] = []
    tisb: list[str] = []
    messages: int | None = None
    seen: float | None = None
    rssi: float | None = None
    dst: float | None = None
    dir: float | None = None


class ADSBFIResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore")
    ac: list[ADSBFIResponseItem]
    msg: str
    now: int
    total: int
    ctime: int
    ptime: int


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
