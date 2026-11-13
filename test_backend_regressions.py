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


def load_backend_module(name, relative_path, config, dependencies=None):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {relative_path}")
    module = importlib.util.module_from_spec(spec)
    overrides = {"backend.config": config, **(dependencies or {})}
    original_modules = {key: sys.modules.get(key) for key in overrides}
    sys.modules.update(overrides)
    try:
        spec.loader.exec_module(module)
    finally:
        for key, original in original_modules.items():
            if original is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = original
    return module


class OptimizerRiskTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse((ROOT / "backend/engines/portfolio_optimizer.py").read_text(encoding="utf-8"))
        allocate = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_allocate_capital")
        namespace = {"MIN_ALLOCATION": 5000, "MAX_SL_RISK_PCT": 0.03}
        exec(compile(ast.Module(body=[allocate], type_ignores=[]), "<optimizer_allocation>", "exec"), namespace)
        self.allocate = namespace["_allocate_capital"]

    def candidate(self, symbol, price=100000.0, stop=95000.0):
        return dict(
            symbol=symbol, company_name=symbol, price=price, stop_loss=stop,
            target_base=price * 1.1, rr_ratio=2.0, score=90.0,
            confidence=90.0, signal="BUY", components={}, power_score=1.0,
        )

    def test_unaffordable_shares_are_skipped(self):
        candidates = [self.candidate("A.NS"), self.candidate("B.NS")]
        self.assertEqual(self.allocate(candidates, 50000, 2, {"max_pct_per_stock": 0.25}), [])

    def test_risk_cap_that_allows_zero_shares_is_respected(self):
        candidates = [self.candidate("A.NS", price=10000, stop=1000)]
        self.assertEqual(self.allocate(candidates, 50000, 1, {"max_pct_per_stock": 0.25}), [])

    def test_valid_allocations_respect_budget_and_stop_risk(self):
        candidates = [self.candidate("A.NS", 100, 95), self.candidate("B.NS", 200, 190)]
        allocations = self.allocate(candidates, 50000, 2, {"max_pct_per_stock": 0.25})
        self.assertEqual(len(allocations), 2)
        self.assertLessEqual(sum(row["invested"] for row in allocations), 50000)
        for row in allocations:
            self.assertLessEqual(row["invested"], 12500)
            self.assertLessEqual(row["sl_risk"], 1500)


class TrailingStopTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse((ROOT / "backend/engines/outcome_tracker.py").read_text(encoding="utf-8"))
        evaluate = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_evaluate_trailing_stop")
        namespace = {}
        exec(compile(ast.Module(body=[evaluate], type_ignores=[]), "<trailing_stop>", "exec"), namespace)
        self.evaluate = namespace["_evaluate_trailing_stop"]

    def run_candles(self, candles, is_buy=True):
        import yfinance as yf

        history = pd.DataFrame(candles, index=pd.date_range("2026-11-12", periods=len(candles), tz="Asia/Kolkata"))
        with patch.object(yf, "Ticker") as ticker:
            ticker.return_value.history.return_value = history
            return self.evaluate(
                "TEST.NS", date(2026, 11, 11), len(candles), 100,
                95 if is_buy else 105, 110 if is_buy else 90, is_buy,
                close_at_horizon=False,
            )

    def test_long_original_stop_precedes_same_bar_target(self):
        result = self.run_candles([dict(Open=100, High=112, Low=94, Close=105)])
        self.assertEqual((result[0], result[4]), ("LOSS", 95))

    def test_short_original_stop_precedes_same_bar_target(self):
        result = self.run_candles([dict(Open=100, High=106, Low=88, Close=95)], is_buy=False)
        self.assertEqual((result[0], result[4]), ("LOSS", 105))

    def test_new_breakeven_stop_is_not_applied_retroactively(self):
        result = self.run_candles([dict(Open=100, High=112, Low=99, Close=108)])
        self.assertEqual(result[0], "OPEN")

    def test_armed_breakeven_stop_applies_on_following_bar(self):
        result = self.run_candles([
            dict(Open=100, High=112, Low=99, Close=108),
            dict(Open=105, High=106, Low=99, Close=101),
        ])
        self.assertEqual((result[0], result[4]), ("BREAKEVEN", 100))

    def test_gap_through_armed_stop_uses_open_price(self):
        result = self.run_candles([
            dict(Open=100, High=112, Low=99, Close=108),
            dict(Open=97, High=99, Low=96, Close=98),
        ])
        self.assertEqual((result[0], result[4]), ("LOSS", 97))

    def test_close_fetch_does_not_substitute_a_later_date(self):
        import logging
        import yfinance as yf
        from datetime import timedelta

        tree = ast.parse((ROOT / "backend/engines/outcome_tracker.py").read_text(encoding="utf-8"))
        fetch = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_fetch_close_price")
        namespace = {"yf": yf, "timedelta": timedelta, "logger": logging.getLogger("test.price")}
        exec(compile(ast.Module(body=[fetch], type_ignores=[]), "<fetch_close>", "exec"), namespace)
        history = pd.DataFrame({"Close": [110]}, index=pd.DatetimeIndex(["2026-11-12"], tz="Asia/Kolkata"))
        with patch.object(yf, "Ticker") as ticker:
            ticker.return_value.history.return_value = history
            self.assertIsNone(namespace["_fetch_close_price"]("TEST.NS", date(2026, 11, 11)))
            self.assertEqual(namespace["_fetch_close_price"]("TEST.NS", date(2026, 11, 12)), 110)


class SchedulerAllocationTests(unittest.TestCase):
    def test_market_interval_is_not_paused_outside_market_hours(self):
        import logging
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.interval import IntervalTrigger
        from apscheduler.triggers.cron import CronTrigger

        tree = ast.parse((ROOT / "backend/data/scheduler.py").read_text(encoding="utf-8"))
        setup = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "setup_scheduler")
        scheduler = AsyncIOScheduler(timezone=pytz.timezone("Asia/Kolkata"))
        namespace = {
            "scheduler": scheduler, "datetime": datetime, "IST": pytz.timezone("Asia/Kolkata"),
            "IntervalTrigger": IntervalTrigger, "CronTrigger": CronTrigger,
            "is_market_open": lambda: False, "logger": logging.getLogger("test.scheduler"),
            "settings": SimpleNamespace(market_data_interval_minutes=5, news_refresh_interval_minutes=10,
                fundamentals_refresh_hour=18, morning_briefing_hour=8, morning_briefing_minute=45),
        }
        async def job():
            pass

        for node in ast.walk(setup):
            if isinstance(node, ast.Name) and node.id.startswith("job_"):
                namespace[node.id] = job
        exec(compile(ast.Module(body=[setup], type_ignores=[]), "<scheduler_setup>", "exec"), namespace)
        namespace["setup_scheduler"]()
        self.assertIsNotNone(scheduler.get_job("market_data").next_run_time)

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


class ScoreMappingTests(unittest.TestCase):
    def test_all_scan_writers_use_the_canonical_mapping(self):
        counts = {}
        for relative_path in ("backend/api/routes/analysis.py", "backend/api/routes/screener.py", "backend/data/scheduler.py"):
            tree = ast.parse((ROOT / relative_path).read_text(encoding="utf-8"))
            counts[relative_path] = sum(
                isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "AnalysisScore"
                and node.func.attr == "from_results" for node in ast.walk(tree)
            )
        self.assertEqual(list(counts.values()), [1, 1, 2])

    def test_horizon_targets_regime_and_shadow_fields_are_retained(self):
        from backend.models.schemas import AnalysisScore

        analysis = dict(
            targets_5d={"conservative": 110, "base": 120, "aggressive": 130},
            targets_10d={"conservative": 140, "base": 150, "aggressive": 160},
            signal="HOLD", shadow_signal="BUY", kill_switch_active=True,
            regime="SIDEWAYS", confidence=75,
            components={"technical": 80, "fundamental": 70, "sentiment": 65},
        )
        technical = dict(close=100, signals=["Trend"], atr=5, trend_score=80, reversion_score=60, adx=22)
        record = AnalysisScore.from_results("TEST.NS", analysis, technical)
        self.assertEqual((record.target_base_5d, record.target_base_10d), (120, 150))
        self.assertEqual((record.regime, record.shadow_signal, record.kill_switch_active), ("SIDEWAYS", "BUY", 1))
        self.assertEqual((record.trend_score, record.reversion_score, record.adx), (80, 60, 22))


class FundamentalsPersistenceTests(DatabaseIsolationTests):
    async def test_upsert_saves_sector_and_preserves_known_values(self):
        from backend.models.schemas import FundamentalData

        config = ModuleType("backend.config")
        config.settings = SimpleNamespace()
        fundamentals = load_backend_module("test_fundamentals", "backend/data/fundamentals.py", config)
        await self.database.init_db()
        async with self.database.AsyncSessionLocal() as session:
            await fundamentals.upsert_fundamentals(session, "TEST.NS", {"sector": "Technology", "pe_ratio": 20})
            await session.commit()
        async with self.database.AsyncSessionLocal() as session:
            await fundamentals.upsert_fundamentals(session, "TEST.NS", {"sector": None, "pe_ratio": 22, "unmapped": 1})
            await session.commit()
        async with self.database.AsyncSessionLocal() as session:
            record = (await session.execute(select(FundamentalData))).scalar_one()
            self.assertEqual(record.sector, "Technology")
            self.assertEqual(record.pe_ratio, 22)


class OutcomeScopeTests(DatabaseIsolationTests):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        from backend.models.schemas import SignalOutcome

        self.Outcome = SignalOutcome
        await self.database.init_db()
        config = ModuleType("backend.config")
        config.IST = pytz.timezone("Asia/Kolkata")
        tracker = ModuleType("backend.engines.outcome_tracker")
        tracker.run_outcome_check = AsyncMock()
        self.learn = load_backend_module(
            "test_learn", "backend/api/routes/learn.py", config,
            {"backend.models.database": self.database, "backend.engines.outcome_tracker": tracker},
        )
        async with self.database.AsyncSessionLocal() as session:
            for symbol, shadow, deployed, signal, price, pnl, outcome in (
                ("VISIBLE.NS", 0, False, "BUY", 105, 5, "WIN"),
                ("SHADOW.NS", 1, False, "BUY", 110, 10, "WIN"),
                ("PAPER.NS", 0, True, "BUY", 95, -5, "LOSS"),
                ("LEGACY.NS", 0, False, "SELL", 90, -10, "WIN"),
            ):
                session.add(SignalOutcome(
                    symbol=symbol, is_shadow=shadow, is_deployed=deployed, signal=signal,
                    entry_price=100, price_at_check=price, pnl_percent=pnl, outcome=outcome,
                    entry_date=datetime.utcnow(), check_day=5,
                ))
            await session.commit()
            legacy = (await session.execute(select(SignalOutcome).where(SignalOutcome.symbol == "LEGACY.NS"))).scalar_one()
            legacy.is_shadow = None
            await session.commit()

    async def test_stats_and_recent_rows_use_identical_scopes(self):
        for scope, expected in (("visible", 3), ("shadow", 1), ("paper", 1), ("all", 4)):
            with self.subTest(scope=scope):
                async with self.database.AsyncSessionLocal() as session:
                    stats = await self.learn.get_learn_stats(days=90, check_day=5, scope=scope, db=session)
                    recent = await self.learn.get_recent_outcomes(limit=50, check_day=5, scope=scope, db=session)
                self.assertEqual(stats["total_signals"], expected)
                self.assertEqual(len(recent), expected)
                self.assertEqual(stats["scope"], scope)
                legacy = next((row for row in recent if row["symbol"] == "LEGACY.NS"), None)
                if legacy:
                    self.assertEqual(legacy["pnl_percent"], 10)

    async def test_report_uses_same_scope_as_learning_stats(self):
        config = ModuleType("backend.config")
        config.IST = pytz.timezone("Asia/Kolkata")
        report = load_backend_module(
            "test_report", "backend/engines/report_generator.py", config,
            {"backend.models.database": self.database},
        )
        async with self.database.AsyncSessionLocal() as session:
            session.add(self.Outcome(
                symbol="FLAT.NS", signal="BUY", entry_price=100, price_at_check=100,
                pnl_percent=0, outcome="BREAKEVEN", is_shadow=0,
                entry_date=datetime.utcnow(), check_day=5,
            ))
            await session.commit()
        captured = []
        class CapturingReport(report.ATBotReport):
            def cell(self, *args, **kwargs):
                captured.append(str(args[2] if len(args) > 2 else kwargs.get("text", "")))
                return super().cell(*args, **kwargs)

        with TemporaryDirectory() as directory, patch.object(report, "REPORTS_DIR", directory), patch.object(report, "ATBotReport", CapturingReport):
            for scope in ("visible", "shadow", "paper", "all"):
                captured.clear()
                path = await report.generate_accuracy_report(days=90, check_day=5, scope=scope)
                self.assertTrue(Path(path).is_file())
                self.assertIn(f"_{scope}_D5_", Path(path).name)
                self.assertIn(f"Scope: {scope}", captured)
                expected_count = {"visible": 4, "shadow": 1, "paper": 1, "all": 5}[scope]
                self.assertTrue(any(f"{expected_count} signals tracked | {expected_count} resolved" in text for text in captured))
                if scope == "visible":
                    self.assertIn("+3.33%", captured)

    async def test_report_endpoint_accepts_all_dashboard_horizons(self):
        import httpx
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(self.learn.router)
        generator = ModuleType("backend.engines.report_generator")
        with TemporaryDirectory() as directory:
            path = Path(directory) / "report.pdf"
            path.write_bytes(b"%PDF-1.4\n")
            generator.generate_accuracy_report = AsyncMock(return_value=str(path))
            with patch.dict(sys.modules, {"backend.engines.report_generator": generator}):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                    for horizon in (1, 2, 5, 10, 50, 100):
                        response = await client.get(f"/learn/report?check_day={horizon}&scope=shadow")
                        self.assertEqual(response.status_code, 200)
                    response = await client.get("/learn/report?scope=invalid")
                    self.assertEqual(response.status_code, 422)

    async def test_invalid_scope_is_rejected(self):
        with self.assertRaises(ValueError):
            self.Outcome.scope_filter("invalid")


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

    async def run_at(self, day, price):
        instant = pytz.timezone("Asia/Kolkata").localize(datetime.combine(day, datetime.min.time()).replace(hour=19))
        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return instant.astimezone(tz) if tz else instant.replace(tzinfo=None)

        with patch.object(self.tracker, "datetime", Clock), patch.object(
            self.tracker, "CHECK_DAYS", [1]
        ), patch.object(self.tracker, "_refresh_paper_positions", new=AsyncMock()), patch.object(
            self.tracker, "_fetch_close_price", return_value=price
        ) as fetch:
            count = await self.tracker.run_outcome_check()
            return count, fetch.call_args_list

    async def test_missed_outcome_is_backfilled_at_original_due_date(self):
        from backend.models.schemas import SignalOutcome

        async with self.database.AsyncSessionLocal() as session:
            await self.add_score(session, "OLD.NS", timestamp=datetime(2026, 11, 2, 10))
            await session.commit()
        count, calls = await self.run_at(date(2026, 11, 6), 105)
        self.assertEqual(count, 1)
        self.assertEqual(calls[0].args, ("OLD.NS", date(2026, 11, 3)))
        async with self.database.AsyncSessionLocal() as session:
            outcome = (await session.execute(select(SignalOutcome))).scalar_one()
            self.assertEqual(outcome.pnl_percent, 5)

    async def test_missing_price_is_retried_on_later_day_without_duplicates(self):
        from backend.models.schemas import SignalOutcome

        async with self.database.AsyncSessionLocal() as session:
            await self.add_score(session, "RETRY.NS", timestamp=datetime(2026, 11, 2, 10))
            await session.commit()
        await self.run_at(date(2026, 11, 3), None)
        await self.run_at(date(2026, 11, 5), 105)
        count, calls = await self.run_at(date(2026, 11, 6), 106)
        self.assertEqual((count, calls), (0, []))
        async with self.database.AsyncSessionLocal() as session:
            outcome = (await session.execute(select(SignalOutcome))).scalar_one()
            self.assertNotEqual(outcome.outcome, "OPEN")
            self.assertEqual(outcome.price_at_check, 105)

    async def test_pending_older_scan_survives_newer_same_day_hold(self):
        from backend.models.schemas import SignalOutcome

        async with self.database.AsyncSessionLocal() as session:
            original = await self.add_score(session, "RETRY.NS", timestamp=datetime(2026, 11, 2, 10))
            original_id = original.id
            await session.commit()
        await self.run_at(date(2026, 11, 3), None)
        async with self.database.AsyncSessionLocal() as session:
            await self.add_score(session, "RETRY.NS", signal="HOLD", timestamp=datetime(2026, 11, 2, 11))
            await session.commit()
        await self.run_at(date(2026, 11, 5), 105)
        async with self.database.AsyncSessionLocal() as session:
            row = (await session.execute(select(SignalOutcome))).scalar_one()
            self.assertEqual(row.analysis_score_id, original_id)
            self.assertNotEqual(row.outcome, "OPEN")

    async def test_profitable_sell_has_positive_stored_pnl(self):
        from backend.models.schemas import SignalOutcome

        async with self.database.AsyncSessionLocal() as session:
            await self.add_score(session, "SHORT.NS", signal="SELL", stop_loss=105, timestamp=datetime(2026, 11, 2, 10))
            await session.commit()
        await self.run_at(date(2026, 11, 4), 90)
        async with self.database.AsyncSessionLocal() as session:
            outcome = (await session.execute(select(SignalOutcome))).scalar_one()
            self.assertEqual((outcome.pnl_amount, outcome.pnl_percent), (10, 10))
            self.assertEqual(outcome.outcome, "WIN")
            self.assertEqual(outcome.price_return_percent, -10)

    async def test_legacy_and_new_short_returns_use_prices_consistently(self):
        from backend.models.schemas import SignalOutcome

        for stored_pnl in (-10, 10):
            outcome = SignalOutcome(signal="SELL", entry_price=100, price_at_check=90, pnl_percent=stored_pnl)
            self.assertEqual(outcome.trade_return_percent, 10)
            self.assertEqual(outcome.price_return_percent, -10)

    async def test_kill_switch_counts_legacy_profitable_shorts_as_wins(self):
        from backend.models.schemas import SignalOutcome

        async with self.database.AsyncSessionLocal() as session:
            for index in range(20):
                session.add(SignalOutcome(
                    symbol=f"SHORT{index}.NS", signal="SELL", entry_price=100,
                    price_at_check=90, pnl_percent=-10, outcome="WIN",
                    regime="SIDEWAYS", is_shadow=0, check_day=5, entry_date=datetime.utcnow(),
                ))
            await session.commit()
        self.assertEqual(await self.tracker.refresh_sideways_win_rate(), (1.0, 20))

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
            "upsert_fundamentals": AsyncMock(),
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