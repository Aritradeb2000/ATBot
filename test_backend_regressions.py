import importlib.util
from datetime import datetime
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

import pandas as pd
import pytz
from sqlalchemy import text


ROOT = Path(__file__).resolve().parent


def load_backend_module(name, relative_path, config):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {relative_path}")
    module = importlib.util.module_from_spec(spec)
    original_config = sys.modules.get("backend.config")
    sys.modules["backend.config"] = config
    try:
        spec.loader.exec_module(module)
    finally:
        if original_config is None:
            sys.modules.pop("backend.config", None)
        else:
            sys.modules["backend.config"] = original_config
    return module


class DatabaseIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        database_path = Path(directory.name) / "isolation.db"
        config = ModuleType("backend.config")
        config.settings = SimpleNamespace(
            database_url=f"sqlite+aiosqlite:///{database_path.as_posix()}",
            debug=False,
        )
        self.database = load_backend_module(
            "isolation_database", "backend/models/database.py", config
        )
        self.addAsyncCleanup(self.database.engine.dispose)
        async with self.database.engine.begin() as connection:
            await connection.execute(text("CREATE TABLE isolation_probe (id INTEGER PRIMARY KEY)"))

    async def test_sessions_do_not_see_uncommitted_writes(self):
        async with self.database.AsyncSessionLocal() as first, self.database.AsyncSessionLocal() as second:
            await first.execute(text("INSERT INTO isolation_probe VALUES (1)"))
            count = await second.scalar(text("SELECT COUNT(*) FROM isolation_probe"))
            self.assertEqual(count, 0)
            await second.rollback()
            await first.rollback()

    async def test_rollback_does_not_discard_another_sessions_write(self):
        async with self.database.AsyncSessionLocal() as first, self.database.AsyncSessionLocal() as second:
            await first.execute(text("INSERT INTO isolation_probe VALUES (1)"))
            await second.execute(text("SELECT COUNT(*) FROM isolation_probe"))
            await second.rollback()
            await first.commit()

        async with self.database.AsyncSessionLocal() as session:
            rows = list((await session.execute(text("SELECT id FROM isolation_probe"))).scalars())
        self.assertEqual(rows, [1])


class MarketDataFreshnessTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        config = ModuleType("backend.config")
        config.settings = SimpleNamespace(
            market_open_hour=9, market_open_minute=15,
            market_close_hour=15, market_close_minute=30,
        )
        config.IST = pytz.timezone("Asia/Kolkata")
        config.INDEX_TICKERS = {}
        config.GLOBAL_CUES = {}
        self.market_data = load_backend_module(
            "freshness_market_data", "backend/data/market_data.py", config
        )
        self.market_data.LOCAL_DATA_DIR = str(self.directory)
        self.freeze_time("2026-11-11T18:00:00+05:30")

    def freeze_time(self, timestamp):
        fixed_time = datetime.fromisoformat(timestamp)

        class FrozenDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                if tz is not None:
                    return fixed_time.astimezone(tz)
                return fixed_time.replace(tzinfo=None)

        clock = patch.object(self.market_data, "datetime", FrozenDateTime)
        clock.start()
        self.addCleanup(clock.stop)

    def write_local(self, dates, volumes=None):
        bars = pd.DataFrame({
            "Date": dates,
            "Open": [100.0] * len(dates),
            "High": [102.0] * len(dates),
            "Low": [99.0] * len(dates),
            "Close": [101.0] * len(dates),
            "Volume": volumes if volumes is not None else [1000] * len(dates),
        })
        bars.to_csv(self.directory / "TEST.csv", index=False)

    def online_bars(self):
        return pd.DataFrame(
            {"Open": [110.0], "High": [112.0], "Low": [109.0], "Close": [111.0], "Volume": [2000]},
            index=pd.DatetimeIndex(["2026-11-11"], tz="Asia/Kolkata"),
        )

    def assert_online_fallback(self):
        with patch.object(self.market_data.yf, "Ticker") as ticker:
            ticker.return_value.history.return_value = self.online_bars()
            result = self.market_data.fetch_ohlcv("TEST.NS")
            ticker.assert_called_once_with("TEST.NS")
            ticker.return_value.history.assert_called_once_with(
                period="6mo", interval="1d", auto_adjust=True
            )
        self.assertIsNotNone(result)
        self.assertEqual(result["Close"].iloc[-1], 111.0)

    def assert_local_used(self):
        with patch.object(self.market_data.yf, "Ticker") as ticker:
            result = self.market_data.fetch_ohlcv("TEST.NS")
            ticker.assert_not_called()
        self.assertIsNotNone(result)
        self.assertEqual(result["Close"].iloc[-1], 101.0)

    def test_years_old_cache_falls_back_to_live_provider(self):
        self.write_local(["2020-01-01", "2020-01-02"])
        self.assert_online_fallback()

    def test_previous_day_cache_is_stale_after_market_close(self):
        self.write_local(["2026-11-10"])
        self.assert_online_fallback()

    def test_fresh_completed_session_uses_local_cache(self):
        self.write_local(["2026-11-11"])
        self.assert_local_used()

    def test_previous_session_is_accepted_before_market_open(self):
        self.freeze_time("2026-11-11T08:00:00+05:30")
        self.write_local(["2026-11-10"])
        self.assert_local_used()

    def test_friday_cache_is_accepted_on_weekends_and_monday_premarket(self):
        self.write_local(["2026-11-06"])
        for timestamp in (
            "2026-11-07T18:00:00+05:30",
            "2026-11-08T08:00:00+05:30",
            "2026-11-09T08:00:00+05:30",
        ):
            with self.subTest(timestamp=timestamp):
                self.freeze_time(timestamp)
                self.assert_local_used()

    def test_market_hours_bypass_even_same_day_local_cache(self):
        self.freeze_time("2026-11-11T10:00:00+05:30")
        self.write_local(["2026-11-11"])
        self.assert_online_fallback()

    def test_invalid_latest_bar_does_not_make_old_data_fresh(self):
        self.write_local(["2026-11-10", "2026-11-11"], volumes=[1000, 0])
        self.assert_online_fallback()

    def test_future_dated_cache_is_rejected(self):
        self.write_local(["2026-11-12"])
        self.assert_online_fallback()

    def test_stale_cache_is_not_returned_when_provider_fails(self):
        self.write_local(["2020-01-01"])
        with patch.object(self.market_data.yf, "Ticker", side_effect=RuntimeError("offline")):
            self.assertIsNone(self.market_data.fetch_ohlcv("TEST.NS"))

    def test_utc_dates_are_checked_in_indian_market_timezone(self):
        self.write_local(["2026-11-10T18:30:00+00:00"])
        self.assert_local_used()

    def test_intraday_requests_do_not_use_daily_local_cache(self):
        self.write_local(["2026-11-11"])
        with patch.object(self.market_data.yf, "Ticker") as ticker:
            ticker.return_value.history.return_value = self.online_bars()
            self.market_data.fetch_ohlcv("TEST.NS", interval="5m", period="1d")
            ticker.return_value.history.assert_called_once_with(
                period="1d", interval="5m", auto_adjust=True
            )


if __name__ == "__main__":
    unittest.main()