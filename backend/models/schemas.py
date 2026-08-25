"""
ATBot — SQLAlchemy Database Models
All tables for storing market data, scores, news, watchlist & trade journal
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, Float, String, Text, Boolean,
    DateTime, ForeignKey, Index, UniqueConstraint
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


# ── OHLCV Price Data ──────────────────────────────────────────────────────
class PriceBar(Base):
    __tablename__ = "price_bars"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    interval = Column(String(5), nullable=False)        # 1d, 1h, 15m, 5m
    timestamp = Column(DateTime, nullable=False, index=True)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("symbol", "interval", "timestamp", name="uq_price_bar"),
        Index("ix_price_bars_symbol_interval", "symbol", "interval"),
    )


# ── Fundamental Data ──────────────────────────────────────────────────────
class FundamentalData(Base):
    __tablename__ = "fundamental_data"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, unique=True, index=True)
    company_name = Column(String(100))
    sector = Column(String(50))
    industry = Column(String(100))

    # Valuation
    pe_ratio = Column(Float)
    pb_ratio = Column(Float)
    ev_ebitda = Column(Float)
    market_cap = Column(Float)

    # Profitability
    roe = Column(Float)
    roce = Column(Float)
    profit_margin = Column(Float)
    operating_margin = Column(Float)

    # Growth
    revenue_growth_yoy = Column(Float)
    eps_growth_yoy = Column(Float)
    revenue_growth_qoq = Column(Float)

    # Balance Sheet
    debt_to_equity = Column(Float)
    current_ratio = Column(Float)
    interest_coverage = Column(Float)

    # India-specific
    promoter_holding = Column(Float)      # % held by promoters
    promoter_pledge = Column(Float)       # % pledged by promoters
    fii_holding = Column(Float)           # % held by FIIs
    dii_holding = Column(Float)           # % held by DIIs

    # Dividends
    dividend_yield = Column(Float)

    # Score
    fundamental_score = Column(Float)    # 0–100

    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ── Analysis Scores ───────────────────────────────────────────────────────
class AnalysisScore(Base):
    __tablename__ = "analysis_scores"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Component scores (0–100 each)
    technical_score = Column(Float)
    fundamental_score = Column(Float)
    sentiment_score = Column(Float)
    composite_score = Column(Float)

    # Signal
    signal = Column(String(15))           # STRONG_BUY, BUY, HOLD, SELL, STRONG_SELL
    confidence = Column(Float)            # 0–1

    # Price targets (₹)
    current_price = Column(Float)
    target_low_5d = Column(Float)
    target_base_5d = Column(Float)
    target_high_5d = Column(Float)
    target_low_10d = Column(Float)
    target_base_10d = Column(Float)
    target_high_10d = Column(Float)
    stop_loss = Column(Float)

    # Technical signals (JSON string)
    active_signals = Column(Text)         # JSON list of signal names
    dominant_pattern = Column(String(50)) # e.g., "Morning Star"

    # ATR for context
    atr_14 = Column(Float)

    # Market regime at time of analysis (Meta-Learner v2)
    regime = Column(String(10), nullable=True)   # BULL / BEAR / SIDEWAYS

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_scores_symbol_ts", "symbol", "timestamp"),
    )


# ── News Articles ─────────────────────────────────────────────────────────
class NewsArticle(Base):
    __tablename__ = "news_articles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), index=True)          # NULL = market-wide news
    headline = Column(String(500), nullable=False)
    summary = Column(Text)
    url = Column(String(1000))
    source = Column(String(100))
    published_at = Column(DateTime, nullable=False, index=True)

    # Sentiment
    sentiment = Column(String(10))                   # positive, negative, neutral
    sentiment_score = Column(Float)                  # -1.0 to 1.0
    sentiment_confidence = Column(Float)             # 0.0 to 1.0

    # Topic (LDA)
    topic = Column(String(50))                       # earnings, results, mgmt, macro

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("url", name="uq_news_url"),
    )


# ── FII / DII Flow ────────────────────────────────────────────────────────
class FIIDIIFlow(Base):
    __tablename__ = "fii_dii_flow"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(DateTime, nullable=False, unique=True, index=True)

    # FII (Foreign Institutional Investors)
    fii_buy = Column(Float)                # ₹ crores
    fii_sell = Column(Float)
    fii_net = Column(Float)                # positive = net buyer

    # DII (Domestic Institutional Investors)
    dii_buy = Column(Float)
    dii_sell = Column(Float)
    dii_net = Column(Float)

    created_at = Column(DateTime, default=datetime.utcnow)


# ── Watchlist ─────────────────────────────────────────────────────────────
class Watchlist(Base):
    __tablename__ = "watchlist"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, unique=True, index=True)
    company_name = Column(String(100))
    added_at = Column(DateTime, default=datetime.utcnow)
    notes = Column(Text)
    alert_on_signal_change = Column(Boolean, default=True)
    alert_price_above = Column(Float)     # alert if price > this
    alert_price_below = Column(Float)     # alert if price < this
    is_active = Column(Boolean, default=True)


# ── Trade Journal ─────────────────────────────────────────────────────────
class TradeJournal(Base):
    __tablename__ = "trade_journal"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    company_name = Column(String(100))

    # Entry
    entry_date = Column(DateTime, nullable=False)
    entry_price = Column(Float, nullable=False)
    quantity = Column(Integer)
    signal_at_entry = Column(String(15))      # what ATBot said at entry
    composite_score_at_entry = Column(Float)

    # Plan
    planned_target = Column(Float)
    planned_stop_loss = Column(Float)
    atbot_target_base = Column(Float)         # ATBot's base target
    atbot_stop_loss = Column(Float)           # ATBot's stop loss

    # Exit
    exit_date = Column(DateTime)
    exit_price = Column(Float)
    exit_reason = Column(String(50))          # TARGET_HIT, SL_HIT, MANUAL, SIGNAL_FLIP

    # Outcome
    pnl_amount = Column(Float)               # ₹ P&L
    pnl_percent = Column(Float)              # % P&L
    holding_days = Column(Integer)
    outcome = Column(String(10))             # WIN, LOSS, BREAKEVEN

    # Notes
    trade_notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# -- User Settings --
class UserSettings(Base):
    __tablename__ = 'user_settings'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(50), nullable=False, unique=True, default='default')
    capital = Column(Float, default=100000.0)
    risk_profile = Column(String(20), default='moderate')
    alert_signal_change = Column(Boolean, default=True)
    alert_strong_signals_only = Column(Boolean, default=False)
    alert_volume_spike = Column(Boolean, default=True)
    alert_vix_threshold = Column(Float, default=20.0)
    alert_fii_threshold = Column(Float, default=2000.0)
    notify_browser = Column(Boolean, default=True)
    notify_telegram = Column(Boolean, default=False)
    telegram_chat_id = Column(String(50))
    screener_default_universe = Column(String(20), default='nifty50')
    screener_default_sort = Column(String(20), default='score')
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # Meta-learner v1: single global adaptive weights (None = not yet learned)
    meta_weight_technical   = Column(Float, nullable=True)
    meta_weight_fundamental = Column(Float, nullable=True)
    meta_weight_sentiment   = Column(Float, nullable=True)
    meta_last_updated       = Column(DateTime, nullable=True)
    meta_sample_count       = Column(Integer, nullable=True)

    # Meta-learner v2: per-regime weight sets (BULL / BEAR / SIDEWAYS)
    # BULL regime weights
    meta_bull_T = Column(Float, nullable=True)
    meta_bull_F = Column(Float, nullable=True)
    meta_bull_S = Column(Float, nullable=True)
    meta_bull_n = Column(Integer, nullable=True)   # sample count for BULL
    # BEAR regime weights
    meta_bear_T = Column(Float, nullable=True)
    meta_bear_F = Column(Float, nullable=True)
    meta_bear_S = Column(Float, nullable=True)
    meta_bear_n = Column(Integer, nullable=True)
    # SIDEWAYS regime weights
    meta_side_T = Column(Float, nullable=True)
    meta_side_F = Column(Float, nullable=True)
    meta_side_S = Column(Float, nullable=True)
    meta_side_n = Column(Integer, nullable=True)

    # v3 metrics
    meta_validation_accuracy    = Column(Float,   nullable=True)   # hold-out accuracy
    meta_regime_shift_detected  = Column(Integer, nullable=True)   # bool stored as 0/1


# -- Signal Outcomes --
class SignalOutcome(Base):
    __tablename__ = 'signal_outcomes'
    id = Column(Integer, primary_key=True, autoincrement=True)
    analysis_score_id = Column(Integer, index=True)   # FK to analysis_scores.id
    symbol = Column(String(20), nullable=False, index=True)
    signal = Column(String(20), index=True)           # STRONG BUY, BUY, HOLD, SELL, STRONG SELL
    composite_score = Column(Float)
    technical_score = Column(Float)
    fundamental_score = Column(Float)
    sentiment_score = Column(Float)
    confidence = Column(Float)
    entry_date = Column(DateTime, nullable=False, index=True)
    entry_price = Column(Float)
    stop_loss = Column(Float)
    target_conservative = Column(Float)  # target_low_5d
    target_base = Column(Float)          # target_base_5d
    target_aggressive = Column(Float)    # target_high_5d
    check_day = Column(Integer)          # 5 or 10
    check_date = Column(DateTime)
    price_at_check = Column(Float)
    pnl_amount = Column(Float)           # price_at_check - entry_price
    pnl_percent = Column(Float)          # % P&L
    outcome = Column(String(20), index=True)  # WIN / LOSS / BREAKEVEN / OPEN
    outcome_detail = Column(String(50))       # e.g. TARGET_HIT / SL_HIT / PARTIAL
    regime = Column(String(10), nullable=True)  # Market regime at signal time (v2)
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint('analysis_score_id', 'check_day', name='uq_outcome_score_day'),)
