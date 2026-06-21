import json
import logging
import sys
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.config import get_settings
from app.core.database import engine
from app.api.v1 import auth, users, clubs, venues, bookings, posts, tournaments

# Setup file + console logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("app.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("club-api")

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup (use alembic in production)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created/verified")
    yield
    await engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    docs_url="/docs",
    lifespan=lifespan,
)

class RequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.time()
        body = None
        if request.method in ("POST", "PUT", "PATCH"):
            try:
                body_bytes = await request.body()
                body = body_bytes.decode()[:2000] if body_bytes else None
            except Exception:
                body = "<read error>"
        response = await call_next(request)
        elapsed = time.time() - start
        logger.info(
            "%s %s → %s (%.0fms)%s",
            request.method, request.url.path, response.status_code,
            elapsed * 1000,
            f" body={body}" if body else "",
        )
        return response


app.add_middleware(RequestLogMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
api_prefix = settings.API_V1_PREFIX
app.include_router(auth.router, prefix=api_prefix)
app.include_router(users.router, prefix=api_prefix)
app.include_router(clubs.router, prefix=api_prefix)
app.include_router(venues.router, prefix=api_prefix)
app.include_router(bookings.router, prefix=api_prefix)
app.include_router(posts.router, prefix=api_prefix)
app.include_router(tournaments.router, prefix=api_prefix)


@app.get("/health")
async def health():
    return {"status": "ok"}
