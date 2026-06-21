import os
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, Depends
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings
from app.core.database import engine
from app.api.deps import get_current_user
from app.api.v1 import auth, users, clubs, venues, bookings, posts, tournaments

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Database schema is managed by Alembic migrations.
    # Run: docker-compose exec api alembic upgrade head
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


@app.post("/api/v1/upload")
async def upload_file(
    file: UploadFile = File(...),
    _=Depends(get_current_user),
):
    """Upload an image file. Returns {url, filename}."""
    upload_dir = os.path.join(os.path.dirname(__file__), "..", "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    ext = os.path.splitext(file.filename or "img.jpg")[1] or ".jpg"
    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(upload_dir, filename)
    content = await file.read()
    with open(filepath, "wb") as f:
        f.write(content)
    base = f"http://127.0.0.1:8000/uploads/{filename}"
    return {"url": base, "filename": filename}


# Serve uploaded files
from fastapi.staticfiles import StaticFiles
uploads_path = os.path.join(os.path.dirname(__file__), "..", "uploads")
os.makedirs(uploads_path, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=uploads_path), name="uploads")
