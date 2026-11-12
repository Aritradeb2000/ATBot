import logging
import math
from datetime import datetime, time, timedelta, timezone
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
import asyncio

from backend.models.schemas import AnalysisScore, PaperPosition, FundamentalData, UserSettings
from backend.config import IST, MAX_SECTOR_POSITIONS, MAX_TOTAL_POSITIONS

logger = logging.getLogger(__name__)

class PortfolioManager:
    def __init__(self, session: AsyncSession, capital: float = 100000.0):
        self.session = session
        self.capital = capital
        self.open_positions = []
        
    async def init(self):
        self.open_positions = await self._fetch_open_positions()

    async def _fetch_open_positions(self) -> List[PaperPosition]:
        """Fetch open paper positions, independent of signal outcome horizons."""
        query = select(PaperPosition).where(PaperPosition.status == "OPEN")
        res = await self.session.execute(query)
        return res.scalars().all()

    async def _get_sector(self, symbol: str) -> str:
        """Fetch sector for a symbol."""
        res = await self.session.execute(
            select(FundamentalData).where(FundamentalData.symbol == symbol)
        )
        fund = res.scalars().first()
        return fund.sector if fund and fund.sector else "Unknown"

    async def allocate(self, daily_scores: List[AnalysisScore], regime: str = "SIDEWAYS") -> List[AnalysisScore]:
        """
        Takes a list of fresh AnalysisScore objects (for today), ranks them,
        and applies sector and total portfolio caps before allocating capital.
        """
        if not math.isfinite(self.capital) or self.capital <= 0:
            raise ValueError("Portfolio capital must be finite and positive")

        sector_counts = {}
        total_open = len(self.open_positions)
        open_symbols = {position.symbol for position in self.open_positions}
        available_capital = max(0.0, self.capital - sum(
            position.quantity * position.entry_price for position in self.open_positions
        ))
        for position in self.open_positions:
            sector_counts[position.sector] = sector_counts.get(position.sector, 0) + 1

        existing = (await self.session.execute(select(PaperPosition))).scalars().all()
        allocated_ids = {position.analysis_score_id for position in existing}
        allocated_days = {
            (position.symbol, position.entry_date.replace(tzinfo=timezone.utc).astimezone(IST).date())
            for position in existing
        }
        latest_scores = {}
        for score in daily_scores:
            previous = latest_scores.get(score.symbol)
            if previous is None or (score.timestamp, score.id) > (previous.timestamp, previous.id):
                latest_scores[score.symbol] = score
        buy_signals = [
            score for score in latest_scores.values()
            if score.signal in ("BUY", "STRONG BUY", "STRONG_BUY")
            and not score.kill_switch_active
        ]
        buy_signals.sort(key=lambda score: score.composite_score or 0, reverse=True)

        for score in buy_signals:
            entry_day = score.timestamp.replace(tzinfo=timezone.utc).astimezone(IST).date()
            if score.id in allocated_ids or score.symbol in open_symbols or (score.symbol, entry_day) in allocated_days:
                continue
            if total_open >= MAX_TOTAL_POSITIONS:
                logger.info(f"  Skipping {score.symbol} - Max total positions ({MAX_TOTAL_POSITIONS}) reached.")
                continue

            sector = await self._get_sector(score.symbol)
            if sector_counts.get(sector, 0) >= MAX_SECTOR_POSITIONS:
                logger.info(f"  Skipping {score.symbol} - Max sector positions ({MAX_SECTOR_POSITIONS}) reached for {sector}.")
                continue

            if (
                score.current_price is None or score.stop_loss is None
                or not math.isfinite(score.current_price) or not math.isfinite(score.stop_loss)
                or not 0 < score.stop_loss < score.current_price
            ):
                continue
            position_regime = score.regime or regime
            regime_risk_mult = {"BULL": 1.0, "SIDEWAYS": 0.85, "BEAR": 0.60}.get(position_regime, 0.85)
            regime_max_alloc = {"BULL": 0.20, "SIDEWAYS": 0.15, "BEAR": 0.10}.get(position_regime, 0.15)
            
            risk_amount = self.capital * 0.01 * regime_risk_mult
            risk_per_share = score.current_price - score.stop_loss
            
            max_shares_by_risk = int(risk_amount / risk_per_share) if risk_per_share > 0 else 0
            max_shares_by_cap = int((self.capital * regime_max_alloc) / score.current_price) if score.current_price else 0
            
            shares = min(max_shares_by_risk, max_shares_by_cap, int(available_capital / score.current_price))
            
            if shares > 0:
                position = PaperPosition(
                    analysis_score_id=score.id, symbol=score.symbol, sector=sector,
                    quantity=shares, entry_date=score.timestamp,
                    entry_price=score.current_price, stop_loss=score.stop_loss,
                    target_conservative=score.target_low_5d or score.target_base_5d,
                    regime=position_regime, status="OPEN",
                )
                self.session.add(position)
                self.open_positions.append(position)
                open_symbols.add(score.symbol)
                allocated_ids.add(score.id)
                allocated_days.add((score.symbol, entry_day))
                available_capital -= shares * score.current_price
                sector_counts[sector] = sector_counts.get(sector, 0) + 1
                total_open += 1
                logger.info(f"  Paper allocation {score.symbol} - Sector: {sector}, Shares: {shares}.")

        await self.session.flush()
        return daily_scores

async def run_portfolio_allocation_for_today():
    from backend.models.database import AsyncSessionLocal

    today = datetime.now(IST).date()
    start = IST.localize(datetime.combine(today, time.min)).astimezone(timezone.utc).replace(tzinfo=None)
    end = IST.localize(datetime.combine(today + timedelta(days=1), time.min)).astimezone(timezone.utc).replace(tzinfo=None)
    
    async with AsyncSessionLocal() as db:
        res = await db.execute(
            select(AnalysisScore).where(
                and_(
                    AnalysisScore.timestamp >= start,
                    AnalysisScore.timestamp < end,
                )
            )
        )
        scores = res.scalars().all()
        
        if not scores:
            logger.info("No scores found for today to allocate.")
            return
            
        user = (await db.execute(select(UserSettings).where(UserSettings.user_id == "default"))).scalar_one_or_none()
        capital = user.capital if user is not None else 100000.0
        pm = PortfolioManager(db, capital=capital)
        await pm.init()
        await pm.allocate(scores)
        await db.commit()
        logger.info(f"Paper portfolio allocation complete for {len(scores)} signals today.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_portfolio_allocation_for_today())
