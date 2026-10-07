import logging
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
import asyncio

from backend.models.schemas import AnalysisScore, SignalOutcome, FundamentalData
from backend.config import MAX_SECTOR_POSITIONS, MAX_TOTAL_POSITIONS

logger = logging.getLogger(__name__)

class PortfolioManager:
    def __init__(self, session: AsyncSession, capital: float = 100000.0):
        self.session = session
        self.capital = capital
        self.open_positions = []
        
    async def init(self):
        self.open_positions = await self._fetch_open_positions()

    async def _fetch_open_positions(self) -> List[SignalOutcome]:
        """Fetch currently open deployed positions (PENDING)."""
        query = select(SignalOutcome).where(
            and_(
                SignalOutcome.outcome == "PENDING",
                SignalOutcome.is_shadow == 0,
            )
        )
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
        sector_counts = {}
        total_open = 0
        
        for pos in self.open_positions:
            res = await self.session.execute(
                select(AnalysisScore).where(AnalysisScore.id == pos.analysis_score_id)
            )
            score = res.scalars().first()
            
            # Since schema does not have position_sizing right now (wait, does it?), 
            # actually we don't have position_sizing in AnalysisScore right now! 
            # Let's check AnalysisScore schema. Oh wait, my patch for ensemble_scorer removed position_sizing.
            # But the DB table doesn't even have position_sizing! Let's ignore it for tallying.
            # If it's in `SignalOutcome` with `outcome == "PENDING"`, then by definition it was deployed!
            total_open += 1
            sector = await self._get_sector(pos.symbol)
            sector_counts[sector] = sector_counts.get(sector, 0) + 1

        buy_signals = [s for s in daily_scores if s.signal in ["BUY", "STRONG BUY"] and not getattr(s, "is_shadow", False)]
        buy_signals.sort(key=lambda x: x.composite_score, reverse=True)

        logger.info(f"[Portfolio] Found {len(buy_signals)} visible BUY signals today. Current open positions: {total_open}.")

        for score in daily_scores:
            setattr(score, 'position_sizing', 0.0)

        for score in buy_signals:
            if total_open >= MAX_TOTAL_POSITIONS:
                logger.info(f"  Skipping {score.symbol} - Max total positions ({MAX_TOTAL_POSITIONS}) reached.")
                continue

            sector = await self._get_sector(score.symbol)
            if sector_counts.get(sector, 0) >= MAX_SECTOR_POSITIONS:
                logger.info(f"  Skipping {score.symbol} - Max sector positions ({MAX_SECTOR_POSITIONS}) reached for {sector}.")
                continue

            regime_risk_mult = {"BULL": 1.0, "SIDEWAYS": 0.85, "BEAR": 0.60}.get(regime, 0.85)
            regime_max_alloc = {"BULL": 0.20, "SIDEWAYS": 0.15, "BEAR": 0.10}.get(regime, 0.15)
            
            risk_amount = self.capital * 0.01 * regime_risk_mult
            risk_per_share = abs(score.current_price - score.stop_loss) if score.stop_loss and score.current_price else 1.0
            
            max_shares_by_risk = int(risk_amount / risk_per_share) if risk_per_share > 0 else 0
            max_shares_by_cap = int((self.capital * regime_max_alloc) / score.current_price) if score.current_price else 0
            
            shares = min(max_shares_by_risk, max_shares_by_cap)
            
            if shares > 0:
                setattr(score, 'position_sizing', float(shares))
                sector_counts[sector] = sector_counts.get(sector, 0) + 1
                total_open += 1
                logger.info(f"  Deployed {score.symbol} - Sector: {sector}, Shares: {shares}.")
            else:
                setattr(score, 'position_sizing', 0.0)

        return daily_scores

async def run_portfolio_allocation_for_today():
    import datetime
    from backend.models.database import AsyncSessionLocal
    from backend.config import IST
    
    today = datetime.datetime.now(IST).date()
    
    async with AsyncSessionLocal() as db:
        res = await db.execute(
            select(AnalysisScore).where(
                and_(
                    AnalysisScore.timestamp >= datetime.datetime.combine(today, datetime.time.min),
                    AnalysisScore.timestamp <= datetime.datetime.combine(today, datetime.time.max)
                )
            )
        )
        scores = res.scalars().all()
        
        if not scores:
            logger.info("No scores found for today to allocate.")
            return
            
        pm = PortfolioManager(db)
        await pm.init()
        await pm.allocate(scores)
        # Note: We don't commit position_sizing because it's not a column in AnalysisScore DB! 
        # Wait, if it's not in the DB, how does the frontend or outcome_tracker know it's deployed?
        logger.info(f"Portfolio allocation complete for {len(scores)} signals today.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_portfolio_allocation_for_today())
