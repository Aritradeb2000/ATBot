import ast
import asyncio
import importlib.util
from datetime import date, datetime
from pathlib import Path
import sys
import threading
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import pandas as pd
import pytz
from sqlalchemy import select, text
from starlette.concurrency import run_in_threadpool


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


class SchedulerAllocationTests(unittest.TestCase):
    def test_daily_screener_awaits_portfolio_allocation(self):
        tree = ast.parse((ROOT / "backend/data/scheduler.py").read_text(encoding="utf-8"))
        job = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "job_daily_screener")
        calls = [
            node.value for node in ast.walk(job)
            if isinstance(node, ast.Await) and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id == "run_portfolio_allocation_for_today"
        ]
        self.assertEqual(len(calls), 1)


class SchedulerRefreshTests(unittest.IsolatedAsyncioTestCase):
    async def test_recurring_index_refresh_runs_providers_in_worker_threads(self):
        import logging

        tree = ast.parse((ROOT / "backend/data/scheduler.py").read_text(encoding="utf-8"))
        refresh = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "job_refresh_index_data")
        thread_ids = []
        def provider():
            thread_ids.append(threading.get_ident())
            return {"fresh": True}

        cache = {"last_updated": {}}
        namespace = {
            "run_in_threadpool": run_in_threadpool, "_cache": cache,
            "fetch_index_data": provider, "get_india_vix": provider,
            "get_market_breadth": provider, "datetime": datetime,
            "IST": pytz.timezone("Asia/Kolkata"), "logger": logging.getLogger("test.scheduler"),
        }
        exec(compile(ast.Module(body=[refresh], type_ignores=[]), "<scheduler_refresh>", "exec"), namespace)
        await namespace["job_refresh_index_data"]()
        self.assertEqual(len(thread_ids), 3)
        self.assertTrue(all(thread_id != threading.get_ident() for thread_id in thread_ids))
        self.assertEqual(cache["indices"], {"fresh": True})
        self.assertIn("indices", cache["last_updated"])


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


class PortfolioPersistenceTests(DatabaseIsolationTests):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        from backend.models.schemas import AnalysisScore, FundamentalData, PaperPosition

        self.Score = AnalysisScore
        self.Position = PaperPosition
        self.Fundamental = FundamentalData
        config = ModuleType("backend.config")
        config.IST = pytz.timezone("Asia/Kolkata")
        config.MAX_SECTOR_POSITIONS = 2
        config.MAX_TOTAL_POSITIONS = 5
        self.portfolio = load_backend_module(
            "test_portfolio_manager", "backend/engines/portfolio_manager.py", config
        )
        await self.database.init_db()

    async def add_score(self, session, symbol, **overrides):
        values = dict(
            symbol=symbol, timestamp=datetime(2026, 11, 12, 10), signal="BUY",
            composite_score=80, current_price=100, stop_loss=95,
            target_low_5d=110, regime="BULL", kill_switch_active=0,
        )
        values.update(overrides)
        score = self.Score(**values)
        session.add(score)
        await session.flush()
        return score

    async def allocate(self, session, scores, capital=100000):
        manager = self.portfolio.PortfolioManager(session, capital=capital)
        await manager.init()
        await manager.allocate(scores)
        await session.commit()

    async def test_quantity_survives_reload_and_rerun_does_not_duplicate(self):
        async with self.database.AsyncSessionLocal() as session:
            score = await self.add_score(session, "TEST.NS")
            await self.allocate(session, [score])
        async with self.database.AsyncSessionLocal() as session:
            scores = list((await session.execute(select(self.Score))).scalars())
            await self.allocate(session, scores)
            positions = list((await session.execute(select(self.Position))).scalars())
            self.assertEqual(len(positions), 1)
            self.assertEqual(positions[0].quantity, 200)
            self.assertEqual(positions[0].status, "OPEN")

    async def test_sector_caps_apply_to_persisted_open_positions(self):
        async with self.database.AsyncSessionLocal() as session:
            scores = [await self.add_score(session, f"SECTOR{index}.NS") for index in range(3)]
            await self.allocate(session, scores)
        async with self.database.AsyncSessionLocal() as session:
            extra = await self.add_score(session, "EXTRA.NS")
            await self.allocate(session, [extra])
            positions = list((await session.execute(select(self.Position))).scalars())
            self.assertEqual(len(positions), 2)

    async def test_latest_hold_prevents_allocating_an_older_buy(self):
        async with self.database.AsyncSessionLocal() as session:
            older = await self.add_score(session, "TEST.NS")
            newer = await self.add_score(session, "TEST.NS", signal="HOLD", timestamp=datetime(2026, 11, 12, 11))
            await self.allocate(session, [older, newer])
            self.assertIsNone((await session.execute(select(self.Position))).scalar_one_or_none())

    async def test_invalid_stops_and_shadow_signals_are_not_allocated(self):
        async with self.database.AsyncSessionLocal() as session:
            scores = [
                await self.add_score(session, "MISSING.NS", stop_loss=None),
                await self.add_score(session, "NEGATIVE.NS", stop_loss=-1),
                await self.add_score(session, "WRONGSIDE.NS", stop_loss=105),
                await self.add_score(session, "SHADOW.NS", kill_switch_active=1),
            ]
            await self.allocate(session, scores)
            self.assertEqual(list((await session.execute(select(self.Position))).scalars()), [])

    async def test_total_cap_and_remaining_capital_are_enforced(self):
        async with self.database.AsyncSessionLocal() as session:
            scores = []
            for index in range(6):
                symbol = f"STOCK{index}.NS"
                session.add(self.Fundamental(symbol=symbol, sector=f"Sector{index}"))
                scores.append(await self.add_score(session, symbol))
            await self.allocate(session, scores, capital=1000)
            positions = list((await session.execute(select(self.Position))).scalars())
            self.assertEqual(len(positions), 5)
            self.assertLessEqual(sum(position.quantity * position.entry_price for position in positions), 1000)


class PortfolioOutcomeTests(PortfolioPersistenceTests):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        config = ModuleType("backend.config")
        config.IST = pytz.timezone("Asia/Kolkata")
        with patch.dict(sys.modules, {"backend.models.database": self.database}):
            self.tracker = load_backend_module(
                "test_outcome_tracker", "backend/engines/outcome_tracker.py", config
            )

    async def test_open_position_is_preserved_and_closed_position_releases_capital(self):
        async with self.database.AsyncSessionLocal() as session:
            score = await self.add_score(session, "TEST.NS", timestamp=datetime(2026, 11, 11, 10))
            await self.allocate(session, [score])
        async with self.database.AsyncSessionLocal() as session:
            with patch.object(self.tracker, "_evaluate_trailing_stop", return_value=("OPEN", 1, 1, datetime(2026, 11, 12), 101)) as evaluate:
                await self.tracker._refresh_paper_positions(session, date(2026, 11, 12))
                self.assertFalse(evaluate.call_args.kwargs["close_at_horizon"])
            await session.commit()
            position = (await session.execute(select(self.Position))).scalar_one()
            self.assertEqual(position.status, "OPEN")
            with patch.object(self.tracker, "_evaluate_trailing_stop", return_value=("LOSS", -5, -5, datetime(2026, 11, 12), 95)):
                await self.tracker._refresh_paper_positions(session, date(2026, 11, 12))
            await session.commit()
        async with self.database.AsyncSessionLocal() as session:
            position = (await session.execute(select(self.Position))).scalar_one()
            self.assertEqual(position.status, "CLOSED")
            self.assertEqual(position.pnl_amount, -1000)
            manager = self.portfolio.PortfolioManager(session)
            await manager.init()
            self.assertEqual(manager.open_positions, [])

    async def test_tracker_prefers_allocated_score_over_newer_unallocated_scan(self):
        from backend.models.schemas import SignalOutcome

        entry_day = datetime.now(pytz.timezone("Asia/Kolkata")).date()
        entry_day -= pd.Timedelta(days=1)
        while entry_day.weekday() >= 5:
            entry_day -= pd.Timedelta(days=1)
        entry_timestamp = datetime.combine(entry_day, datetime.min.time()).replace(hour=10)
        async with self.database.AsyncSessionLocal() as session:
            allocated = await self.add_score(session, "TEST.NS", timestamp=entry_timestamp)
            await self.allocate(session, [allocated])
            await self.add_score(session, "TEST.NS", timestamp=entry_timestamp.replace(hour=11))
            allocated_id = allocated.id
            await session.commit()
        with patch.object(self.tracker, "CHECK_DAYS", [1]), patch.object(
            self.tracker, "_refresh_paper_positions", new=AsyncMock()
        ), patch.object(self.tracker, "_fetch_close_price", return_value=None):
            await self.tracker.run_outcome_check()
        async with self.database.AsyncSessionLocal() as session:
            outcome = (await session.execute(select(SignalOutcome))).scalar_one()
            self.assertEqual(outcome.analysis_score_id, allocated_id)
            self.assertTrue(outcome.is_deployed)
        with patch.object(self.tracker, "CHECK_DAYS", [1]), patch.object(
            self.tracker, "_refresh_paper_positions", new=AsyncMock()
        ), patch.object(self.tracker, "_fetch_close_price", return_value=101), patch.object(
            self.tracker, "_evaluate_trailing_stop", return_value=("WIN", 1, 1, entry_timestamp, 101)
        ):
            await self.tracker.run_outcome_check()
        async with self.database.AsyncSessionLocal() as session:
            outcome = (await session.execute(select(SignalOutcome))).scalar_one()
            self.assertTrue(outcome.is_deployed)
            self.assertEqual(outcome.trailing_outcome, "WIN")


class EndpointResponsivenessTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query
        from sqlalchemy.ext.asyncio import AsyncSession
        from typing import Optional

        from backend.models.schemas import AnalysisScore

        self.loop = asyncio.get_running_loop()
        self.started = asyncio.Event()
        self.release = threading.Event()
        self.addCleanup(self.release.set)
        self.worker_thread = None
        self.released_in_time = None
        scheduler = ModuleType("backend.data.scheduler")
        scheduler.get_cache = lambda: {}
        self.market = self.load_route("backend/api/routes/market.py", {
            "APIRouter": APIRouter, "Query": Query, "get_cache": scheduler.get_cache,
            "fetch_ohlcv": self.blocking_provider, "get_fii_dii_history": self.blocking_provider,
            "yf": SimpleNamespace(Ticker=lambda symbol: SimpleNamespace(history=self.blocking_provider)),
            "logging": __import__("logging"), "asyncio": asyncio,
        })
        self.database = SimpleNamespace(add=lambda record: None, commit=AsyncMock(), rollback=AsyncMock())
        self.analysis = self.load_route("backend/api/routes/analysis.py", {
            "APIRouter": APIRouter, "HTTPException": HTTPException, "Depends": Depends,
            "Optional": Optional, "AsyncSession": AsyncSession, "AnalysisScore": AnalysisScore,
            "run_in_threadpool": run_in_threadpool, "get_db": lambda: self.database,
            "fetch_ohlcv": self.blocking_provider,
            "fetch_fundamentals_yfinance": lambda symbol: {},
            "fetch_finnhub_news": lambda symbol: [],
            "get_cache": lambda: {}, "get_fii_dii_data": lambda: {},
            "analyze_technical": lambda frame: {"close": 101},
            "analyze_fundamental": lambda data: {}, "analyze_sentiment": lambda news, flow: {},
            "calculate_composite": lambda **kwargs: {"composite_score": 75, "signal": "BUY", "confidence": 0.8},
            "logging": __import__("logging"), "json": __import__("json"),
        })
        self.app = FastAPI()
        self.app.include_router(self.market.router)
        self.app.include_router(self.analysis.router)

    def load_route(self, relative_path, namespace):
        tree = ast.parse((ROOT / relative_path).read_text(encoding="utf-8"))
        tree.body = [node for node in tree.body if not isinstance(node, (ast.Import, ast.ImportFrom))]
        exec(compile(tree, str(ROOT / relative_path), "exec"), namespace)
        return SimpleNamespace(**namespace)

    def blocking_provider(self, *args, **kwargs):
        self.worker_thread = threading.get_ident()
        self.loop.call_soon_threadsafe(self.started.set)
        self.released_in_time = self.release.wait(timeout=2)
        return pd.DataFrame(
            {"Open": [100], "High": [102], "Low": [99], "Close": [101], "Volume": [1000]},
            index=pd.DatetimeIndex(["2026-11-12"], tz="Asia/Kolkata"),
        )

    async def request_while_provider_waits(self, path):
        import httpx

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://test") as client:
            request = asyncio.create_task(client.get(path))
            try:
                await asyncio.wait_for(self.started.wait(), timeout=3)
                self.assertNotEqual(self.worker_thread, threading.get_ident())
            finally:
                self.release.set()
            response = await asyncio.wait_for(request, timeout=3)
        self.assertTrue(self.released_in_time)
        self.assertEqual(response.status_code, 200)
        return response.json()

    async def test_daily_chart_fetch_does_not_block_event_loop(self):
        response = await self.request_while_provider_waits("/ohlcv/TEST.NS")
        self.assertEqual(response[0]["time"], "2026-11-12")
        self.assertEqual(response[0]["close"], 101)

    async def test_intraday_chart_preserves_unix_timestamps(self):
        response = await self.request_while_provider_waits("/ohlcv/TEST.NS?interval=5m")
        self.assertIsInstance(response[0]["time"], int)

    async def test_analysis_fetch_and_scoring_leave_event_loop_responsive(self):
        response = await self.request_while_provider_waits("/analyze/test.ns")
        self.assertEqual(response["symbol"], "TEST.NS")
        self.assertEqual(response["analysis"]["signal"], "BUY")
        self.database.commit.assert_awaited_once()

    async def test_vix_fetch_does_not_block_event_loop(self):
        response = await self.request_while_provider_waits("/market/vix-history")
        self.assertEqual(response[0]["vix"], 101)

    async def test_sector_fetch_does_not_block_event_loop(self):
        def history(**kwargs):
            current = self.blocking_provider()
            previous = current.copy()
            previous.index -= pd.Timedelta(days=1)
            previous["Close"] = 100
            return pd.concat([previous, current])

        self.market.yf.Ticker = lambda symbol: SimpleNamespace(history=history)
        response = await self.request_while_provider_waits("/market/sector-heatmap")
        self.assertEqual(len(response), 8)

    async def test_fii_history_fetch_does_not_block_event_loop(self):
        namespace = self.market.get_fii_dii_history_endpoint.__globals__
        def history(**kwargs):
            self.blocking_provider()
            return []

        with patch.dict(namespace, {"get_fii_dii_history": history}):
            response = await self.request_while_provider_waits("/market/fii-history")
        self.assertEqual(response, [])


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