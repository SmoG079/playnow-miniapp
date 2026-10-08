import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings
from app.core.database import engine
from app.core.logger import setup_logging, RequestLogMiddleware, get_logger
from app.api.deps import get_current_user
from app.api.v1 import auth, users, clubs, venues, bookings, posts, tournaments, activities, discovery
from app.services import storage

settings = get_settings()
setup_logging(settings)

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Database schema is managed by Alembic migrations.
    # Run: docker-compose exec api alembic upgrade head
    logger.info("media storage backend: %s", storage.active_backend())
    yield
    await engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    docs_url="/docs",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RequestLogMiddleware)

# Register routers
api_prefix = settings.API_V1_PREFIX
app.include_router(auth.router, prefix=api_prefix)
app.include_router(users.router, prefix=api_prefix)
app.include_router(clubs.router, prefix=api_prefix)
app.include_router(venues.router, prefix=api_prefix)
app.include_router(bookings.router, prefix=api_prefix)
app.include_router(posts.router, prefix=api_prefix)
app.include_router(tournaments.router, prefix=api_prefix)
app.include_router(activities.router, prefix=api_prefix)
app.include_router(discovery.router, prefix=api_prefix)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/v1/upload")
async def upload_file(
    file: UploadFile = File(...),
    file_type: str = Form("upload"),
    _=Depends(get_current_user),
):
    """Upload an image to COS. Returns {url, filename} with a client-reachable URL.

    file_type selects the object prefix: avatar / court / post / video (其他回落 upload)。
    活动图片（post）强制 COS；其他类型在未配置时兼容本地回退。
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="缺少文件名")
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in settings.UPLOAD_ALLOWED_EXT:
        raise HTTPException(status_code=400, detail="仅支持 jpg/png/webp/gif 图片")
    content = await file.read()
    max_bytes = settings.UPLOAD_MAX_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413, detail=f"图片不能超过 {settings.UPLOAD_MAX_MB}MB"
        )
    key = storage.build_key(file_type, ext)
    try:
        url = await run_in_threadpool(storage.put_object, key, content, ext)
    except storage.StorageUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception:
        logger.error("media upload failed: key=%s", key, exc_info=True)
        raise HTTPException(status_code=502, detail="图片上传失败，请稍后重试")
    logger.info(
        "media upload: %s -> %s (%d bytes)", key, storage.active_backend(), len(content)
    )
    return {"url": url, "filename": key}


# Serve legacy uploaded files. 2026-10-07 起新上传走 COS，此挂载仅为兼容
# 数据库中已存在的 /uploads/<uuid> 历史链接（storage.py 未配置 COS 时也复用它）。
from fastapi.staticfiles import StaticFiles

os.makedirs(storage.LOCAL_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=storage.LOCAL_DIR), name="uploads")
