"""
ATBot — FastAPI Application Entry Point
"""

import time
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from backend.config import settings
from backend.logging_config import setup_logging, get_request_logger
from backend.models.database import init_db
from backend.data.scheduler import (
    setup_scheduler, job_refresh_index_data,
    job_refresh_news, job_refresh_fii_dii, startup_catchup
)
from backend.engines.meta_learner import get_current_adaptive_weights
from backend.engines.ensemble_scorer import set_adaptive_weights

# Routers
from backend.api.routes import analysis, market, news, screener, settings as settings_router, learn, optimizer
from backend.api.websocket import router as ws_router

# Setup date-wise file logging (requests, errors, app) and console logging
setup_logging(debug=settings.debug)
logger = logging.getLogger(__name__)
request_logger = get_request_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle events: Startup and Shutdown."""
    logger.info(f"🚀 Starting {settings.app_name} v{settings.app_version}...")

    # 1. Initialize Database
    await init_db()

    # 2. Start Background Scheduler
    scheduler = setup_scheduler()
    scheduler.start()

    # 3. Eagerly warm the cache so the frontend gets data immediately
    logger.info("⚡ Warming cache on startup...")
    await job_refresh_index_data()
    await job_refresh_news()
    await job_refresh_fii_dii()

    # 4. Load adaptive weights from DB (if meta-learner has run before)
    try:
        saved_weights = await get_current_adaptive_weights()
        if saved_weights:
            set_adaptive_weights(saved_weights)
            logger.info(f"🧠 Loaded adaptive weights from DB: T={saved_weights.get('T')} F={saved_weights.get('F')} S={saved_weights.get('S')}")
        else:
            logger.info("🧠 No adaptive weights found — using regime-based defaults until meta-learner runs")
    except Exception as e:
        logger.warning(f"⚠️ Could not load adaptive weights: {e}")

    # 4b. Bootstrap the SIDEWAYS kill switch IN-PROCESS.
    # Without this, _sideways_kill_state stays empty after every server
    # restart, and the switch remains dormant until the 6:30 PM outcome
    # tracker job runs. Running the bootstrap here ensures the switch is
    # armed the moment the app is ready to serve requests.
    try:
        from backend.engines.outcome_tracker import refresh_sideways_win_rate
        from backend.engines.ensemble_scorer import set_sideways_win_rate
        wr, n = await refresh_sideways_win_rate(days=30)
        set_sideways_win_rate(wr, n)
        logger.info(f"🛑 [Startup] Kill switch bootstrapped: win_rate={wr}, n={n}")
    except Exception as e:
        logger.warning(f"⚠️ Could not bootstrap kill switch: {e}")

    logger.info("✅ Cache warm — ready to serve!")

    # 5. Catch-up missed jobs (outcome check, report, precompute) if server
    #    was offline at their scheduled time. Runs in background so startup
    #    is not blocked. Logs appear in console ~a few seconds later.
    import asyncio
    asyncio.create_task(startup_catchup())

    yield  # Application runs while yielded

    # Shutdown
    logger.info("🛑 Shutting down...")
    scheduler.shutdown()


# Initialize FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan
)

# CORS Middleware for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For local dev. Change to localhost:3000 in prod.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Date-wise Request & Error Logging Middleware
@app.middleware("http")
async def log_requests_middleware(request: Request, call_next):
    start_time = time.perf_counter()
    client_ip = request.client.host if request.client else "unknown"
    method = request.method
    path = request.url.path
    if request.url.query:
        path = f"{path}?{request.url.query}"

    try:
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start_time) * 1000
        request_logger.info(
            f"{client_ip} | {method} {path} | {response.status_code} | {duration_ms:.1f}ms"
        )
        return response
    except Exception as exc:
        duration_ms = (time.perf_counter() - start_time) * 1000
        request_logger.error(
            f"{client_ip} | {method} {path} | 500 ERROR | {duration_ms:.1f}ms | {exc}"
        )
        logger.exception(f"Unhandled exception during {method} {path}: {exc}")
        raise exc

# Include Routers
app.include_router(analysis.router, prefix="/api")
app.include_router(market.router, prefix="/api")
app.include_router(news.router, prefix="/api")
app.include_router(screener.router, prefix="/api")
app.include_router(settings_router.router, prefix="/api")
app.include_router(learn.router, prefix="/api")
app.include_router(optimizer.router, prefix="/api")
app.include_router(ws_router)


@app.get("/health")
async def health_check():
    """Simple health check endpoint."""
    return {"status": "healthy", "version": settings.app_version}