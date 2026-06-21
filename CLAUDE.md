# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PlayNow is a WeChat Mini Program SaaS platform for sports clubs (badminton, basketball, tennis, etc.). Clubs publish venue schedules; users book slots and pay via WeChat Pay. The platform settles with clubs via WeChat's profit-sharing API.

## Architecture

### Frontend (`miniprogram/`)

Native WeChat Mini Program (WXML/WXSS/JS). No build step.

- **5-tab custom tab bar** (`custom-tab-bar/`) with a "+" publish button that opens a role-aware action sheet
- **Auth flow**: `wx.login()` → code-to-backend → JWT access + refresh tokens stored in `wx.getStorageSync`
- **Request layer**: `app.js::request()` is the primary HTTP wrapper. It auto-attaches `Authorization: Bearer` headers, handles 401 by calling `refreshTokenAndRetry()`, and falls back to login page on refresh failure. `utils/request.js` is an alternative module wrapper around the same logic.
- **Role system**: 3 roles — `user`, `club_admin`, `platform_admin`. `globalData.role` and `globalData.managedClubIds` drive UI visibility. Backend enforces final authorization.
- **Permission guards** (`utils/permission.js`): `requireLogin()`, `requireClubAdmin()`, `canManageClub(clubId)` — use these in page `onShow`/`onTap` handlers.

### Backend (`backend/`)

Python 3.12 + FastAPI + SQLAlchemy 2.0 (async) + MySQL 8.0 + Redis 7 + Celery.

- **Entry**: `app/main.py` registers routers under `/api/v1`. Database schema is managed by Alembic migrations; run `alembic upgrade head` before starting the app.
- **Database**: `app/core/database.py` uses `create_async_engine` with `asyncmy` driver. `get_db()` is an async generator dependency that auto-commits on success and rolls back on exception.
- **Auth**: JWT access + refresh tokens (`app/core/security.py`). `app/api/deps.py` provides `get_current_user`, `get_club_admin`, `get_platform_admin` dependencies.
  - **Important**: `deps.py` defines `_v(field)` helper because `asyncmy` returns enum columns as strings, not enum objects. Always use `_v()` when comparing enum fields in Python code.
- **Redis locks** (`app/core/redis.py`): Used for venue slot booking. Lock key pattern: `slot:{venue_id}:{date}:{start_time}`. TTL defaults to 600s (10 min).
- **Celery tasks** (`app/tasks/`):
  - `release_expired_locks` runs every 60s to free slots where payment never completed
  - Broker and result backend both use Redis
  - Worker command: `celery -A app.tasks.worker worker -l info -c 2`
  - Beat command: `celery -A app.tasks.worker beat -l info`
- **Models** (`app/models/models.py`): 12 tables. Key relationships:
  - `Club` → `Venue` → `VenueTimeSlot`
  - `BookingOrder` links `User`, `Venue`, `VenueTimeSlot`, `Club`
  - `SettlementRecord` is 1:1 with `BookingOrder` (profit sharing after 30 days)
  - `ClubMember` bridges `User` and `Club` (owner/admin roles)
- **API routes** (`app/api/v1/`): 7 modules — `auth`, `users`, `clubs`, `venues`, `bookings`, `posts`, `tournaments`
- **WeChat Pay V3** (`wechatpayv3` library): Used in `bookings.py` for native payments and profit sharing.
- **OSS**: Alibaba Cloud OSS (`oss2` library) for image uploads.

## Development Commands

### Run everything (Docker Compose)

```bash
# Start all services (nginx, api, celery_worker, celery_beat, mysql, redis)
docker-compose up -d

# View API logs
docker-compose logs -f api

# View Celery worker logs
docker-compose logs -f celery_worker

# Enter API container
docker-compose exec api bash
```

### Backend (inside container or local venv)

```bash
cd backend

# Local development (requires MySQL + Redis running locally)
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with local DB/Redis credentials

# Run API server directly
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run Celery worker
 celery -A app.tasks.worker worker -l info -c 2

# Run Celery beat
 celery -A app.tasks.worker beat -l info
```

### Database

Schema changes are managed with Alembic. The API container uses the async `mysql+asyncmy` driver, while Alembic uses the synchronous `mysql+pymysql` driver; `backend/alembic/env.py` handles the conversion automatically.

```bash
# Fresh database: apply all migrations
# (run after docker-compose up -d, before using the API)
docker-compose exec api alembic upgrade head

# After changing SQLAlchemy models, generate a migration
docker-compose exec api alembic revision --autogenerate -m "description"

# Review the generated file under backend/alembic/versions/, then apply it
docker-compose exec api alembic upgrade head

# Useful commands
docker-compose exec api alembic current      # show current revision
docker-compose exec api alembic history      # show migration history
docker-compose exec api alembic downgrade -1 # rollback one revision
```

For local development without Docker, ensure `DATABASE_URL` is exported and run the same `alembic` commands from the `backend/` directory.

### Mini Program

```bash
# Open in WeChat Developer Tools
# Point the tool at the miniprogram/ directory
```

No build step. Preview/compile happens inside WeChat Developer Tools. The `baseURL` in `miniprogram/app.js` must point to a running backend (local or remote).

## Environment Setup

1. Copy `backend/.env.example` → `backend/.env` and fill in:
   - `WX_APP_ID`, `WX_APP_SECRET` (from WeChat MP console)
   - `WX_MCH_ID`, `WX_MCH_API_V3_KEY`, `WX_MCH_SERIAL_NO` (WeChat Pay merchant)
   - Place `apiclient_key.pem` in `backend/certs/`
   - Place SSL cert (`fullchain.pem`, `privkey.pem`) in `backend/ssl/`
2. Update `miniprogram/app.js` `baseURL` to match your API domain
3. Update `miniprogram/project.config.json` `appid` to your WeChat Mini Program AppID
4. Update `backend/nginx/nginx.conf` `server_name` to your domain

## Key Business Flows

### Booking & Payment

1. User selects slot → `POST /bookings` locks slot (Redis + DB `status = locked`)
2. `POST /bookings/{id}/pay` creates WeChat Pay order
3. WeChat callback → `POST /bookings/wx-notify` updates order to `paid`, creates `SettlementRecord`
4. Celery releases expired locks every 60s for unpaid bookings

### Profit Sharing (Settlement)

- 30 days after payment, platform calls WeChat profit-sharing API
- Split ratio per club (`clubs.split_ratio`, default 10% platform / 90% club)
- Settlement status tracked in `settlement_records`

### Role Assignment

- New users default to `user` role
- Creating a club auto-inserts a `ClubMember` record with `owner` role and upgrades user to `club_admin`
- `platform_admin` is manually assigned
