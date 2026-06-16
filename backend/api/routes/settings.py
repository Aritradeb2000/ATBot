"""
ATBot — Settings Endpoint
GET  /api/settings        → return current user settings
PUT  /api/settings        → upsert user settings
"""

import logging
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional

from backend.models.database import get_db
from backend.models.schemas import UserSettings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Settings"])

DEFAULT_USER_ID = "default"


# ── Pydantic request / response models ───────────────────────────────────────

class SettingsPayload(BaseModel):
    capital: Optional[float] = None
    risk_profile: Optional[str] = None           # conservative | moderate | aggressive
    alert_signal_change: Optional[bool] = None
    alert_strong_signals_only: Optional[bool] = None
    alert_volume_spike: Optional[bool] = None
    alert_vix_threshold: Optional[float] = None
    alert_fii_threshold: Optional[float] = None
    notify_browser: Optional[bool] = None
    notify_telegram: Optional[bool] = None
    telegram_chat_id: Optional[str] = None
    screener_default_universe: Optional[str] = None
    screener_default_sort: Optional[str] = None


def _row_to_dict(row: UserSettings) -> dict:
    return {
        "user_id":                   row.user_id,
        "capital":                   row.capital,
        "risk_profile":              row.risk_profile,
        "alert_signal_change":       row.alert_signal_change,
        "alert_strong_signals_only": row.alert_strong_signals_only,
        "alert_volume_spike":        row.alert_volume_spike,
        "alert_vix_threshold":       row.alert_vix_threshold,
        "alert_fii_threshold":       row.alert_fii_threshold,
        "notify_browser":            row.notify_browser,
        "notify_telegram":           row.notify_telegram,
        "telegram_chat_id":          row.telegram_chat_id,
        "screener_default_universe": row.screener_default_universe,
        "screener_default_sort":     row.screener_default_sort,
        "updated_at":                row.updated_at.isoformat() if row.updated_at else None,
    }


# ── GET /api/settings ─────────────────────────────────────────────────────────

@router.get("/settings")
async def get_settings(db: AsyncSession = Depends(get_db)):
    """Return the current user settings row. Creates defaults if missing."""
    result = await db.execute(
        select(UserSettings).where(UserSettings.user_id == DEFAULT_USER_ID)
    )
    row = result.scalar_one_or_none()

    if row is None:
        # First-time: create defaults
        row = UserSettings(user_id=DEFAULT_USER_ID)
        db.add(row)
        await db.commit()
        await db.refresh(row)

    return _row_to_dict(row)


# ── PUT /api/settings ─────────────────────────────────────────────────────────

@router.put("/settings")
async def update_settings(payload: SettingsPayload, db: AsyncSession = Depends(get_db)):
    """Upsert user settings. Only provided fields are updated."""
    result = await db.execute(
        select(UserSettings).where(UserSettings.user_id == DEFAULT_USER_ID)
    )
    row = result.scalar_one_or_none()

    if row is None:
        row = UserSettings(user_id=DEFAULT_USER_ID)
        db.add(row)

    # Apply only fields that were explicitly set in the request
    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(row, field, value)

    await db.commit()
    await db.refresh(row)

    logger.info(f"Settings updated: {update_data}")
    return {"status": "ok", "settings": _row_to_dict(row)}
