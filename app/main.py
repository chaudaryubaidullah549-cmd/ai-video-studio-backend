"""
AI Video Studio - backend entrypoint.

Run with:
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
"""
from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import health, projects, scenes
from app.config import get_settings
from app.database import init_db
from app.utils.errors import AppError, RateLimitError
from app.utils.logging import configure_logging, get_logger, log_event

settings = get_settings()
configure_logging("DEBUG" if settings.DEBUG else "INFO")
logger = get_logger(__name__)

app = FastAPI(
    title=settings.APP_NAME,
    description="Backend/API for an AI video generation platform. See /docs for the interactive API reference.",
    version="1.0.0",
)

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# --- Request size limit ---
@app.middleware("http")
async def limit_request_size(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > settings.MAX_REQUEST_BODY_BYTES:
        return JSONResponse(
            status_code=413,
            content={
                "error": {
                    "code": "REQUEST_TOO_LARGE",
                    "message": f"Request body exceeds the {settings.MAX_REQUEST_BODY_BYTES} byte limit.",
                    "retryable": False,
                }
            },
        )
    return await call_next(request)


# --- Basic in-memory rate limiting (per client IP, sliding window) ---
# NOTE: this is process-local and resets on restart - adequate for a
# single-instance dev/staging deployment. For multi-instance production
# deployments, replace with a shared store (e.g. Redis) behind the same
# middleware interface.
_request_log: dict[str, deque] = defaultdict(deque)


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    if request.url.path in ("/health", "/docs", "/openapi.json", "/redoc"):
        return await call_next(request)

    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    window_start = now - settings.RATE_LIMIT_WINDOW_SECONDS
    log = _request_log[client_ip]
    while log and log[0] < window_start:
        log.popleft()

    if len(log) >= settings.RATE_LIMIT_REQUESTS:
        err = RateLimitError(
            f"Rate limit of {settings.RATE_LIMIT_REQUESTS} requests per "
            f"{settings.RATE_LIMIT_WINDOW_SECONDS}s exceeded."
        )
        return JSONResponse(status_code=err.status_code, content=err.to_dict())

    log.append(now)
    return await call_next(request)


# --- Error handling ---
@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    log_event(logger, "warning", "api.error", path=request.url.path, code=exc.code, message=exc.message)
    return JSONResponse(status_code=exc.status_code, content=exc.to_dict())


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    log_event(logger, "warning", "api.validation_error", path=request.url.path, errors=str(exc.errors())[:500])
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed.",
                "retryable": False,
                "details": {"errors": exc.errors()},
            }
        },
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    log_event(logger, "error", "api.unhandled_error", path=request.url.path, error=str(exc))
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred.",
                "retryable": True,
            }
        },
    )


# --- Static media (local storage backend) ---
import os

os.makedirs(settings.LOCAL_STORAGE_PATH, exist_ok=True)
app.mount("/media", StaticFiles(directory=settings.LOCAL_STORAGE_PATH), name="media")

# --- Routers ---
app.include_router(health.router)
app.include_router(projects.router)
app.include_router(scenes.router)


@app.on_event("startup")
async def on_startup():
    init_db()
    log_event(
        logger, "info", "app.startup",
        mock_mode=settings.MOCK_MODE, environment=settings.ENVIRONMENT,
    )


@app.get("/")
async def root():
    return {
        "name": settings.APP_NAME,
        "status": "running",
        "mock_mode": settings.MOCK_MODE,
        "docs": "/docs",
    }
