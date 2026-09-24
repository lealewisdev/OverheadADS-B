# Overhead ADS-B

An ADS-B telemetry enrichment API. It watches a public ADS-B feed for
aircraft near a location you choose, enriches the closest one with its
owner, registration, category (plane or helicopter) and UK squawk-code
meaning, and serves the result as JSON. Small desktop widgets turn that
into a one-line "what's flying overhead right now" readout.

## How it works

```text
 adsb.fi ──┐
 hexdb.io ─┼─▶ overheadadsb ──▶ /api/v1/overhead ──▶ desktop widgets
 CSV data ─┘     (FastAPI)           (JSON)        (Quickshell, Rainmeter)
```

1. On startup the service loads the bundled squawk table and helicopter
   type designators, then starts a background poll loop.
2. Every `POLL_INT` seconds it queries the
   [adsb.fi open data API](https://opendata.adsb.fi/) for aircraft within
   `RAD_NM` nautical miles of (`LAT`, `LON`) and picks the nearest.
3. The owner is looked up on [hexdb.io](https://hexdb.io/) by the
   aircraft's Mode S address and cached (up to `OWNER_POLL_CACHE_MAX`
   entries, least recently used evicted first).
4. The aircraft is classified as `HELI` if its ICAO type designator is in
   the helicopter list, otherwise `PLANE`.
5. The squawk is translated into its UK meaning where one is listed.
6. The latest result is held in memory and served by the endpoints below.
   If a poll fails, the previous result is kept and `as_of` does not
   change, so clients can tell how fresh it is.

## API

Interactive documentation is served at `/docs` (Swagger UI).

### `GET /api/v1/overhead`

Returns the closest aircraft in range, or `"data": null` when there is
none (or before the first successful poll).

```json
{
  "data": {
    "icao": "3C6444",
    "registration": "D-ABCD",
    "aircraft_type": "A320",
    "category": "PLANE",
    "owner": "Example Airlines",
    "squawk": "1234",
    "squawk_meaning": null,
    "distance_km": 6.3,
    "times_seen": 3
  },
  "meta": {
    "as_of": "2026-09-24T14:05:31.123456+01:00"
  }
}
```

The values above are illustrative. Only `icao` is always present; the
other aircraft fields are `null` when unknown.

- `icao`: the aircraft's Mode S hex address.
- `registration`, `aircraft_type`: from the ADS-B feed (type is the ICAO
  type designator, such as `A320`).
- `category`: `PLANE` or `HELI`.
- `owner`: registered owner according to hexdb.io.
- `squawk`, `squawk_meaning`: the transponder code and its UK meaning.
- `distance_km`: distance from the configured centre point.
- `times_seen`: how many separate times this aircraft has become the
  closest one since the service started (resets on restart).
- `meta.as_of`: time of the last successful poll, in the configured time
  zone.

### `GET /api/v1/overhead/FR24`

Redirects (302) to the Flightradar24 page for the closest aircraft's
registration. Errors return a JSON `detail` with a `code`:

- `404 no_registration`: the closest aircraft has no registration.
- `404 no_flightradar24_entry`: Flightradar24 has no page for it.
- `502 flightradar24_unreachable`: the lookup failed.

### `GET /health`

Returns `{"as_of": ...}` with the time of the last successful poll. The
status is 200 whenever the app is running, including before the first
successful poll, when `as_of` is `null`.

### `GET /api/v1/rainmetertest`

Returns a fixed example aircraft in the same format as `/api/v1/overhead`,
for testing a client without live traffic.

## Quick start

**Requirements**: Docker, Compose
**Optional**: (External) Docker network named `traefik`, personal fork of this
 repository to utilize the [CI/CD](#cicd-and-deployment) pipeline

```bash
git clone <repo-url>
cd OverheadADS-B

cp .env.example .env
$EDITOR .env    # set LAT, LON, RAD_NM, DOMAIN, REGISTRY, IMAGE_TAG, ...

docker network create traefik   # skip if it already exists
docker login <registry>
docker compose up -d
```

The service is then available at `https://overheadadsb.<DOMAIN>`:

```bash
curl https://overheadadsb.mydomain.tld/api/v1/overhead
```

To build locally instead of pulling, run `docker login dhi.io` (the base
images are Docker Hardened Images), comment out `image:` in
`compose.yaml`, uncomment the `build:` block and run
`docker compose up -d --build`. Locally built images are not compatible
with the provided Ansible playbooks.

To run without Docker you need Python 3.14 and
[uv](https://docs.astral.sh/uv/). Run from the repository root, because
the data files are loaded by relative path:

```bash
uv sync --no-dev
LAT=51.500 LON=-0.120 uv run uvicorn overheadadsb.main:app --port 8003
```

## Configuration

The app is configured entirely through environment variables. Copy
`.env.example` to `.env` for Docker Compose.

| Variable               | Default         | Description                    |
| ---------------------- | --------------- | ------------------------------ |
| `LAT`                  | `0.000`         | Latitude of the search centre  |
| `LON`                  | `0.000`         | Longitude of the search centre |
| `RAD_NM`               | `4`             | Search radius (nautical miles) |
| `POLL_INT`             | `10`            | Seconds between feed polls     |
| `HTTP_TIMEOUT`         | `5`             | Timeout for upstream requests  |
| `OWNER_POLL_CACHE_MAX` | `5000`          | Max cached owner lookups       |
| `PORT`                 | `8003`          | Port the API listens on        |
| `TZ`                   | `Europe/London` | Container time zone            |

The remaining entries in `.env.example` are used for deployment rather
than by the app. `REGISTRY`, `REGISTRY_USER` and `IMAGE_TAG` form the
image reference in `compose.yaml` (the deploy playbook rewrites
`IMAGE_TAG`), and `DOMAIN` sets the Traefik host rule
(`overheadadsb.<DOMAIN>`).

## Clients

Both clients poll `/api/v1/overhead` and show the squawk meaning, a
category icon and the owner (falling back to the registration, then the
hex address). Both need
[Iosevka Nerd Font](https://www.nerdfonts.com/) for the icons.

### Quickshell

Copy the files in `clients/quickshell/` into your Quickshell config and
set `apiUrl` in `ADSB.qml` to your instance. The widget polls with
`curl` every `refreshIntervalMs` (5 seconds by default) and turns red
when the API cannot be reached or its response cannot be parsed.

### Rainmeter

Copy `clients/rainmeter/overheadadsb.ini` into a skin folder and set the
`URL` and `UpdateRate` variables. The skin uses the WebParser plugin and
shows "Aircraft Free Zone" when `data` is `null`. Point `URL` at
`/api/v1/rainmetertest` to check the layout without live traffic.

## Development

Everything is built around [uv](https://docs.astral.sh/uv/) and Python
3.14. A reproducible shell is provided through
[devenv](https://devenv.sh/) (Nix):

```bash
devenv shell      # Python venv, uv sync, git, hadolint, prek
lint              # runs every pre-commit hook: prek run --all-files
prek install      # optional: install the git hooks
```

Without Nix, install uv, run `uv sync`, and use the commands below.

### Checks

These are the same checks the Docker `test` stage and CI run:

```bash
uv run ruff check src scripts
uv run basedpyright
uv run bandit -r src scripts -ll
uv run pytest --cov=overheadadsb --cov-report=term-missing

# or, all in one, exactly as CI does it
docker buildx build --target test .
```

Git hooks (managed by [prek](https://prek.j178.dev/)) cover whitespace,
large files, Hadolint, TruffleHog, Docker Compose linting, Ruff,
markdownlint, yamllint, ansible-lint and the Renovate config. Commit
messages follow [Conventional Commits](https://www.conventionalcommits.org/),
enforced by Commitizen.

### Regenerating the data files

The CSVs in `src/overheadadsb/data/` are generated by the scripts in
`scripts/`. `squawk_ranges.csv` and `faa.pdf` are not included in the repository
 and will be replaced as sources in future releases.

- `generate_uk_squawk_codes.py` expands `squawk_ranges.csv`, which was manually
 extracted from [deeside.com](https://www.deeside.com/squawk-codes/), into
 `squawks.csv`, one row per squawk code.
- `generate_aircraft_type_descriptions.py` reads the FAA Order
  JO 7360.1J PDF (`faa.pdf`) with pdfplumber and writes one CSV of type
  designators per aircraft class (`helicopter.csv`, `landplane.csv`,
  and so on).
- `generate_aircraft_type_designators.py` scrapes ICAO Doc 8643 type
  pages from [doc8643.com](https://doc8643.com/) into `icao.csv`, using a
  headless browser through `nodriver`. It expects `sitemap.xml` in the
  working directory (uncomment `get_sitemap()` to download it, and strip
  the `xmlns` attribute from the root tag so it parses).

Squawk meanings currently come from
[deeside.com](https://www.deeside.com/squawk-codes/), and helicopter
designators from the FAA order (see [TODO](#todo)).

## CI/CD and deployment

Workflows live in `.forgejo/workflows/` and run on Forgejo Actions.

- **PR checks** (`pr-checks.yml`): Hadolint, Compose lint, a TruffleHog
  secret scan, Renovate config validation and the `test` image stage.
- **Build, scan, push** (`build-scan.push.yml`): on pushes to `main`
  that touch code, packaging or CI files. It runs the tests, builds the
  `runtime` image, generates a CycloneDX SBOM, fails on fixable HIGH or
  CRITICAL vulnerabilities (Trivy), pushes `<sha>`, `v<version>` and
  `latest` tags, signs the image and attests the SBOM with cosign, then
  calls an n8n webhook to start deployment.
- **Scan latest image** (`scan-latest-image.yml`): nightly Trivy scan of
  the published `latest` image at 04:00 Europe/London, with n8n
  notifications.

Images are signed, so you can verify a pulled image with the public key
in the repo:

```bash
cosign verify --key packaging/cosign.pub <registry>/<repo>:<tag>
```

Renovate keeps dependencies current: container images are pinned by
digest, and lock files are refreshed on Mondays before 6am.

### Required configuration

| Type     | Name                                            |
| -------- | ----------------------------------------------- |
| Variable | `REGISTRY`, `SEMAPHORE_PROJECT_ID`              |
| Variable | `SEMAPHORE_DEPLOY_TEMPLATE_ID`                  |
| Variable | `SEMAPHORE_ROLLBACK_TEMPLATE_ID`                |
| Secret   | `DHI_USER`, `DHI_TOKEN`                         |
| Secret   | `REGISTRY_USER`, `REGISTRY_TOKEN`               |
| Secret   | `COSIGN_KEY`, `COSIGN_PASSWORD`                 |
| Secret   | `N8N_DEPLOY_WEBHOOK_URL`, `N8N_WEBHOOK_URL`     |
| Secret   | `N8N_WEBHOOK_TOKEN`, `SEMAPHORE_URL`            |
| Secret   | `APPRISE_URL`                                   |

### Deploying and rolling back

n8n receives the webhook and starts a Semaphore task that runs the
playbooks in `ansible/` against the `app_servers` group.

- `deploy.yml` records the running image tag (to `.previous_tag`), pulls
  the new image, sets `IMAGE_TAG` in the host's `.env`, recreates the
  service and waits for `health_url` (for example the `/health` endpoint)
  to return 200 (10 tries, 3 seconds apart). A failed health check fails
  the run, which triggers the rollback task.
- `rollback.yml` restores the tag saved in `.previous_tag` and recreates
  the service.

The playbooks expect these variables: `compose_dir`, `service_name`,
`registry`, `registry_user`, `image_repo`, `image_tag` and `health_url`,
plus a `registry_password` environment variable.

## Project layout

```text
.
├── src/overheadadsb/       # API: main, poller, models, config, CSV data
├── tests/                  # pytest suite (placeholder for now)
├── scripts/                # data-generation scripts
├── clients/
│   ├── quickshell/         # Quickshell bar widget (QML)
│   └── rainmeter/          # Rainmeter skin
├── ansible/                # deploy and rollback playbooks
├── packaging/              # nfpm config, cosign public key, Trivy ignores
├── .forgejo/workflows/     # PR checks, build/scan/push, nightly scan
├── Dockerfile              # builder, test, runtime and .deb package stages
├── compose.yaml            # Traefik-fronted service definition
├── devenv.nix, devenv.yaml # reproducible dev shell (Nix)
├── prek.toml               # pre-commit hooks
└── renovate.json           # dependency update policy
```

## TODO

1. Add D2 diagram
2. Switch from FAA Order JO 7360.1J to ICAO Doc 8643 aircraft-type
   description and generate aircraft type designators reffreences for all types
   instead of just helicopters
3. Switch from [deeside](https://www.deeside.com/squawk-codes/) to UK
   AIP ENR 1.6 for squawk codes
4. Packaging with nFPM
5. Updatecli to premt trivy failing from fixable issues
