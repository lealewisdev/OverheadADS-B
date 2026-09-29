"""Tests for the FastAPI routes in overheadadsb.main.

These construct the ASGI app directly via httpx's ASGITransport, without
entering the app's lifespan context -- so `poll_cache`'s real background
poll loop never starts, and no test here touches the network on its own.
`poll_cache` (the app's singleton) is monkeypatched per test instead.
"""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import httpx
import pytest
import respx
from httpx import ASGITransport, AsyncClient

from overheadadsb import config, poller
from overheadadsb.main import app
from overheadadsb.models import Aircraft, AircraftCategory

AIRCRAFT = Aircraft(
    icao="3C6444",
    registration="D-ABCD",
    aircraft_type="A320",
    category=AircraftCategory.PLANE,
    owner="Example Airlines",
    squawk="1234",
    squawk_meaning=None,
    distance_km=6.3,
    times_seen=3,
)


@pytest.fixture
def client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# -- /api/v1/overhead ---------------------------------------------------


async def test_overhead_returns_snapshot(client, monkeypatch):
    as_of = datetime(2026, 1, 1, tzinfo=UTC)
    monkeypatch.setattr(
        poller.poll_cache, "snapshot", AsyncMock(return_value=(AIRCRAFT, as_of))
    )

    response = await client.get("/api/v1/overhead")

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["icao"] == "3C6444"
    assert body["meta"]["as_of"] is not None


async def test_overhead_returns_null_data_when_nothing_in_range(client, monkeypatch):
    monkeypatch.setattr(
        poller.poll_cache, "snapshot", AsyncMock(return_value=(None, None))
    )

    response = await client.get("/api/v1/overhead")

    assert response.status_code == 200
    assert response.json() == {"data": None, "meta": {"as_of": None}}


# -- /health --------------------------------------------------------------


async def test_health_ok(client, monkeypatch):
    as_of = datetime(2026, 1, 1, tzinfo=UTC)
    monkeypatch.setattr(
        poller.poll_cache, "health", AsyncMock(return_value=(as_of, True, None))
    )

    response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["poll_ok"] is True
    assert body["as_of"] is not None
    assert body["last_error"] is None


async def test_health_unhealthy_returns_503(client, monkeypatch):
    monkeypatch.setattr(
        poller.poll_cache,
        "health",
        AsyncMock(return_value=(None, False, "adsb.fi unreachable")),
    )

    response = await client.get("/health")

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["code"] == "poller_unhealthy"
    assert detail["message"] == "adsb.fi unreachable"


# -- /api/v1/overhead/FR24 -------------------------------------------------


async def test_fr24_no_aircraft_returns_404(client, monkeypatch):
    monkeypatch.setattr(
        poller.poll_cache, "snapshot", AsyncMock(return_value=(None, None))
    )

    response = await client.get("/api/v1/overhead/FR24")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "no_aircraft"


async def test_fr24_no_registration_returns_404(client, monkeypatch):
    aircraft = AIRCRAFT.model_copy(update={"registration": None})
    monkeypatch.setattr(
        poller.poll_cache, "snapshot", AsyncMock(return_value=(aircraft, None))
    )

    response = await client.get("/api/v1/overhead/FR24")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "no_registration"


@respx.mock
async def test_fr24_redirects_when_entry_exists(client, monkeypatch):
    monkeypatch.setattr(
        poller.poll_cache, "snapshot", AsyncMock(return_value=(AIRCRAFT, None))
    )
    entry_url = f"{config.FR24_URL}/d-abcd/abc123"
    respx.get(f"{config.FR24_URL}/D-ABCD").mock(
        return_value=httpx.Response(302, headers={"location": entry_url})
    )
    respx.get(entry_url).mock(return_value=httpx.Response(200))

    response = await client.get("/api/v1/overhead/FR24", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == entry_url


@respx.mock
async def test_fr24_no_entry_returns_404_with_registration_in_message(
    client, monkeypatch
):
    """Regression test for the missing f-string prefix: the message must
    contain the actual registration, not the literal text
    '{overhead.registration}'."""
    monkeypatch.setattr(
        poller.poll_cache, "snapshot", AsyncMock(return_value=(AIRCRAFT, None))
    )
    respx.get(f"{config.FR24_URL}/D-ABCD").mock(
        return_value=httpx.Response(302, headers={"location": config.FR24_URL})
    )
    respx.get(config.FR24_URL).mock(return_value=httpx.Response(200))

    response = await client.get("/api/v1/overhead/FR24")

    assert response.status_code == 404
    detail = response.json()["detail"]
    assert detail["code"] == "no_flightradar24_entry"
    assert "D-ABCD" in detail["message"]
    assert "{overhead.registration}" not in detail["message"]


@respx.mock
async def test_fr24_unreachable_returns_502(client, monkeypatch):
    monkeypatch.setattr(
        poller.poll_cache, "snapshot", AsyncMock(return_value=(AIRCRAFT, None))
    )
    respx.get(f"{config.FR24_URL}/D-ABCD").mock(side_effect=httpx.ConnectError("boom"))

    response = await client.get("/api/v1/overhead/FR24")

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "flightradar24_unreachable"


# -- /api/v1/example --------------------------------------------------------
#
# The route is actually named /api/v1/example (main.py), not
# /api/v1/rainmetertest -- the old test here asserted on that nonexistent
# path and was silently passing... no, failing: it got a 404 and the
# assertion on status_code == 200 never held. Fixed to hit the real route
# and check the full sample payload it's meant to guard.


async def test_example_returns_sample_payload(client):
    response = await client.get("/api/v1/example")

    assert response.status_code == 200
    body = response.json()
    assert body["data"] == {
        "icao": "3C6444",
        "registration": "D-ABCD",
        "aircraft_type": "A320",
        "category": "PLANE",
        "owner": "Example Airlines",
        "squawk": "1234",
        "squawk_meaning": None,
        "distance_km": 42.5,
        "times_seen": 3,
    }
    assert body["meta"]["as_of"] is not None


async def test_example_not_in_openapi_schema(client):
    """include_in_schema=False -- this is a manual test helper, not part
    of the public API surface."""
    response = await client.get("/openapi.json")

    assert "/api/v1/example" not in response.json()["paths"]


# -- /metrics -----------------------------------------------------------


async def test_metrics_not_exposed_when_prometheus_disabled(client):
    """ENABLE_PROMETHEUS defaults to false in this test environment, so
    the Instrumentator middleware should never have been mounted."""
    response = await client.get("/metrics")

    assert response.status_code == 404


# -- lifespan -------------------------------------------------------------


async def test_lifespan_starts_and_cleanly_cancels_poll_loop(monkeypatch):
    """main.lifespan starts poll_cache.poll_loop() on startup and cancels
    it on shutdown. Previously untested -- a broken cancel/await here
    would hang app shutdown in production."""
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def fake_poll_loop():
        started.set()
        try:
            await asyncio.Event().wait()  # block until cancelled
        except asyncio.CancelledError:
            cancelled.set()
            raise

    monkeypatch.setattr(poller.poll_cache, "poll_loop", fake_poll_loop)

    async with app.router.lifespan_context(app):
        await asyncio.wait_for(started.wait(), timeout=1)

    assert cancelled.is_set()
