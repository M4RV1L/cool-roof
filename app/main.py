"""
main.py — FastAPI application entry point
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import analysis


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    )
    logging.getLogger(__name__).info("Cool Roof Backend starting up (%s)", settings.app_env)
    yield
    logging.getLogger(__name__).info("Cool Roof Backend shutting down")


app = FastAPI(
    title="Cool Roof Analyzer API",
    description=(
        "Satellite-derived albedo analysis and cool-roof benefit estimation. "
        "Powered by Sentinel-2 L2A imagery via Sentinel Hub."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Restrict in production
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analysis.router, prefix="/api/v1")


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok"}
