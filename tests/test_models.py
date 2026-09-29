"""Tests for overheadadsb.models.

Mainly guards the `extra="ignore"` contract on the external API response
models -- adsb.fi and hexdb.io can add fields at any time, and if that
tolerance were ever accidentally dropped, poll_once() would start raising
ValidationErrors and marking every poll as failed.
"""

import pytest
from pydantic import ValidationError

from overheadadsb.models import (
    ADSBFIResponseItem,
    Aircraft,
    APIResponse,
    HealthResponse,
    HEXDBResponse,
)


def test_aircraft_only_icao_is_required():
    aircraft = Aircraft(icao="ABC123")

    assert aircraft.registration is None
    assert aircraft.category is None
    assert aircraft.times_seen == 0  # the field poll_once relies on defaulting cleanly


def test_aircraft_requires_icao():
    # Deliberately calls the constructor without its one required argument to
    # check Pydantic raises ValidationError at runtime -- which is exactly
    # the call a type checker is right to flag statically, since it's an
    # intentionally invalid call at the type level.
    with pytest.raises(ValidationError):
        Aircraft()  # pyright: ignore[reportCallIssue]


def test_adsbfi_item_requires_only_hex():
    item = ADSBFIResponseItem.model_validate({"hex": "ABC123"})

    assert item.hex == "ABC123"
    assert item.dst is None
    assert item.r is None  # registration
    assert item.squawk is None


def test_adsbfi_item_ignores_unknown_fields():
    item = ADSBFIResponseItem.model_validate(
        {"hex": "ABC123", "some_new_field_adsbfi_added_later": 1}
    )

    assert item.hex == "ABC123"


def test_hexdb_response_tolerates_missing_and_extra_fields():
    resp = HEXDBResponse.model_validate(
        {"RegisteredOwners": "Example Airlines", "SomeNewField": "x"}
    )

    assert resp.RegisteredOwners == "Example Airlines"
    assert resp.Registration is None


def test_api_response_allows_null_data():
    resp = APIResponse.model_validate({"data": None, "meta": {"as_of": None}})

    assert resp.data is None


def test_health_response_defaults():
    resp = HealthResponse(poll_ok=True)

    assert resp.as_of is None
    assert resp.last_error is None
