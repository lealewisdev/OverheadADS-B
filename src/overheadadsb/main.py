import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse

# from prometheus_fastapi_instrumentator import Instrumentator
from overheadadsb import config
from overheadadsb.models import Aircraft, AircraftCategory, APIResponse, Meta
from overheadadsb.poller import poll_cache

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("overhead_main")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    poll_loop = asyncio.create_task(poll_cache.poll_loop())
    yield
    _ = poll_loop.cancel()
    try:
        await poll_loop
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="Overhead ADS-B",
    version="1.0.0",
    lifespan=lifespan,
)

# Instrumentator().instrument(app).expose(app)


def build_meta(
    as_of: datetime | None,
):
    return Meta(
        as_of=as_of,
    )


@app.get(
    "/api/v1/overhead",
    response_model=APIResponse,
)
async def overhead():
    aircraft, as_of = await poll_cache.snapshot()
    return APIResponse(
        data=aircraft,
        meta=build_meta(
            as_of,
        ),
    )


@app.get("/api/v1/overhead/FR24")
async def nearest_flightradar24():
    (
        overhead,
        _,
    ) = await poll_cache.snapshot()
    if overhead and not overhead.registration:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "no_registration",
                "message": "No aircraft in range with registration",
            },
        )
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=config.HTTP_TIMEOUT,
        ) as client:
            if overhead:
                response = await client.get(
                    f"{config.FR24_URL}/{overhead.registration}"
                )
                redirect = str(response.url)
                if redirect.rstrip("/") == config.FR24_URL:
                    raise HTTPException(
                        status_code=404,
                        detail={
                            "code": "no_flightradar24_entry",
                            "message": "No FlightRadar24 entry for {overhead.registration}",
                        },
                    )
                return RedirectResponse(
                    url=redirect,
                    status_code=302,
                )
    except httpx.HTTPError as e:
        logger.warning(
            "FR24 lookup failed: %s",
            e,
        )
        raise HTTPException(
            status_code=502,
            detail={
                "code": "flightradar24_unreachable",
                "message": "Unable to reach FlightRadar24",
            },
        )


@app.get(
    "/health",
    response_model=Meta,
)
async def health():
    as_of = await poll_cache.health()
    return Meta(
        as_of=as_of,
    )


@app.get(
    "/api/v1/rainmetertest",
    response_model=APIResponse,
)
async def example():
    example_aircraft = Aircraft(
        icao="3C6444",
        registration="D-ABCD",
        aircraft_type="A320",
        category=AircraftCategory.PLANE,
        owner="Example Airlines",
        squawk="1234",
        squawk_meaning=None,
        distance_km=42.5,
        times_seen=3,
    )
    return APIResponse(
        data=example_aircraft,
        meta=build_meta(datetime.now(ZoneInfo(config.TZ))),
    )
