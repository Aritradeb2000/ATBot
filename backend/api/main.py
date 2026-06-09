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
    job_refresh_news, job_refresh_fii_dii
)

# Routers
from backend.api.routes import analysis, market, news, screener
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
    logger.info("✅ Cache warm — ready to serve!")
    
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
app.include_router(ws_router)

@app.get("/health")
async def health_check():
    """Simple health check endpoint."""
    return {"status": "healthy", "version": settings.app_version}
