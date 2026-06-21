# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Project Overview

网球俱乐部（PlayNow）是一款网球场地预约 + 约球社交 + 比赛报名的微信小程序平台。俱乐部发布场地信息，用户在线预约并支付，平台提供约球广场和比赛系统。当前聚焦网球，所有前端运动类型已固定为网球。

## Architecture

### Frontend (`miniprogram/`)

Native WeChat Mini Program (WXML/WXSS/JS). No build step.

- **5-tab custom tab bar** (`custom-tab-bar/`) with a "+" center button for role-aware actions
- **Auth flow**: `wx.login()` → backend `/auth/login` → JWT access_token(2h) + refresh_token(30d) stored in Storage. Auto-refresh on 401.
- **Request layer**: `app.js::request()` auto-attaches `Authorization: Bearer` header, handles 401 refresh.
- **Role system**: 3 roles — `user`, `club_admin`, `platform_admin`. `utils/permission.js` provides guards.
- **Dev login**: Backend `/auth/login` supports `code` starting with `dev_` to bypass WeChat API. Frontend `auth.js` falls back to `dev_<timestamp>` when `wx.login()` fails.

### Backend (`backend/`)

Python 3.11 + FastAPI + SQLAlchemy 2.0 (async) + MySQL 8.0 + Redis 7.

- **Entry**: `app/main.py` registers routers under `/api/v1`. DB schema managed by Alembic OR `Base.metadata.create_all` on startup.
- **Database**: `app/core/database.py` uses `create_async_engine` with `asyncmy` driver. **Important**: `asyncmy` returns enum columns as strings and TIME columns as `timedelta` — always use `_v()` helper and convert timedelta to time.
- **Auth**: JWT via `app/core/security.py`. Dependencies: `get_current_user`, `get_club_admin` in `deps.py`.
- **Redis locks**: Slot booking uses Redis SET NX EX. Key pattern: `slot:{venue_id}:{date}:{start_time}`. TTL 600s. Expired locks auto-detected on slot listing.
- **Payment**: Placeholder — `POST /bookings/{id}/pay` directly marks order as paid. WeChat Pay V3 integration pending.
- **Models**: 15 tables (users, clubs, club_members, venues, venue_time_slots, booking_orders, settlement_records, match_posts, match_registrations, tournaments, tournament_registrations, notifications, comments, payment_logs, refund_records).
- **Key relationships**: Club → Venue → VenueTimeSlot. BookingOrder links User+Venue+Slot+Club.

## Key Rules

### Venue & Slot Model
- `Club.opening_time` / `Club.closing_time` control slot generation (not Venue)
- Slots are 30-min intervals, generated for next 3 days on venue creation
- Minimum booking: 1 hour (2 consecutive 30-min slots)
- `Venue.price_rules` supports special pricing: `date_range` (with optional time) and `daily_time`
- Slot listing auto-detects expired Redis locks and resets DB status

### Match Post Modes
- **自由约球** (free): No club required, any user can create
- **定场约球** (venue-linked): Requires club admin, must book a venue slot first. Clicking "去定场" navigates to venue-detail → payment → returns via globalData

### Permission Rules
- **约球帖**: Free mode = any user; Venue mode = club_admin only
- **比赛**: club_admin only
- **场地管理**: club_admin only, accessed from club-dashboard
- Phone number required for booking/registration (enforced in frontend)

### Price Rules
- Default: venue hourly price
- `date_range`: applies specific dates, optionally gated by time window
- `daily_time`: applies every day during time window
- Rules stored in `venues.price_rules` JSON field

## Development Commands

```bash
cd backend
uvicorn app.main:app --reload --port 8000

# Pre-flight check
bash scripts/preflight.sh

# Smoke tests
python backend/tests/smoke_test.py
```

### Mini Program
Open `miniprogram/` in WeChat Developer Tools. `baseURL` in `app.js` → `http://127.0.0.1:8000/api/v1`. Enable "不校验合法域名" in local settings.

## Branch Structure
- `master` — main branch (merged PR #1)
- `dev-20260621-0` — dev first edition (pre-merge)
- `dev-20260621-1` — current working branch based on master
- `mix-20260621-0` — experiment merge branch
- `snapshot-2026-06-20` — zg73's PR #1 source
