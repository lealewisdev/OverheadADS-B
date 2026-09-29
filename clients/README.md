# Dashboard & Clients

Three ways to consume Overhead ADS-B: a [Grafana](https://github.com/grafana/grafana)
dashboard for the API's own operational health, and two lightweight desktop
widgets — [Quickshell](https://quickshell.org/) and
[Rainmeter](https://www.rainmeter.net/) — that turn `/api/v1/overhead` into a
one-line "what's flying overhead right now" readout.

```text
                 ┌─ Grafana dashboard  (request rate, latency, errors)
overheadadsb ────┼─ Quickshell widget  (Linux bar)
   /metrics       └─ Rainmeter skin    (Windows desktop)
   /api/v1/overhead
```

<!-- d2: overheadadsb -> {grafana, quickshell, rainmeter} -->

## Grafana Dashboard

Panels covering the API itself, not the aircraft data: request rate (by
status and by endpoint), p95 latency per endpoint, and a 5xx error-rate
gauge. Metrics come from the app's built-in
[prometheus-fastapi-instrumentator](https://github.com/trallnag/prometheus-fastapi-instrumentator)
exposition at `/metrics`.

## Requirements

- `ENABLE_PROMETHEUS=true` set on the service (see the main README's
  [Configuration](../README.md#configuration) table)
- A [Grafana Alloy](https://github.com/grafana/alloy) scrape job on the
  same Docker network, targeting the container directly (no published
  port needed):

  ```alloy
  prometheus.scrape "overheadadsb" {
    targets         = [{ "__address__" = "overheadadsb:8003", "instance" = "overheadadsb" }]
    metrics_path    = "/metrics"
    job_name        = "overheadadsb"
    forward_to      = [prometheus.remote_write.victoriametrics.receiver]
    scrape_interval = "60s"
  }
  ```

## Provisioning

| File                     | Role                                                                    |
|--------------------------|-------------------------------------------------------------------------|
| `dashboards.yaml`        | Provisioning provider — tells Grafana where to load dashboard JSON from |
| `overheadadsb-dash.json` | The dashboard itself                                                    |

```bash
cp dashboards.yaml /etc/grafana/provisioning/dashboards/
mkdir -p /etc/grafana/provisioning/dashboards/overheadadsb
cp overheadadsb-dash.json /etc/grafana/provisioning/dashboards/overheadadsb/
docker compose restart grafana
```

The dashboard polls on a 1-minute auto-refresh over a 1-hour window by
default, since it's meant as a live operational view rather than a
long-range overview.

## Quickshell Client

A [Quickshell](https://quickshell.org/) bar widget written in QML.

| File             | Role                                                                                                          |
|------------------|---------------------------------------------------------------------------------------------------------------|
| `ADSB.qml`       | Singleton data model — polls the API via `curl` on a timer, parses JSON, exposes `displayText` and `hasError` |
| `ADSBWidget.qml` | The `Text` element that renders `displayText`, coloured red on error                                          |
| `Bar.qml`        | Example panel bar embedding the widget on every screen                                                        |

## Setups

1. Copy the three files into your Quickshell config.
2. Set `apiUrl` in `ADSB.qml` to your instance (defaults to
   `https://overheadadsb.mydomain.tld/api/v1/overhead`).
3. Install [Iosevka Nerd Font](https://github.com/ryanoasis/nerd-fonts) —
   `ADSBWidget.qml` renders in "Iosevka Nerd Font Mono" for the plane/heli
   glyphs.

## Behaviours

- Polls every `refreshIntervalMs` (5000ms default).
- Display order: `squawk_meaning` → category icon (plane `\uf072` / heli
  `\uedfd`) → `owner`, falling back to `registration`, then `icao`.
- Text is empty (`idleText`) when there's no aircraft in range.
- Turns red (`#f38ba8`) if the response fails to parse or the request
  errors — there's no explicit "unreachable" state beyond that colour
  change, since a failed `curl` simply leaves `lastData` and `hasError`
  at their previous values until the next successful parse.

## Rainmeter Client

A [Rainmeter](https://www.rainmeter.net/) skin (`overheadadsb.ini`) using
the bundled `WebParser.dll` plugin to poll and regex-parse the API
response directly — no external dependencies beyond Rainmeter itself.

## Setup

1. Copy `overheadadsb.ini` into a skin folder under Rainmeter's `Skins`
   directory.
2. Set the `URL` and `UpdateRate` variables at the top of the file.
3. Install [Iosevka Nerd Font](https://github.com/ryanoasis/nerd-fonts) —
   the skin renders in "Iosevka NF" for the glyphs.
4. Refresh the skin from Rainmeter's tray icon or skin editor.

## Behaviour

- `MeasureDataCheck` toggles between two meters depending on whether
  `"data"` in the response is `null`: `MeterEmpty` shows "󰄶 Aircraft Free
  Zone", `MeterPlaneInfo` shows the live readout.
- `MeterPlaneInfo` text order is `%2 %1 %3` → squawk meaning, category
  icon, owner (any missing field falls back to "Unknown" via
  `RegExpSubstitute`).
- Point `URL` at `/api/v1/example` instead of `/api/v1/overhead` to check
  the layout renders correctly without live traffic.
