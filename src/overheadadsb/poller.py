import asyncio
import csv
import json
import logging
import time
from collections import OrderedDict
from datetime import datetime
from zoneinfo import ZoneInfo

import asyncpg
import httpx
from pydantic import ValidationError

from overheadadsb import config, metrics
from overheadadsb.models import (
    ADSBFIResponse,
    ADSBFIResponseItem,
    Aircraft,
    AircraftCategory,
    HEXDBResponse,
)

logger = logging.getLogger("overhead_poller")


class PollCache:
    def __init__(self):
        self._lock: asyncio.Lock = asyncio.Lock()
        self._overhead: Aircraft | None = None
        self._as_of: datetime | None = None
        self._poll_ok: bool = False
        self._last_error: str | None = None
        self._owner_poll_cache: OrderedDict[str, str | None] = OrderedDict()
        self._sighting_counts: dict[str, int] = {}
        self.squawks: dict[str, str] = {}
        self.heli_types: set[str] = set()
        self._client: httpx.AsyncClient | None = None
        self._db_pool: asyncpg.Pool | None = None

    def load_reference_data(self):
        with open(config.SQUAWKS_CSV, newline="") as f:
            for row in csv.DictReader(f):
                self.squawks[row["squawk"]] = row["function"]
        with open(config.ICAO_CSV) as f:
            self.heli_types = {line.strip() for line in f if line.strip()}
        logger.info(
            "Loaded %d squawks and %d helicopter types",
            len(self.squawks),
            len(self.heli_types),
        )

    async def _ensure_schema(self):
        assert self._db_pool is not None
        await self._db_pool.execute(
            """
            CREATE TABLE IF NOT EXISTS aircraft_sightings (
                icao        TEXT PRIMARY KEY,
                times_seen  INTEGER NOT NULL DEFAULT 0,
                first_seen  TIMESTAMPTZ NOT NULL DEFAULT now(),
                last_seen   TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )

    async def _load_sighting_counts(self):
        assert self._db_pool is not None
        rows = await self._db_pool.fetch(
            "SELECT icao, times_seen FROM aircraft_sightings"
        )
        self._sighting_counts = {row["icao"]: row["times_seen"] for row in rows}
        logger.info("Loaded %d persisted sighting counts", len(self._sighting_counts))

    async def _record_sighting(self, icao: str) -> None:
        """Increment the sighting count for icao and persist it if a database
        is configured; always keeps the in-memory cache in sync so poll_once
        can read it back without an extra round trip."""
        if self._db_pool is None:
            self._sighting_counts[icao] = self._sighting_counts.get(icao, 0) + 1
            return

        count = await self._db_pool.fetchval(
            """
            INSERT INTO aircraft_sightings (icao, times_seen, first_seen, last_seen)
            VALUES ($1, 1, now(), now())
            ON CONFLICT (icao) DO UPDATE
                SET times_seen = aircraft_sightings.times_seen + 1,
                    last_seen  = now()
            RETURNING times_seen
            """,
            icao,
        )
        self._sighting_counts[icao] = count

    async def _identify_owner(self, icao: str) -> str | None:
        if icao in self._owner_poll_cache:
            self._owner_poll_cache.move_to_end(icao)
            metrics.hexdb_lookups_total.labels(result="hit").inc()
            return self._owner_poll_cache[icao]

        assert self._client is not None
        try:
            response = await self._client.get(config.HEXDB_URL + icao)
            _ = response.raise_for_status()
            owner = HEXDBResponse.model_validate(response.json()).RegisteredOwners
        except httpx.HTTPError as e:
            logger.warning("HexDB lookup failed for %s: %s", icao, e)
            metrics.hexdb_lookups_total.labels(result="error").inc()
            return None  # not cached — retried next time this aircraft is seen

        metrics.hexdb_lookups_total.labels(result="miss").inc()
        self._owner_poll_cache[icao] = owner
        if len(self._owner_poll_cache) > config.OWNER_POLL_CACHE_MAX:
            _ = self._owner_poll_cache.popitem(last=False)
        return owner

    async def poll_once(self):
        assert self._client is not None
        start = time.monotonic()
        try:
            response = await self._client.get(config.ADSBFI_URL)
            _ = response.raise_for_status()
            body = ADSBFIResponse.model_validate(response.json())

        except (httpx.HTTPError, json.JSONDecodeError, ValidationError) as e:
            logger.warning("ADS-B.fi poll failed: %s", e)
            metrics.polls_total.labels(result="failure").inc()
            metrics.poll_duration_seconds.observe(time.monotonic() - start)
            async with self._lock:
                self._poll_ok = False
                self._last_error = str(e)
            return

        aircraft: list[ADSBFIResponseItem] = sorted(
            body.ac, key=lambda a: a.dst if a.dst is not None else float("inf")
        )
        overhead: Aircraft | None = None
        if aircraft:
            nearest = aircraft[0]
            icao: str = nearest.hex
            squawk: str | None = nearest.squawk
            category = (
                AircraftCategory.HELI
                if nearest.t in self.heli_types
                else AircraftCategory.PLANE
            )
            was_already_overhead: bool = (
                self._overhead is not None and self._overhead.icao == icao
            )
            if not was_already_overhead:
                await self._record_sighting(icao)
                metrics.aircraft_sightings_total.labels(category=category.value).inc()
            overhead = Aircraft(
                icao=icao,
                registration=nearest.r,
                aircraft_type=nearest.t,
                category=category,
                owner=await self._identify_owner(icao),
                squawk=squawk,
                squawk_meaning=self.squawks.get(squawk) if squawk else None,
                distance_km=round(nearest.dst * 1.852, 1)
                if nearest.dst is not None
                else None,
                times_seen=self._sighting_counts[icao],
            )
            logger.info("Aircraft: %s", overhead)
        async with self._lock:
            self._overhead = overhead
            self._as_of = datetime.now(ZoneInfo(config.TZ))
            self._poll_ok = True
            self._last_error = None
        metrics.polls_total.labels(result="success").inc()
        metrics.last_successful_poll_timestamp.set(time.time())
        metrics.poll_duration_seconds.observe(time.monotonic() - start)

    async def sighting_count(self, icao: str) -> int:
        async with self._lock:
            return self._sighting_counts.get(icao, 0)

    async def snapshot(self):
        async with self._lock:
            return (
                self._overhead,
                self._as_of,
            )

    async def health(self) -> tuple[datetime | None, bool, str | None]:
        async with self._lock:
            return (self._as_of, self._poll_ok, self._last_error)

    async def poll_loop(self):
        self.load_reference_data()
        if config.DATABASE_URL:
            self._db_pool = await asyncpg.create_pool(
                config.DATABASE_URL, min_size=1, max_size=5
            )
            await self._ensure_schema()
            await self._load_sighting_counts()
        self._client = httpx.AsyncClient(timeout=config.HTTP_TIMEOUT)
        try:
            while True:
                try:
                    await self.poll_once()
                except Exception:
                    logger.exception("Unexpected poller failure")
                    metrics.polls_total.labels(result="unexpected_error").inc()
                    async with self._lock:
                        self._poll_ok = False
                await asyncio.sleep(config.POLL_INT)
        finally:
            if self._client:
                await self._client.aclose()
            if self._db_pool:
                await self._db_pool.close()


poll_cache = PollCache()
