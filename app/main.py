"""
main.py — ShimonVault FastAPI entry point

STARTUP DESIGN:
  The /health endpoint MUST return HTTP 200 immediately so the ALB health
  check passes and the instance is marked healthy.  DB initialisation is
  therefore moved to a background thread that retries until RDS is ready
  (takes 30-60 s after the EC2 boots).  The app serves traffic while the
  DB is still warming up; any route that actually hits the DB will get a
  503 until init_db() succeeds, but the health check stays green.

FRONTEND SERVING:
  In production the React SPA is built by the Dockerfile's frontend-builder
  stage and copied to ./frontend_dist. This file mounts /assets and serves
  index.html at "/" and as a catch-all, so the whole app loads same-origin
  at shimonvault.junhanshin.com (no CORS needed in prod). When the build is
  absent (local `uvicorn` dev), "/" falls back to a small JSON info page.
"""

import logging
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from config import APP_VERSION, PROJECT_NAME, ENVIRONMENT
from database import init_db
from rate_limit import limiter

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)

# ── DB-init state (read by /health) ──────────────────────────────────────────
_db_ready = False
_db_init_error: str = ""


def _init_db_with_retry(max_attempts: int = 20, delay: int = 15) -> None:
    """
    Called in a daemon thread.  Retries every `delay` seconds until
    create_all() succeeds or max_attempts is exhausted.
    20 attempts x 15 s = 5 minutes total patience.
    """
    global _db_ready, _db_init_error
    for attempt in range(1, max_attempts + 1):
        try:
            logger.info("DB init attempt %d/%d ...", attempt, max_attempts)
            init_db()
            _db_ready = True
            _db_init_error = ""
            logger.info("Database schema ready (attempt %d)", attempt)
            return
        except Exception as exc:
            _db_init_error = str(exc)
            logger.warning(
                "DB init attempt %d failed: %s — retrying in %ds",
                attempt, exc, delay
            )
            time.sleep(delay)

    logger.error("DB init failed after %d attempts: %s", max_attempts, _db_init_error)


# ── Lifespan (replaces deprecated @app.on_event) ─────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("ShimonVault %s starting up (env: %s)", APP_VERSION, ENVIRONMENT)

    # Fire-and-forget background DB initialisation.
    # daemon=True means this thread will not prevent process shutdown.
    t = threading.Thread(target=_init_db_with_retry, daemon=True, name="db-init")
    t.start()

    yield  # app runs here

    logger.info("ShimonVault shutting down.")


# ── App instance ──────────────────────────────────────────────────────────────
app = FastAPI(
    title="ShimonVault",
    description="Secure internal operations platform",
    version=APP_VERSION,
    lifespan=lifespan,
)

# ── Rate limiting ─────────────────────────────────────────────────────────────
# Must be attached here -- a Limiter() instance created in a router but never
# registered on app.state + given SlowAPIMiddleware will let every
# @limiter.limit(...) decorator run without ever actually enforcing a limit.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# ── CORS ──────────────────────────────────────────────────────────────────────
# Still useful for local dev (Vite on :5173 hitting this API). In production the
# SPA is served same-origin, so CORS is not actually exercised there.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # tighten in production if needed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Prometheus metrics ────────────────────────────────────────────────────────
Instrumentator().instrument(app).expose(app, endpoint="/metrics")

# ── Routers ───────────────────────────────────────────────────────────────────
from routers.auth_router import router as auth_router  # noqa: E402
from routers.docs_router import router as docs_router  # noqa: E402
from routers.meetings_router import router as meetings_router  # noqa: E402
from routers.audit_router import router as audit_router  # noqa: E402
from routers.admin_router import router as admin_router  # noqa: E402
from routers.demo_router import router as demo_router  # noqa: E402

app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(docs_router, prefix="/docs", tags=["docs"])
app.include_router(meetings_router, prefix="/meetings", tags=["meetings"])
app.include_router(audit_router, prefix="/audit", tags=["audit"])
# Admin dashboard data (Grafana-equivalent) + one-click demo triggers.
# Both are admin-only; the SPA console calls these.
app.include_router(admin_router, prefix="/admin", tags=["admin"])
app.include_router(demo_router, prefix="/demo", tags=["demo"])


# ── Audit middleware (logs EVERY request to the AuditStream / DynamoDB) ────────
# Added last so it is the outermost layer: it sees every request first and the
# final response last. Without this line the AuditStream feature does nothing.
from middleware.audit_middleware import AuditMiddleware  # noqa: E402

app.add_middleware(AuditMiddleware)


# ── Frontend (React SPA) ──────────────────────────────────────────────────────
# The Dockerfile copies the Vite build to ./frontend_dist. Built index.html
# references /assets/*.js + /assets/*.css, so we mount that directory here.
# Guarded with is_dir() so running uvicorn locally without a build won't crash.
_FRONTEND_DIST = Path(__file__).resolve().parent / "frontend_dist"
_FRONTEND_INDEX = _FRONTEND_DIST / "index.html"

if (_FRONTEND_DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=_FRONTEND_DIST / "assets"), name="assets")
    logger.info("Serving SPA from %s", _FRONTEND_DIST)
else:
    logger.info("No frontend build at %s — serving API only", _FRONTEND_DIST)


# ── Health endpoint ───────────────────────────────────────────────────────────
@app.get("/health", tags=["health"])
def health_check():
    """
    Always returns HTTP 200 so the ALB health check passes immediately.

    The 'db' field tells you whether the database is also ready:
      - "initialising" -> background thread is still retrying (normal for
        the first 1-3 minutes after a fresh EC2 boot)
      - "ok"           -> schema created, connections working
      - "error: ..."   -> something is wrong; check /logs

    The ALB only cares about the HTTP status code (200), not the body.
    """
    if _db_ready:
        db_status = "ok"
    elif _db_init_error:
        db_status = f"error: {_db_init_error[:120]}"
    else:
        db_status = "initialising"

    return {
        "status": "healthy",
        "version": APP_VERSION,
        "project": PROJECT_NAME,
        "environment": ENVIRONMENT,
        "db": db_status,
    }


# ── Root ──────────────────────────────────────────────────────────────────────
@app.get("/", tags=["root"])
def root():
    # Serve the SPA in production; fall back to API info when no build present.
    if _FRONTEND_INDEX.is_file():
        return FileResponse(_FRONTEND_INDEX)
    return {
        "project": PROJECT_NAME,
        "version": APP_VERSION,
        "docs": "/docs",
        "health": "/health",
        "metrics": "/metrics",
    }


# ── SPA fallback ──────────────────────────────────────────────────────────────
# MUST be the last route declared. API routes, /assets, /docs, /metrics and
# /health are all registered earlier, so they match first; anything else falls
# through to index.html so the React app loads (and future client-side routes /
# page refreshes work). Returns 404 only when no build is present.
@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str):
    if _FRONTEND_INDEX.is_file():
        return FileResponse(_FRONTEND_INDEX)
    raise HTTPException(status_code=404, detail="Not found")
