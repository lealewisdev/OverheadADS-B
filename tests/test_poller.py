"""Tests for overheadadsb.poller.PollCache."""

import asyncio

import httpx
import pytest
import respx

from overheadadsb import config, metrics, poller
from overheadadsb.models import AircraftCategory

# asyncio_mode = "auto" (set in pyproject.toml) picks up async def tests
# automatically -- no explicit pytestmark needed, and one test below is
# intentionally sync.

# -- load_reference_data ------------------------------------------------


async def test_load_reference_data(poll_cache, tiny_reference_data):
    poll_cache.load_reference_data()

    assert poll_cache.squawks == {
        "7700": "Emergency",
        "7600": "Radio failure",
        "1177": "HEMS",
    }
    assert poll_cache.heli_types == {"EC35", "H125", "AW139"}


def test_load_reference_data_from_real_bundled_files(poll_cache):
    """Smoke test against the actual shipped CSVs (not the tiny fixture),
    so a bad `scripts/generate_*` regeneration is caught before it ships."""
    poll_cache.load_reference_data()

    assert len(poll_cache.squawks) > 0
    assert len(poll_cache.heli_types) > 0
    assert "0000" in poll_cache.squawks  # present since the file's early rows


# -- _identify_owner ------------------------------------------------------


@respx.mock
async def test_identify_owner_cache_hit_skips_network(poll_cache):
    poll_cache._owner_poll_cache["ABC123"] = "Example Airlines"
    poll_cache._client = httpx.AsyncClient()

    owner = await poll_cache._identify_owner("ABC123")

    assert owner == "Example Airlines"
    assert respx.calls.call_count == 0
    await poll_cache._client.aclose()


@respx.mock
async def test_identify_owner_success_is_cached(poll_cache):
    respx.get(config.HEXDB_URL + "ABC123").mock(
        return_value=httpx.Response(200, json={"RegisteredOwners": "Example Airlines"})
    )
    poll_cache._client = httpx.AsyncClient()

    owner = await poll_cache._identify_owner("ABC123")

    assert owner == "Example Airlines"
    assert poll_cache._owner_poll_cache["ABC123"] == "Example Airlines"
    await poll_cache._client.aclose()


@respx.mock
async def test_identify_owner_known_unowned_is_cached(poll_cache):
    """A 200 response with no owner listed is a real answer and should
    be cached, unlike a failed request (see the next test)."""
    respx.get(config.HEXDB_URL + "ABC123").mock(
        return_value=httpx.Response(200, json={"RegisteredOwners": None})
    )
    poll_cache._client = httpx.AsyncClient()

    owner = await poll_cache._identify_owner("ABC123")

    assert owner is None
    assert "ABC123" in poll_cache._owner_poll_cache
    await poll_cache._client.aclose()


@respx.mock
async def test_identify_owner_failure_is_not_cached(poll_cache):
    """A network failure shouldn't stick -- retry next time this aircraft
    is seen, rather than caching a false 'no owner' forever."""
    respx.get(config.HEXDB_URL + "ABC123").mock(side_effect=httpx.ConnectError("boom"))
    poll_cache._client = httpx.AsyncClient()

    owner = await poll_cache._identify_owner("ABC123")

    assert owner is None
    assert "ABC123" not in poll_cache._owner_poll_cache
    await poll_cache._client.aclose()


async def test_identify_owner_lru_eviction(poll_cache, monkeypatch):
    monkeypatch.setattr(config, "OWNER_POLL_CACHE_MAX", 2)
    poll_cache._owner_poll_cache["A"] = "Owner A"
    poll_cache._owner_poll_cache["B"] = "Owner B"
    poll_cache._client = httpx.AsyncClient()

    with respx.mock:
        respx.get(config.HEXDB_URL + "C").mock(
            return_value=httpx.Response(200, json={"RegisteredOwners": "Owner C"})
        )
        await poll_cache._identify_owner("C")

    await poll_cache._client.aclose()
    assert "A" not in poll_cache._owner_poll_cache  # oldest, evicted
    assert set(poll_cache._owner_poll_cache) == {"B", "C"}


# -- database-backed sighting persistence ------------------------------
#
# None of this was previously covered: _ensure_schema, _load_sighting_counts,
# and the _db_pool branch of _record_sighting only ever ran against a real
# Postgres instance, never in the test suite. FakeAsyncpgPool (conftest.py)
# stands in for asyncpg.Pool so these can run without a database.


async def test_ensure_schema_creates_sightings_table(poll_cache, fake_db_pool):
    pool = fake_db_pool()
    poll_cache._db_pool = pool

    await poll_cache._ensure_schema()

    assert len(pool.executed) == 1
    query, _ = pool.executed[0]
    assert "CREATE TABLE IF NOT EXISTS aircraft_sightings" in query


async def test_load_sighting_counts_populates_cache_from_db(poll_cache, fake_db_pool):
    pool = fake_db_pool(
        rows=[{"icao": "A1", "times_seen": 3}, {"icao": "B2", "times_seen": 9}]
    )
    poll_cache._db_pool = pool

    await poll_cache._load_sighting_counts()

    assert poll_cache._sighting_counts == {"A1": 3, "B2": 9}


async def test_record_sighting_without_db_only_updates_memory(poll_cache):
    """No DATABASE_URL configured -> in-memory counting only (the path the
    existing poll_once tests already exercise indirectly)."""
    await poll_cache._record_sighting("ICAO1")
    await poll_cache._record_sighting("ICAO1")

    assert poll_cache._sighting_counts["ICAO1"] == 2


async def test_sighting_count_defaults_to_zero_for_unseen_icao(poll_cache):
    assert await poll_cache.sighting_count("NEVERSEEN") == 0


async def test_sighting_count_reflects_recorded_sightings(poll_cache):
    await poll_cache._record_sighting("ICAO1")
    await poll_cache._record_sighting("ICAO1")

    assert await poll_cache.sighting_count("ICAO1") == 2


async def test_record_sighting_persists_via_db_pool_when_configured(
    poll_cache, fake_db_pool
):
    pool = fake_db_pool(fetchval_return=5)
    poll_cache._db_pool = pool

    await poll_cache._record_sighting("ICAO1")

    assert (
        poll_cache._sighting_counts["ICAO1"] == 5
    )  # takes the DB's count, not a local increment
    assert len(pool.fetchval_calls) == 1
    query, args = pool.fetchval_calls[0]
    assert args == ("ICAO1",)
    assert "ON CONFLICT" in query
    assert "INSERT INTO aircraft_sightings" in query


# -- poll_once --------------------------------------------------------------

_EMPTY_ENVELOPE = {"msg": "ok", "now": 0, "total": 0, "ctime": 0, "ptime": 0}


def _adsbfi_body(aircraft: list[dict]) -> dict:
    return {**_EMPTY_ENVELOPE, "ac": aircraft, "total": len(aircraft)}


@respx.mock
async def test_poll_once_picks_nearest_and_classifies(poll_cache, tiny_reference_data):
    poll_cache.load_reference_data()
    poll_cache._client = httpx.AsyncClient()
    respx.get(config.ADSBFI_URL).mock(
        return_value=httpx.Response(
            200,
            json=_adsbfi_body(
                [
                    {"hex": "FAR1", "dst": 12.0, "t": "A320"},
                    {
                        "hex": "NEAR1",
                        "dst": 3.5,
                        "t": "EC35",
                        "squawk": "1177",
                        "r": "G-TEST",
                    },
                    {"hex": "NODIST"},  # dst missing -> sorts as farthest
                ]
            ),
        )
    )
    respx.get(config.HEXDB_URL + "NEAR1").mock(
        return_value=httpx.Response(200, json={"RegisteredOwners": "Air Ambulance"})
    )

    await poll_cache.poll_once()
    overhead, as_of = await poll_cache.snapshot()

    assert overhead is not None
    assert overhead.icao == "NEAR1"
    assert overhead.category is AircraftCategory.HELI
    assert overhead.owner == "Air Ambulance"
    assert overhead.squawk_meaning == "HEMS"
    assert overhead.distance_km == round(3.5 * 1.852, 1)
    assert overhead.times_seen == 1
    assert as_of is not None
    await poll_cache._client.aclose()


@respx.mock
async def test_poll_once_no_aircraft_in_range(poll_cache, tiny_reference_data):
    poll_cache.load_reference_data()
    poll_cache._client = httpx.AsyncClient()
    respx.get(config.ADSBFI_URL).mock(
        return_value=httpx.Response(200, json=_adsbfi_body([]))
    )

    await poll_cache.poll_once()
    overhead, _ = await poll_cache.snapshot()

    assert overhead is None
    await poll_cache._client.aclose()


@respx.mock
async def test_poll_once_times_seen_only_increments_when_overhead_changes(
    poll_cache, tiny_reference_data
):
    poll_cache.load_reference_data()
    poll_cache._client = httpx.AsyncClient()
    same = httpx.Response(200, json=_adsbfi_body([{"hex": "SAME1", "dst": 1.0}]))
    other = httpx.Response(200, json=_adsbfi_body([{"hex": "OTHER1", "dst": 1.0}]))
    respx.get(config.ADSBFI_URL).mock(side_effect=[same, same, other, same])
    respx.get(config.HEXDB_URL + "SAME1").mock(
        return_value=httpx.Response(200, json={})
    )
    respx.get(config.HEXDB_URL + "OTHER1").mock(
        return_value=httpx.Response(200, json={})
    )

    await poll_cache.poll_once()
    overhead, _ = await poll_cache.snapshot()
    assert overhead.times_seen == 1

    await poll_cache.poll_once()  # SAME1 again, consecutively
    overhead, _ = await poll_cache.snapshot()
    assert overhead.times_seen == 1  # unchanged

    await poll_cache.poll_once()  # OTHER1 becomes overhead
    await poll_cache.poll_once()  # SAME1 becomes overhead again
    overhead, _ = await poll_cache.snapshot()
    assert overhead.icao == "SAME1"
    assert overhead.times_seen == 2  # incremented on return

    await poll_cache._client.aclose()


@respx.mock
async def test_poll_once_network_failure_keeps_previous_overhead(
    poll_cache, tiny_reference_data
):
    poll_cache.load_reference_data()
    poll_cache._client = httpx.AsyncClient()
    good = httpx.Response(200, json=_adsbfi_body([{"hex": "GOOD1", "dst": 1.0}]))
    respx.get(config.ADSBFI_URL).mock(side_effect=[good, httpx.ConnectError("boom")])
    respx.get(config.HEXDB_URL + "GOOD1").mock(
        return_value=httpx.Response(200, json={})
    )

    await poll_cache.poll_once()
    overhead_before, as_of_before = await poll_cache.snapshot()
    assert overhead_before.icao == "GOOD1"

    await poll_cache.poll_once()  # this poll fails
    overhead_after, as_of_after = await poll_cache.snapshot()

    assert overhead_after == overhead_before  # unchanged on failure
    assert as_of_after == as_of_before  # not bumped on failure
    _, poll_ok, last_error = await poll_cache.health()
    assert poll_ok is False
    assert last_error is not None

    await poll_cache._client.aclose()


@respx.mock
async def test_poll_once_unknown_squawk_has_no_meaning(poll_cache, tiny_reference_data):
    poll_cache.load_reference_data()
    poll_cache._client = httpx.AsyncClient()
    respx.get(config.ADSBFI_URL).mock(
        return_value=httpx.Response(
            200, json=_adsbfi_body([{"hex": "X1", "dst": 1.0, "squawk": "9999"}])
        )
    )
    respx.get(config.HEXDB_URL + "X1").mock(return_value=httpx.Response(200, json={}))

    await poll_cache.poll_once()
    overhead, _ = await poll_cache.snapshot()

    assert overhead.squawk == "9999"
    assert overhead.squawk_meaning is None  # present in the feed, absent from our CSV
    await poll_cache._client.aclose()


@respx.mock
async def test_poll_once_defaults_to_plane_when_type_missing(
    poll_cache, tiny_reference_data
):
    poll_cache.load_reference_data()
    poll_cache._client = httpx.AsyncClient()
    respx.get(config.ADSBFI_URL).mock(
        return_value=httpx.Response(200, json=_adsbfi_body([{"hex": "X2", "dst": 1.0}]))
    )
    respx.get(config.HEXDB_URL + "X2").mock(return_value=httpx.Response(200, json={}))

    await poll_cache.poll_once()
    overhead, _ = await poll_cache.snapshot()

    assert overhead.category is AircraftCategory.PLANE
    await poll_cache._client.aclose()


@respx.mock
async def test_poll_once_malformed_hexdb_response_treated_as_lookup_failure(
    poll_cache, tiny_reference_data
):
    """`_identify_owner` now catches `json.JSONDecodeError` and
    `ValidationError` alongside `httpx.HTTPError`, so a 200 response with an
    invalid or wrongly-shaped hexdb.io body no longer escapes uncaught and
    crashes the poll -- it's treated like any other lookup failure: logged,
    counted as `result="error"`, owner left as `None`, not cached (retried
    next time this aircraft is seen)."""
    poll_cache.load_reference_data()
    poll_cache._client = httpx.AsyncClient()
    respx.get(config.ADSBFI_URL).mock(
        return_value=httpx.Response(
            200, json=_adsbfi_body([{"hex": "BAD1", "dst": 1.0}])
        )
    )
    respx.get(config.HEXDB_URL + "BAD1").mock(
        return_value=httpx.Response(200, content=b"not json")
    )

    await poll_cache.poll_once()

    assert poll_cache._sighting_counts["BAD1"] == 1
    overhead, _ = await poll_cache.snapshot()
    assert overhead is not None
    assert overhead.icao == "BAD1"
    assert overhead.owner is None
    assert "BAD1" not in poll_cache._owner_poll_cache

    await poll_cache._client.aclose()


# -- poll_loop ----------------------------------------------------------
#
# Previously untested end to end: reference-data loading, optional DB
# bootstrap, the httpx client lifecycle, per-iteration error containment,
# and cleanup on cancellation (the same cancellation main.lifespan performs
# on shutdown).


async def test_poll_loop_sets_up_db_and_loads_persisted_counts(
    poll_cache, tiny_reference_data, monkeypatch, fake_db_pool
):
    fake_pool = fake_db_pool(rows=[{"icao": "OLD1", "times_seen": 7}])

    async def fake_create_pool(*args, **kwargs):
        return fake_pool

    async def fake_poll_once():
        await asyncio.sleep(0)  # never touch the real network

    monkeypatch.setattr(config, "DATABASE_URL", "postgres://fake")
    monkeypatch.setattr(config, "POLL_INT", 0.01)
    monkeypatch.setattr(poller.asyncpg, "create_pool", fake_create_pool)
    monkeypatch.setattr(poll_cache, "poll_once", fake_poll_once)

    task = asyncio.create_task(poll_cache.poll_loop())
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert poll_cache._sighting_counts == {
        "OLD1": 7
    }  # loaded via _load_sighting_counts
    assert any("CREATE TABLE" in q for q, _ in fake_pool.executed)
    assert fake_pool.closed is True  # cleaned up on cancellation
    assert poll_cache._client is not None
    assert poll_cache._client.is_closed


async def test_poll_loop_survives_unexpected_error_and_keeps_polling(
    poll_cache, tiny_reference_data, monkeypatch
):
    monkeypatch.setattr(config, "POLL_INT", 0.01)
    calls = []

    async def flaky_poll_once():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("boom")

    monkeypatch.setattr(poll_cache, "poll_once", flaky_poll_once)
    before = metrics.polls_total.labels(result="unexpected_error")._value.get()

    task = asyncio.create_task(poll_cache.poll_loop())
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert len(calls) >= 2  # the RuntimeError on call 1 didn't kill the loop
    _, poll_ok, _ = await poll_cache.health()
    assert poll_ok is False  # left unhealthy by the failed call
    after = metrics.polls_total.labels(result="unexpected_error")._value.get()
    assert after == before + 1
    assert poll_cache._client.is_closed  # still cleaned up on cancel
