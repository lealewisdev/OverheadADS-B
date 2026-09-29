from prometheus_client import Counter, Gauge, Histogram

polls_total = Counter(
    "overheadadsb_polls_total",
    "Poll attempts against the ADS-B feed",
    ["result"],  # success | failure | unexpected_error
)

last_successful_poll_timestamp = Gauge(
    "overheadadsb_last_successful_poll_timestamp_seconds",
    "Unix timestamp of the last successful poll",
)

poll_duration_seconds = Histogram(
    "overheadadsb_poll_duration_seconds",
    "Time spent in a single poll_once() call",
)

hexdb_lookups_total = Counter(
    "overheadadsb_hexdb_lookups_total",
    "Owner lookups against hexdb.io",
    ["result"],  # hit | miss | not_found | error
)

aircraft_sightings_total = Counter(
    "overheadadsb_aircraft_sightings_total",
    "New (non-repeat) aircraft sightings",
    ["category"],  # HELI | PLANE
)
