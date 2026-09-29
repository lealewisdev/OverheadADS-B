"""Shared fixtures for the overheadadsb test suite."""

import pytest

from overheadadsb.poller import PollCache


class FakeAsyncpgPool:
    """Minimal stand-in for asyncpg.Pool.

    Records every `execute`/`fetchval` call it receives so tests can assert
    on the SQL that was sent, without needing a real Postgres instance.
    `fetch` returns plain dicts, which behave like asyncpg.Record for our
    purposes (both support `row["col"]` access).
    """

    def __init__(self, rows=None, fetchval_return=None):
        self.rows = rows or []
        self.fetchval_return = fetchval_return
        self.executed: list[tuple[str, tuple]] = []
        self.fetchval_calls: list[tuple[str, tuple]] = []
        self.closed = False

    async def execute(self, query, *args):
        self.executed.append((query, args))

    async def fetch(self, query, *args):
        return list(self.rows)

    async def fetchval(self, query, *args):
        self.fetchval_calls.append((query, args))
        return self.fetchval_return

    async def close(self):
        self.closed = True


@pytest.fixture
def fake_db_pool():
    """Factory so tests can construct a FakeAsyncpgPool with the rows/
    return value they need, e.g. `fake_db_pool(fetchval_return=5)`."""
    return FakeAsyncpgPool


@pytest.fixture
def poll_cache() -> PollCache:
    """A fresh PollCache per test.

    The app uses a module-level singleton (`overheadadsb.poller.poll_cache`)
    so its state -- the owner cache, sighting counts, loaded squawks and
    helicopter types -- persists across requests. Tests get their own
    instance so they can't leak state into each other.
    """
    return PollCache()


@pytest.fixture
def tiny_reference_data(tmp_path, monkeypatch):
    """Point config at small, known reference CSVs instead of the real
    (large, generated) bundled ones, so poller tests don't depend on
    exactly what's currently in the data files.

    See test_poller.test_load_reference_data_from_real_bundled_files for
    a smoke test against the real files.
    """
    from overheadadsb import config

    squawks_csv = tmp_path / "squawks.csv"
    squawks_csv.write_text(
        "squawk,function\n7700,Emergency\n7600,Radio failure\n1177,HEMS\n"
    )

    heli_csv = tmp_path / "heli.csv"
    heli_csv.write_text("EC35\nH125\nAW139\n")

    monkeypatch.setattr(config, "SQUAWKS_CSV", str(squawks_csv))
    monkeypatch.setattr(config, "ICAO_CSV", str(heli_csv))
    return squawks_csv, heli_csv
