from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api import analysis, auth, imports, movies, profile, recommendations
from app.config import settings
from app.database import Base, SessionLocal, engine

logging.basicConfig(
    level=logging.INFO if settings.production else logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
# httpx/httpcore include query strings in debug logs. TMDB authenticates with a
# query parameter, so keep those libraries quiet to avoid leaking API keys.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger("myboxd")

if settings.auto_create_schema:
    # Development/test convenience only. Production uses Alembic migrations.
    Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="MyBoxd API",
    version="5.2.0",
    description="Private multi-user Letterboxd taste analysis and explainable movie recommendations.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.frontend_origins),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)

for router in (auth.router, imports.router, profile.router, recommendations.router, movies.router, analysis.router):
    app.include_router(router, prefix="/api")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if request.url.path.startswith("/api/") and request.url.path != "/api/health":
        response.headers["Cache-Control"] = "no-store"
    if settings.production:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else None
    message = first.get("msg", "Invalid request") if first else "Invalid request"
    return JSONResponse(status_code=422, content={"detail": message, "code": "validation_error"})


@app.exception_handler(Exception)
async def unexpected_error(_: Request, exc: Exception):
    logger.exception("Unhandled API error", exc_info=exc)
    if settings.production:
        return JSONResponse(status_code=500, content={"detail": "Something went wrong on the server.", "code": "server_error"})
    return JSONResponse(status_code=500, content={"detail": str(exc), "code": "server_error"})


FRONTEND_DIST = Path(__file__).resolve().parents[1] / "frontend_dist"
if (FRONTEND_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")


@app.get("/", include_in_schema=False)
def root():
    index = FRONTEND_DIST / "index.html"
    if index.exists():
        return FileResponse(index)
    return {"name": settings.app_name, "status": "ok", "docs": "/docs"}


@app.get("/health", tags=["system"])
@app.get("/api/health", tags=["system"])
def health():
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "ok"}
    except SQLAlchemyError:
        return JSONResponse(status_code=503, content={"status": "degraded", "database": "unavailable"})


@app.get("/{full_path:path}", include_in_schema=False)
def frontend_spa(full_path: str):
    # API/docs/system routes above keep precedence. Everything else is the React SPA.
    if not FRONTEND_DIST.exists():
        return JSONResponse(status_code=404, content={"detail": "Not found"})
    candidate = (FRONTEND_DIST / full_path).resolve()
    try:
        candidate.relative_to(FRONTEND_DIST.resolve())
    except ValueError:
        return JSONResponse(status_code=404, content={"detail": "Not found"})
    if candidate.is_file():
        return FileResponse(candidate)
    return FileResponse(FRONTEND_DIST / "index.html")
