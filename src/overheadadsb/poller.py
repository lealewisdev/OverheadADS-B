import asyncio
import csv
import json
import logging
from collections import OrderedDict
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
from pydantic import ValidationError

from overheadadsb import config
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

    async def _identify_owner(self, icao: str) -> str | None:
        if icao in self._owner_poll_cache:
            self._owner_poll_cache.move_to_end(icao)
            return self._owner_poll_cache[icao]

        assert self._client is not None
        try:
            response = await self._client.get(config.HEXDB_URL + icao)
            _ = response.raise_for_status()
            owner = HEXDBResponse.model_validate(response.json()).RegisteredOwners
        except httpx.HTTPError as e:
            logger.warning("HexDB lookup failed for %s: %s", icao, e)
            owner = None

        self._owner_poll_cache[icao] = owner
        if len(self._owner_poll_cache) > config.OWNER_POLL_CACHE_MAX:
            _ = self._owner_poll_cache.popitem(last=False)
        return owner

    async def poll_once(self):
        assert self._client is not None
        try:
            response = await self._client.get(config.ADSBFI_URL)
            _ = response.raise_for_status()
            body = ADSBFIResponse.model_validate(response.json())

        except (httpx.HTTPError, json.JSONDecodeError, ValidationError) as e:
            logger.warning("ADS-B.fi poll failed: %s", e)
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
            was_already_overhead: bool = (
                self._overhead is not None and self._overhead.icao == icao
            )
            if not was_already_overhead:
                self._sighting_counts[icao] = self._sighting_counts.get(icao, 0) + 1
            overhead = Aircraft(
                icao=icao,
                registration=nearest.r,
                aircraft_type=nearest.t,
                category=(
                    AircraftCategory.HELI
                    if nearest.t in self.heli_types
                    else AircraftCategory.PLANE
                ),
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

    async def sighting_count(self, icao: str) -> int:
        async with self._lock:
            return self._sighting_counts.get(icao, 0)

    async def snapshot(self):
        async with self._lock:
            return (
                self._overhead,
                self._as_of,
            )

    async def health(self):
        async with self._lock:
            return self._as_of

    async def poll_loop(self):
        self.load_reference_data()
        self._client = httpx.AsyncClient(timeout=config.HTTP_TIMEOUT)
        try:
            while True:
                try:
                    await self.poll_once()
                except Exception:
                    logger.exception("Unexpected poller failure")
                    async with self._lock:
                        self._poll_ok = False
                await asyncio.sleep(config.POLL_INT)
        finally:
            if self._client:
                await self._client.aclose()


poll_cache = PollCache()
