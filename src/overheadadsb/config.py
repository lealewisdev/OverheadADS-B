import os
from pathlib import Path

TZ = os.getenv("TZ", "Europe/London")

LAT = os.getenv("LAT", "0.000")
LON = os.getenv("LON", "0.000")
RAD_NM = os.getenv("RAD_NM", "4")

# adsb.fi's public endpoints are rate limited to 1 request/second -- clamp so
# a misconfigured POLL_INT can't get this deployment rate-limited or banned.
POLL_INT = max(float(os.getenv("POLL_INT", "10")), 1.0)
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "5"))

OWNER_POLL_CACHE_MAX = float(os.getenv("OWNER_POLL_CACHE_MAX", "5000"))

ADSBFI_URL = f"https://opendata.adsb.fi/api/v3/lat/{LAT}/lon/{LON}/dist/{RAD_NM}"
HEXDB_URL = "https://hexdb.io/api/v1/aircraft/"
FR24_URL = "https://www.flightradar24.com/data/aircraft"

# Anchored to the package directory, not the process's working directory: a
# CWD-relative path only works when the app happens to be launched from the
# repo root, and breaks for an installed wheel, a container with a different
# WORKDIR, or a systemd unit with its own WorkingDirectory.
_DATA_DIR = Path(__file__).parent / "data"
SQUAWKS_CSV = str(_DATA_DIR / "uk_squawk_codes.csv")
ICAO_CSV = str(_DATA_DIR / "aircraft_type_designators_helicopter.csv")

DATABASE_URL = os.getenv("DATABASE_URL")
ENABLE_PROMETHEUS = os.getenv("ENABLE_PROMETHEUS", "false").lower() == "true"
