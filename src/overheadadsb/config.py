import os

TZ = os.getenv("TZ", "Europe/London")

LAT = os.getenv("LAT", "0.000")
LON = os.getenv("LON", "0.000")
RAD_NM = os.getenv("RAD_NM", "4")

POLL_INT = float(os.getenv("POLL_INT", "10"))
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "5"))

OWNER_POLL_CACHE_MAX = float(os.getenv("OWNER_POLL_CACHE_MAX", "5000"))

ADSBFI_URL = f"https://opendata.adsb.fi/api/v3/lat/{LAT}/lon/{LON}/dist/{RAD_NM}"
HEXDB_URL = "https://hexdb.io/api/v1/aircraft/"
FR24_URL = "https://www.flightradar24.com/data/aircraft"

SQUAWKS_CSV = "src/overheadadsb/data/uk_squawk_codes.csv"
ICAO_CSV = "src/overheadadsb/data/aircraft_type_designators_helicopter.csv"
