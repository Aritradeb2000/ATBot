"""
ATBot — Portfolio Allocation Optimizer API Routes
POST /api/optimizer/run  →  Returns an optimal stock allocation plan
"""

import logging
from typing import Optional, List
from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.engines.portfolio_optimizer import run_optimizer

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Optimizer"])


class OptimizerRequest(BaseModel):
    amount:           float = Field(..., gt=0, description="Total capital to deploy in ₹")
    universe:         str   = Field(default="nifty50", description="nifty50 | watchlist | custom")
    symbols:          Optional[List[str]] = Field(default=None, description="Custom symbols list")
    watchlist_symbols: Optional[List[str]] = Field(default=None, description="Watchlist symbols (when universe=watchlist)")
    risk_profile:     str   = Field(default="moderate", description="conservative | moderate | aggressive")
    max_stocks:       int   = Field(default=5, ge=2, le=15)
    min_rr:           Optional[float] = Field(default=None, description="Override minimum R:R ratio")


@router.post("/optimizer/run")
async def run_portfolio_optimizer(req: OptimizerRequest):
    """
    Run the portfolio allocation optimizer.

    Scans the requested stock universe, filters by signal quality,
    and returns a score-weighted capital allocation plan.
    Takes ~60–120s for Nifty 50 (parallel batches of 5).
    """
    logger.info(
        f"🎯 Optimizer request: ₹{req.amount:,.0f} | "
        f"universe={req.universe} | profile={req.risk_profile} | max_stocks={req.max_stocks}"
    )
    try:
        result = await run_optimizer(
            amount=req.amount,
            universe=req.universe,
            symbols=req.symbols,
            risk_profile=req.risk_profile,
            max_stocks=req.max_stocks,
            min_rr=req.min_rr,
            watchlist_symbols=req.watchlist_symbols,
        )
        return result
    except Exception as e:
        logger.error(f"Optimizer failed: {e}")
        return {
            "status":  "error",
            "message": str(e),
            "allocations": [],
        }
