"""
ATBot — FastAPI Application Entry Point
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from backend.config import settings
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

# Setup basic logging
logging.basicConfig(
    level=logging.INFO if settings.debug else logging.WARNING,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


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
