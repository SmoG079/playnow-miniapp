"""Publishing permissions against a disposable database; no payment API calls."""
import pytest
import pytest_asyncio
from contextlib import asynccontextmanager
from app.services import activity_ids
from fastapi import HTTPException
from sqlalchemy import BigInteger, select, func
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.models.models import (
    Base, User, UserRole, Club, Venue, BookingOrder, OrderStatus, MatchPost,
)
from app.schemas.schemas import PostCreate, PostUpdate
from app.api.v1.posts import create_post, update_post


@compiles(BigInteger, "sqlite")
def sqlite_bigint(type_, compiler, **kw):
    return "INTEGER"


@pytest_asyncio.fixture
async def db(monkeypatch):
    @asynccontextmanager
    async def sql_only_lock():
        yield
    monkeypatch.setattr(activity_ids, "allocation_lock", sql_only_lock)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        session.add_all([
            User(id='1', openid="post-user", nickname="用户", role=UserRole.user),
            User(id='2', openid="other-user", role=UserRole.user),
            Club(id=1, name="俱乐部"), Club(id=2, name="其他俱乐部"),
            Venue(id=1, club_id=1, name="场地", sport_type="tennis", price_per_hour=100),
            Venue(id=2, club_id=2, name="其他场地", sport_type="tennis", price_per_hour=100),
            BookingOrder(id=1, order_no="post-booking", user_id='1', club_id=1,
                         venue_id=1, amount=100, status=OrderStatus.paid),
        ])
        await session.commit()
        yield session
    await engine.dispose()


def request(**kwargs):
    return PostCreate(title="一起打球", price=0, preferred_date="2026-11-01", preferred_start="09:00", preferred_end="11:00", players_needed=2, **kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize("role", list(UserRole))
async def test_all_roles_can_publish_own_booked_post_without_club_membership(db, role):
    user = await db.get(User, 1)
    user.role = role
    post = await create_post(request(booking_id=1, venue_id=1, club_id=1), user, db)
    assert (post.user_id, post.club_id, post.booking_id, post.venue_id) == ("1", 1, 1, 1)


@pytest.mark.asyncio
async def test_free_post_still_needs_no_club(db):
    post = await create_post(request(), await db.get(User, 1), db)
    assert post.club_id is None and post.booking_id is None


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [s for s in OrderStatus if s != OrderStatus.paid])
async def test_unpaid_cancelled_or_finished_booking_cannot_be_linked(db, status):
    (await db.get(BookingOrder, 1)).status = status
    with pytest.raises(HTTPException) as exc:
        await create_post(request(booking_id=1, venue_id=1), await db.get(User, 1), db)
    assert exc.value.status_code == 422
    assert await db.scalar(select(func.count(MatchPost.id))) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("fields,code", [
    ({"booking_id": 1, "venue_id": 1}, 403),
    ({"booking_id": 999, "venue_id": 1}, 403),
])
async def test_cannot_use_other_users_or_missing_booking(db, fields, code):
    with pytest.raises(HTTPException) as exc:
        await create_post(request(**fields), await db.get(User, 2), db)
    assert exc.value.status_code == code


@pytest.mark.asyncio
@pytest.mark.parametrize("fields", [
    {"booking_id": 1, "venue_id": 2},
    {"booking_id": 1, "venue_id": 1, "club_id": 2},
    {"venue_id": 1, "club_id": 1},
])
async def test_mismatched_or_unbooked_venue_rejected(db, fields):
    with pytest.raises(HTTPException) as exc:
        await create_post(request(**fields), await db.get(User, 1), db)
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_tournament_order_cannot_be_used_as_booking(db):
    (await db.get(BookingOrder, 1)).business_type = "tournament"
    with pytest.raises(HTTPException):
        await create_post(request(booking_id=1), await db.get(User, 1), db)


@pytest.mark.asyncio
async def test_edit_cannot_bypass_booking_ownership_and_unlink_becomes_free(db):
    user = await db.get(User, 2)
    free = await create_post(request(), user, db)
    with pytest.raises(HTTPException) as exc:
        await update_post(free.id, PostUpdate(booking_id=1, venue_id=1), user, db)
    assert exc.value.status_code == 403
    owner = await db.get(User, 1)
    linked = await create_post(request(booking_id=1), owner, db)
    await update_post(linked.id, PostUpdate(booking_id=None, venue_id=None), owner, db)
    stored = await db.get(MatchPost, linked.id)
    assert stored.club_id is None and stored.venue_id is None and stored.booking_id is None
