import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings
from app.core.database import engine, get_db
from sqlalchemy import select, cast, String
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.responses import Response, FileResponse
from app.models.models import PrivateUpload, Club
from app.core.logger import setup_logging, RequestLogMiddleware, get_logger
from app.api.deps import get_current_user
from app.api.v1 import auth, users, clubs, venues, bookings, posts, tournaments, activities, discovery, applications
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

from app.core.public_identity import PublicIdentityMiddleware
app.add_middleware(PublicIdentityMiddleware)
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
app.include_router(applications.router, prefix=api_prefix)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/v1/upload")
async def upload_file(
    file: UploadFile = File(...),
    file_type: str = Form("upload"),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload an image to COS. Returns {url, filename} with a client-reachable URL.

    file_type selects the object prefix: avatar / court / post / video (其他回落 upload)。
    活动图片（post）强制 COS；其他类型在未配置时兼容本地回退。
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="缺少文件名")
    ext = os.path.splitext(file.filename)[1].lower()
    is_document = file_type == "doc"
    if ext not in ((*settings.UPLOAD_ALLOWED_EXT, ".pdf") if is_document else settings.UPLOAD_ALLOWED_EXT):
        raise HTTPException(status_code=400, detail="仅支持 jpg/png/webp/gif 图片")
    max_bytes = (10 if is_document else settings.UPLOAD_MAX_MB) * 1024 * 1024
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413, detail=f"文件不能超过 {max_bytes // (1024 * 1024)}MB"
        )
    if is_document:
        if ext == ".pdf" and not content.startswith(b"%PDF-"):
            raise HTTPException(422, "认证 PDF 文件格式无效")
        filename = storage.build_key("doc", ext).split("/")[1]
        try:
            backend = await run_in_threadpool(storage.put_private_document, filename, content, ext)
        except storage.StorageUnavailable as exc:
            raise HTTPException(503, str(exc)) from exc
        db.add(PrivateUpload(id=filename, user_id=user.id, backend=backend, content_type=storage.MIME[ext]))
        await db.flush()
        return {"url": f"{settings.PUBLIC_BASE_URL}/api/v1/media/doc/{filename}", "filename": filename}
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



@app.get("/api/v1/media/doc/{filename}")
async def private_document(filename: str, user=Depends(get_current_user), db: AsyncSession=Depends(get_db)):
    record = await db.get(PrivateUpload, filename)
    if record is None: raise HTTPException(404, "文件不存在")
    permitted = record.user_id == user.id or getattr(user.role, "value", user.role) == "platform_admin"
    if not permitted:
        from app.services.privacy import can_view_club_documents
        clubs = (await db.execute(select(Club).where(cast(Club.documents, String).contains(filename)))).scalars().all()
        for club in clubs:
            if await can_view_club_documents(db, club, user):
                permitted = True
                break
    if not permitted: raise HTTPException(403, "无权访问认证材料")
    if record.backend == "local":
        path = os.path.join(storage.PRIVATE_LOCAL_DIR, filename)
        if not os.path.isfile(path): raise HTTPException(404, "文件不存在")
        return FileResponse(path, media_type=record.content_type, headers={"Cache-Control":"private, no-store"})
    content = await run_in_threadpool(storage.read_private_document, filename)
    return Response(content, media_type=record.content_type, headers={"Cache-Control":"private, no-store"})


# Serve legacy uploaded files. 2026-10-07 起新上传走 COS，此挂载仅为兼容
# 数据库中已存在的 /uploads/<uuid> 历史链接（storage.py 未配置 COS 时也复用它）。
from fastapi.staticfiles import StaticFiles

os.makedirs(storage.LOCAL_DIR, exist_ok=True)
class LegacyStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        if path.split("/", 1)[0] == "doc":
            raise HTTPException(404, "认证材料需迁移到私有存储")
        return await super().get_response(path, scope)

app.mount("/uploads", LegacyStaticFiles(directory=storage.LOCAL_DIR), name="uploads")
