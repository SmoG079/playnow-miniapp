"""Real row-lock and Redis regression tests for the new booking and schedule paths."""

import asyncio
import os
import secrets
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
from unittest.mock import AsyncMock
import pytest
import pytest_asyncio
import redis.asyncio as redis
from fastapi import HTTPException
from sqlalchemy import select, delete, func
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from app.models.models import (
    User,
    Club,
    Venue,
    VenueTimeSlot,
    BookingOrder,
    BookingSlot,
)
from app.api.v1 import bookings, clubs
from app.schemas.schemas import BookingCreateRequest, CancelRequest

URL = os.environ.get("ACTIVITY_MYSQL_TEST_DATABASE_URL")
REDIS = os.environ.get("ACTIVITY_REDIS_TEST_URL")
pytestmark = pytest.mark.skipif(
    not URL or not REDIS, reason="Explicit disposable MySQL and Redis required"
)


@pytest_asyncio.fixture
async def resources(monkeypatch):
    from app.core import redis as core_redis

    url = make_url(URL)
    if (
        url.host not in ("127.0.0.1", "localhost")
        or not (url.database == "test_db" or url.database.startswith("playnow_test_"))
        or not REDIS.endswith("/15")
    ):
        raise RuntimeError("Refusing non-disposable booking integration infrastructure")
    engine = create_async_engine(url, poolclass=NullPool, hide_parameters=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    client = redis.from_url(REDIS, decode_responses=True)
    monkeypatch.setattr(core_redis, "redis_client", client)
    monkeypatch.setattr(bookings, "check_rate_limit", AsyncMock())
    token = secrets.token_hex(8)
    day = datetime.now(ZoneInfo("Asia/Shanghai")).date() + timedelta(days=1)
    async with factory() as db:
        users = [
            User(openid=f"review-booking-{token}-{i}", phone="13800138000")
            for i in range(2)
        ]
        club = Club(
            name="isolated-booking",
            opening_time=time(8),
            closing_time=time(22),
            approval_status="approved",
            status="active",
        )
        db.add_all(users + [club])
        await db.flush()
        venue = Venue(
            club_id=club.id,
            name="court",
            sport_type="tennis",
            price_per_hour=100,
            max_capacity=4,
            status="active",
        )
        db.add(venue)
        await db.flush()
        slots = [
            VenueTimeSlot(
                venue_id=venue.id, date=day, start_time=time(10), end_time=time(10, 30)
            ),
            VenueTimeSlot(
                venue_id=venue.id, date=day, start_time=time(10, 30), end_time=time(11)
            ),
        ]
        db.add_all(slots)
        await db.flush()
        await db.commit()
        user_ids = [u.id for u in users]
        slot_ids = [s.id for s in slots]
        venue_id = venue.id
        club_id = club.id
    try:
        yield factory, client, user_ids, slot_ids, venue_id, club_id, day
    finally:
        async with factory() as db:
            allslots = (
                (
                    await db.execute(
                        select(VenueTimeSlot).where(VenueTimeSlot.venue_id == venue_id)
                    )
                )
                .scalars()
                .all()
            )
            for slot in allslots:
                await client.delete(
                    f"slot:{slot.venue_id}:{slot.date}:{slot.start_time}"
                )
                slot.booking_order_id = None
            await db.flush()
            ids = select(BookingOrder.id).where(BookingOrder.venue_id == venue_id)
            await db.execute(delete(BookingSlot).where(BookingSlot.order_id.in_(ids)))
            await db.execute(
                delete(BookingOrder).where(BookingOrder.venue_id == venue_id)
            )
            await db.execute(
                delete(VenueTimeSlot).where(VenueTimeSlot.venue_id == venue_id)
            )
            await db.execute(delete(Venue).where(Venue.id == venue_id))
            await db.execute(delete(Club).where(Club.id == club_id))
            await db.execute(delete(User).where(User.id.in_(user_ids)))
            await db.commit()
        await client.aclose()
        await engine.dispose()


@pytest.mark.asyncio
async def test_two_users_competing_for_same_pair_get_one_booking(resources):
    factory, client, user_ids, slot_ids, *_ = resources
    gate = asyncio.Event()

    async def compete(uid):
        async with factory() as db:
            user = await db.get(User, uid)
            await gate.wait()
            try:
                result = await bookings.create_booking(
                    BookingCreateRequest(slot_ids=slot_ids), user, db
                )
                await db.commit()
                return 200, result.id
            except HTTPException as exc:
                await db.rollback()
                return exc.status_code, None

    tasks = [asyncio.create_task(compete(uid)) for uid in user_ids]
    gate.set()
    results = await asyncio.gather(*tasks, return_exceptions=True)
    assert all(isinstance(result, tuple) for result in results), results
    assert sorted(code for code, _ in results) == [200, 409]
    winner = next(ident for code, ident in results if code == 200)
    async with factory() as db:
        assert (
            await db.execute(
                select(func.count(BookingSlot.id)).where(BookingSlot.order_id == winner)
            )
        ).scalar_one() == 2
        for sid in slot_ids:
            assert (await db.get(VenueTimeSlot, sid)).booking_order_id == winner


@pytest.mark.asyncio
async def test_concurrent_grid_generation_preserves_single_nonoverlapping_schedule(
    resources,
):
    factory, client, user_ids, slot_ids, venue_id, club_id, day = resources
    gate = asyncio.Event()

    async def load():
        async with factory() as db:
            await gate.wait()
            result = await clubs.get_club_venue_slots(club_id, day, venue_id, db)
            await db.commit()
            return result

    tasks = [asyncio.create_task(load()) for _ in range(2)]
    gate.set()
    results = await asyncio.gather(*tasks)
    assert all(len(r.rows) == 28 for r in results)
    async with factory() as db:
        rows = (
            (
                await db.execute(
                    select(VenueTimeSlot)
                    .where(
                        VenueTimeSlot.venue_id == venue_id, VenueTimeSlot.date == day
                    )
                    .order_by(VenueTimeSlot.start_time)
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 28 and all(
            a.end_time == b.start_time for a, b in zip(rows, rows[1:])
        )


@pytest.mark.asyncio
async def test_expired_order_rebooking_and_old_cancel_do_not_release_new_order(
    resources,
):
    factory, client, user_ids, slot_ids, venue_id, club_id, day = resources
    async with factory() as db:
        user = await db.get(User, user_ids[0])
        old = await bookings.create_booking(
            BookingCreateRequest(slot_ids=slot_ids), user, db
        )
        (await db.get(BookingOrder, old.id)).created_at = datetime.utcnow() - timedelta(
            minutes=20
        )
        await db.commit()
        for sid in slot_ids:
            slot = await db.get(VenueTimeSlot, sid)
            await client.delete(f"slot:{slot.venue_id}:{slot.date}:{slot.start_time}")
    async with factory() as db:
        new = await bookings.create_booking(
            BookingCreateRequest(slot_ids=slot_ids), await db.get(User, user_ids[0]), db
        )
        await db.commit()
    async with factory() as db:
        with pytest.raises(HTTPException):
            await bookings.cancel_booking(
                old.id, CancelRequest(), await db.get(User, user_ids[0]), db
            )
        await db.rollback()
        for sid in slot_ids:
            slot = await db.get(VenueTimeSlot, sid)
            assert slot.booking_order_id == new.id and slot.status.value == "locked"
            assert (
                await client.get(f"slot:{slot.venue_id}:{slot.date}:{slot.start_time}")
                == f"booking:{new.order_no}"
            )


@pytest.mark.asyncio
async def test_booking_and_schedule_generation_share_venue_first_lock_order(resources):
    factory, client, user_ids, slot_ids, venue_id, club_id, day = resources
    gate = asyncio.Event()

    async def book():
        async with factory() as db:
            user = await db.get(User, user_ids[0])
            await gate.wait()
            result = await bookings.create_booking(
                BookingCreateRequest(slot_ids=slot_ids), user, db
            )
            await db.commit()
            return result.id

    async def schedule():
        async with factory() as db:
            await gate.wait()
            result = await clubs.get_club_venue_slots(club_id, day, venue_id, db)
            await db.commit()
            return len(result.rows)

    tasks = [asyncio.create_task(book()), asyncio.create_task(schedule())]
    gate.set()
    results = await asyncio.gather(*tasks, return_exceptions=True)
    assert all(isinstance(result, int) for result in results), results
    assert results[1] == 28
    async with factory() as db:
        for sid in slot_ids:
            assert (await db.get(VenueTimeSlot, sid)).booking_order_id == results[0]


def test_sync_task_resources_work_across_success_failure_and_new_event_loops(
    monkeypatch,
):
    from types import SimpleNamespace
    from sqlalchemy import text
    from app.tasks import runtime

    if (
        make_url(URL).host not in ("127.0.0.1", "localhost")
        or not make_url(URL).database.startswith("playnow_test_")
        or not REDIS.endswith("/15")
    ):
        raise RuntimeError("Refusing non-disposable task resources")
    monkeypatch.setattr(
        runtime,
        "get_settings",
        lambda: SimpleNamespace(DATABASE_URL=URL, REDIS_URL=REDIS),
    )
    loops = []
    key = "review-task:" + secrets.token_hex(16)

    async def exercise(fail=False):
        loops.append(asyncio.get_running_loop())
        async with runtime.task_session_factory.get()() as session:
            assert await session.scalar(text("SELECT 1")) == 1
        client = runtime.task_redis_client.get()
        await client.set(key, "isolated", ex=60)
        assert await client.get(key) == "isolated"
        await client.delete(key)
        if fail:
            raise ValueError("isolated task failure")
        return True

    assert runtime.run_async_task(exercise)
    with pytest.raises(ValueError):
        runtime.run_async_task(exercise, True)
    assert runtime.run_async_task(exercise)
    assert len({id(loop) for loop in loops}) == 3
    assert all(loop.is_closed() for loop in loops)
    assert (
        runtime.task_session_factory.get() is None
        and runtime.task_redis_client.get() is None
    )
