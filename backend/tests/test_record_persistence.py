"""Database-backed records and club permissions on an isolated SQLite database."""
from datetime import datetime, time
import pytest
from fastapi import FastAPI, HTTPException
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import async_sessionmaker
from tests.test_post_booking_permissions import db  # isolated fixture
from app.models.models import (
    User, UserRole, Club, ClubMember, ClubStatus, MatchPost, MatchPostStatus, Activity,
    MatchRegistration, RegistrationStatus, Venue,
)
from app.api.v1 import users, clubs, posts, venues
from app.api.deps import get_current_user
from app.core.database import get_db
from app.schemas.schemas import (
    ClubCreate, ClubUpdate, RegisterPostRequest, ReviewRegistrationRequest,
    VenueCreate, VenueUpdate,
)


@pytest.mark.asyncio
async def test_daily_slots_use_club_hours_half_hours_and_preserve_existing_intervals(db, monkeypatch):
    from datetime import date, timedelta
    from app.models.models import VenueTimeSlot
    from app.tasks import tasks

    class ShanghaiMidnight(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2030, 1, 2, 0, 15, tzinfo=tz)

    monkeypatch.setattr(tasks, "datetime", ShanghaiMidnight)
    club = await db.get(Club, 1)
    club.opening_time, club.closing_time = time(9, 30), time(11)
    (await db.get(Venue, 2)).status = "closed"
    db.add(VenueTimeSlot(venue_id=1, date=date(2030, 1, 2), start_time=time(9, 30), end_time=time(10, 30)))
    await db.commit()
    monkeypatch.setattr(tasks, "async_session_factory", async_sessionmaker(db.bind, expire_on_commit=False))
    assert await tasks._generate_daily_slots_impl() == 7
    assert await tasks._generate_daily_slots_impl() == 0
    slots = (await db.execute(select(VenueTimeSlot).order_by(VenueTimeSlot.date, VenueTimeSlot.start_time))).scalars().all()
    assert len(slots) == 8 and all(s.venue_id == 1 for s in slots)
    assert [(s.start_time, s.end_time) for s in slots[:2]] == [(time(9, 30), time(10, 30)), (time(10, 30), time(11))]
    assert slots[-1].date == date(2030, 1, 2) + timedelta(days=2)


@pytest.mark.asyncio
async def test_cleanup_keeps_legacy_and_all_json_order_slots(db, monkeypatch):
    from datetime import timedelta
    from zoneinfo import ZoneInfo
    from app.models.models import VenueTimeSlot, BookingOrder
    from app.tasks import tasks

    old = datetime.now(ZoneInfo("Asia/Shanghai")).date() - timedelta(days=40)
    for ident in range(1, 6):
        db.add(VenueTimeSlot(id=ident, venue_id=1, date=old, start_time=time(ident), end_time=time(ident, 30)))
    await db.flush()
    legacy = await db.get(BookingOrder, 1)
    legacy.slot_id = 1
    legacy.status = "cancelled"
    db.add(BookingOrder(order_no="review-multi", user_id="1", venue_id=1, club_id=1,
                        slot_id=2, slot_ids=[2, 3], amount=100, status="cancelled"))
    (await db.get(VenueTimeSlot, 5)).status = "booked"
    await db.commit()
    monkeypatch.setattr(tasks, "async_session_factory", async_sessionmaker(db.bind, expire_on_commit=False))
    assert await tasks._cleanup_old_slots_impl() == 1
    assert set((await db.execute(select(VenueTimeSlot.id))).scalars()) == {1, 2, 3, 5}
    assert await tasks._cleanup_old_slots_impl() == 0


@pytest.mark.parametrize("payload", [
    {"price_per_hour": -1}, {"price_per_hour": 0}, {"max_capacity": 0},
    {"name": None}, {"status": None}, {"price_per_hour": None}, {"status": "booked"},
])
def test_invalid_venue_edits_are_rejected_before_database(payload):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        VenueUpdate(**payload)


@pytest.mark.asyncio
async def test_club_daily_stats_use_shanghai_day_for_utc_timestamps(db, monkeypatch):
    from app.models.models import BookingOrder

    class ShanghaiMorning(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2030, 1, 2, 1, tzinfo=tz)

    monkeypatch.setattr(clubs, "datetime", ShanghaiMorning)
    (await db.get(BookingOrder, 1)).created_at = datetime(2029, 1, 1)
    for ident, created in enumerate([
        datetime(2030, 1, 1, 15, 59, 59), datetime(2030, 1, 1, 16),
        datetime(2030, 1, 2, 15, 59, 59), datetime(2030, 1, 2, 16),
    ]):
        db.add(BookingOrder(order_no=f"daily-stats-{ident}", user_id="1", club_id=1,
                            venue_id=1, amount=10, status="paid", created_at=created))
    await db.flush()
    result = await clubs.club_stats(1, await db.get(User, 1), db)
    assert result.today_orders == 2 and result.today_revenue == 20


@pytest.mark.asyncio
async def test_personal_records_paginate_and_isolate_accounts_without_local_state(db):
    db.add_all([Activity(id=i, kind="post") for i in range(1, 54)])
    await db.flush()
    for i in range(1, 54):
        db.add(MatchPost(id=i, user_id='2', title=f"约球{i}", club_id=1 if i % 2 else None,
                         price=0, status=MatchPostStatus.closed if i == 1 else MatchPostStatus.open))
        db.add(MatchRegistration(id=i, post_id=i, user_id='1',
            status=list(RegistrationStatus)[i % len(RegistrationStatus)],
            message="本人的留言", created_at=datetime(2026, 10, 7)))
    db.add(MatchRegistration(id=54, post_id=1, user_id='2', message="其他账号的留言"))
    await db.commit()
    async with async_sessionmaker(db.bind, expire_on_commit=False)() as fresh:
        user = await fresh.get(User, 1)
        first = await users.my_post_registrations(1, 50, user, fresh)
        last = await users.my_post_registrations(2, 50, user, fresh)
        assert first.total == last.total == 53
        assert len(first.items) == 50 and len(last.items) == 3
        assert [r.id for r in first.items + last.items] == list(range(53, 0, -1))
        assert all(r.user_id == "1" for r in first.items + last.items)
        assert any(r.club_id is None for r in first.items)
        assert last.items[-1].post_status == "closed"
        other = await users.my_post_registrations(1, 50, await fresh.get(User, 2), fresh)
        assert other.total == 1 and other.items[0].message == "其他账号的留言"


@pytest.mark.asyncio
async def test_cancel_keeps_record_reopens_capacity_and_can_register_again(db):
    user = await db.get(User, 1)
    db.add(Activity(id=1, kind="post"))
    await db.flush()
    db.add(MatchPost(id=1, user_id='2', title="约球", price=0, players_needed=1))
    await db.flush()
    await posts.register_post(1, RegisterPostRequest(message="报名"), user, db)
    assert (await db.get(MatchPost, 1)).status == MatchPostStatus.full
    await posts.cancel_register(1, user, db)
    await posts.cancel_register(1, user, db)  # retry is safe
    record = await users.my_post_registrations(1, 50, user, db)
    assert record.total == 1 and record.items[0].status == "cancelled"
    assert (await db.get(MatchPost, 1)).status == MatchPostStatus.open
    owned = await users.my_posts(1, 50, await db.get(User, 2), db)
    assert owned.items[0].registration_count == 0
    with pytest.raises(HTTPException) as exc:
        await posts.review_registration(1, user.public_id, ReviewRegistrationRequest(status="approved"),
                                        await db.get(User, 2), db)
    assert exc.value.status_code == 409
    await posts.register_post(1, RegisterPostRequest(message="重新报名"), user, db)
    record = await users.my_post_registrations(1, 50, user, db)
    assert record.total == 1 and record.items[0].status == "approved"


@pytest.mark.asyncio
async def test_venue_configuration_survives_new_session_and_partial_edit(db):
    rules = [{"type": "daily_time", "start_time": "18:00", "end_time": "20:00", "price": 150}]
    created = await venues.create_venue_for_club(1, VenueCreate(
        name="新场地", price_per_hour=100, price_rules=rules, max_capacity=6,
        cover_image="https://test/court.png",
    ), await db.get(User, 1), db)
    await db.commit()
    async with async_sessionmaker(db.bind, expire_on_commit=False)() as fresh:
        result = await venues.get_venue(created.id, fresh)
        assert result.price_rules == rules and result.max_capacity == 6
        changed = await venues.update_venue(created.id, 1, VenueUpdate(name="改名"),
                                            await fresh.get(User, 1), fresh)
        assert changed.price_rules == rules and changed.cover_image == "https://test/court.png"


@pytest.mark.asyncio
async def test_club_data_round_trip_and_edit_preserves_other_fields(db):
    user = await db.get(User, 1)
    from app.models.models import PrivateUpload
    from app.core.config import get_settings
    filename = "review-private-rules.pdf"
    db.add(PrivateUpload(id=filename, user_id=user.id, backend="local", content_type="application/pdf"))
    await db.flush()
    created = await clubs.create_club(ClubCreate(
        name="新俱乐部", sport_types=["tennis"], rules="请穿网球鞋",
        description="介绍", contact_phone="13800138000", address="地址",
        opening_time="09:30", closing_time="20:30", images=["https://test/image.png"],
        documents=[{"name": "规则", "url": f"{get_settings().PUBLIC_BASE_URL}/api/v1/media/doc/{filename}"}],
    ), user, db)
    assert (created.rules, created.opening_time, created.closing_time) == ("请穿网球鞋", "09:30", "20:30")
    assert created.approval_status == "pending" and user.role == UserRole.user
    from app.api.v1.applications import review_club, ClubReview
    reviewer = await db.get(User, 2)
    reviewer.role = UserRole.platform_admin
    await review_club(created.id, ClubReview(approved=True), reviewer, db)
    await db.commit()
    async with async_sessionmaker(db.bind, expire_on_commit=False)() as fresh:
        club = await fresh.get(Club, created.id)
        assert club.images == ["https://test/image.png"] and club.documents[0]["name"] == "规则"
        updated = await clubs.update_club(created.id, ClubUpdate(name="改名", opening_time="10:00"), user, fresh)
        assert updated.rules == "请穿网球鞋" and updated.documents == created.documents
        assert updated.opening_time == "10:00" and updated.closing_time == "20:30"
        await fresh.commit()
    await db.refresh(user)
    assert user.role == UserRole.club_admin
    listed = await clubs.managed_clubs(1, 50, user, db)
    assert [c.id for c in listed.items] == [created.id]
    with pytest.raises(HTTPException):
        await clubs.update_club(created.id, ClubUpdate(closing_time="09:00"), user, db)


@pytest.mark.asyncio
async def test_http_club_scope_cannot_be_spoofed_and_role_changes_are_immediate(db):
    user = await db.get(User, 1)
    user.role = UserRole.club_admin
    db.add(ClubMember(user_id='1', club_id=1))
    (await db.get(Club, 1)).status = ClubStatus.inactive
    await db.commit()
    app = FastAPI()
    app.include_router(clubs.router)
    app.include_router(venues.router)
    app.include_router(users.router)
    async def database():
        yield db
    async def current_user():
        return user
    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_current_user] = current_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://isolated") as client:
        listed = await client.get("/clubs/managed")
        assert listed.status_code == 200 and [c["id"] for c in listed.json()["items"]] == [1]
        assert (await client.put("/clubs/2", json={"name": "越权改名"})).status_code == 403
        assert (await client.get("/clubs/2/stats")).status_code == 403
        assert (await client.put("/venues/2/with-club/1", json={"name": "错误归属"})).status_code == 404
        assert (await client.put("/venues/2/with-club/2", json={"name": "越权"})).status_code == 403
        assert (await client.put("/clubs/1", json={"rules": "新的规则"})).status_code == 200
        assert (await db.get(Club, 2)).name == "其他俱乐部"
        user.role = UserRole.platform_admin
        listed = await client.get("/clubs/managed?page_size=1")
        assert listed.json()["total"] == 2 and len(listed.json()["items"]) == 1
        user.role = UserRole.user
        assert (await client.get("/clubs/managed")).status_code == 403
        assert (await client.put("/clubs/1", json={"rules": "权限已收回"})).status_code == 403
