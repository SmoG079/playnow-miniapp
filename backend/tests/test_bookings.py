import pytest
from datetime import datetime, timedelta, timezone, time, date
from zoneinfo import ZoneInfo
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock, patch, call
from fastapi import HTTPException
from app.api.v1.bookings import create_booking
from app.models.models import (
    User, UserRole, Venue, VenueStatus, VenueTimeSlot, SlotStatus,
    Club, BookingOrder, OrderStatus,
)
from app.schemas.schemas import BookingCreateRequest


class FakeResult:
    def __init__(self, row):
        self.row = row

    def scalar_one_or_none(self):
        return self.row

    def scalar(self):
        return self.row

    def one_or_none(self):
        return self.row

    def scalars(self):
        class FakeScalars:
            def __init__(self, rows):
                self.rows = rows
            def all(self):
                return self.rows
        return FakeScalars(self.row if isinstance(self.row, list) else [self.row])

    def first(self):
        return self.row

    def all(self):
        return self.row if isinstance(self.row, list) else [self.row]


class FakeSession:
    def __init__(self, rows_map=None):
        self.rows_map = rows_map or {}
        self.committed = False
        self.flushed = False
        self._added = []

    async def execute(self, stmt):
        stmt_str = str(stmt)
        # Try exact key match first
        for key, row in self.rows_map.items():
            if key in stmt_str:
                return FakeResult(row)
        # Fallback: if the statement contains a model name, try matching by model name
        if "venue_time_slots" in stmt_str.lower() and "VenueTimeSlot" in self.rows_map:
            return FakeResult(self.rows_map["VenueTimeSlot"])
        if "venues" in stmt_str.lower() and "Venue" in self.rows_map:
            return FakeResult(self.rows_map["Venue"])
        if "clubs" in stmt_str.lower() and "Club" in self.rows_map:
            return FakeResult(self.rows_map["Club"])
        return FakeResult(None)

    def add(self, obj):
        self._added.append(obj)
        if isinstance(obj, BookingOrder):
            obj.id = 1
            obj.order_no = "ORD001"
            obj.created_at = datetime.utcnow()

    async def flush(self):
        self.flushed = True

    async def refresh(self, obj):
        pass

    async def commit(self):
        self.committed = True


@pytest.fixture
def user():
    return User(
        id=1,
        openid="openid_123",
        nickname="Test",
        role=UserRole.user,
    )


@pytest.fixture
def venue():
    return Venue(
        id=1,
        club_id=1,
        name="Court A",
        sport_type="badminton",
        price_per_hour=Decimal("50.00"),
        status=VenueStatus.active,
    )


@pytest.fixture
def club():
    return Club(
        id=1,
        name="Test Club",
        sport_types=["badminton"],
        split_ratio=Decimal("0.100"),
    )


@pytest.fixture
def settings_mock():
    settings = MagicMock()
    settings.BOOKING_LOCK_TTL_SECONDS = 600
    return settings


# ---------------------------------------------------------------------------
# P1-2: reject past slots
# ---------------------------------------------------------------------------

def _make_end_time(d: date, t: time) -> time:
    """Return a time one hour after the given date+time."""
    return (datetime.combine(d, t) + timedelta(hours=1)).time()


@pytest.mark.asyncio
async def test_create_booking_rejects_yesterday(user, venue, club, settings_mock):
    """P1-2: reject a slot from yesterday."""
    tz = ZoneInfo("Asia/Shanghai")
    past_date = (datetime.now(tz) - timedelta(days=1)).date()
    slot_time = time(10, 0)

    slot = VenueTimeSlot(
        id=1,
        venue_id=venue.id,
        date=past_date,
        start_time=slot_time,
        end_time=_make_end_time(past_date, slot_time),
        status=SlotStatus.available,
    )

    session = FakeSession(rows_map={
        "VenueTimeSlot": slot,
        "Venue": venue,
        "Club": club,
    })

    req = BookingCreateRequest(slot_id=1)

    with patch("app.api.v1.bookings.get_settings", return_value=settings_mock), \
         patch("app.api.v1.bookings.acquire_lock", new=AsyncMock(return_value=True)):
        with pytest.raises(HTTPException) as exc_info:
            await create_booking(req, current_user=user, db=session)

    assert exc_info.value.status_code == 400
    assert "already passed" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_create_booking_rejects_today_past_time(user, venue, club, settings_mock):
    """P1-2: reject a slot from today whose start time has already passed."""
    tz = ZoneInfo("Asia/Shanghai")
    today = datetime.now(tz).date()
    past_time = time(0, 0)  # midnight is always in the past

    slot = VenueTimeSlot(
        id=1,
        venue_id=venue.id,
        date=today,
        start_time=past_time,
        end_time=_make_end_time(today, past_time),
        status=SlotStatus.available,
    )

    session = FakeSession(rows_map={
        "VenueTimeSlot": slot,
        "Venue": venue,
        "Club": club,
    })

    req = BookingCreateRequest(slot_id=1)

    with patch("app.api.v1.bookings.get_settings", return_value=settings_mock), \
         patch("app.api.v1.bookings.acquire_lock", new=AsyncMock(return_value=True)):
        with pytest.raises(HTTPException) as exc_info:
            await create_booking(req, current_user=user, db=session)

    assert exc_info.value.status_code == 400
    assert "already passed" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_create_booking_accepts_today_future_time(user, venue, club, settings_mock):
    """P1-2: accept a slot from today whose start time is still in the future."""
    tz = ZoneInfo("Asia/Shanghai")
    today = datetime.now(tz).date()
    future_time = time(23, 59)  # near end of day, almost always in the future

    slot = VenueTimeSlot(
        id=1,
        venue_id=venue.id,
        date=today,
        start_time=future_time,
        end_time=_make_end_time(today, future_time),
        status=SlotStatus.available,
    )

    session = FakeSession(rows_map={
        "VenueTimeSlot": slot,
        "Venue": venue,
        "Club": club,
    })

    req = BookingCreateRequest(slot_id=1)

    with patch("app.api.v1.bookings.get_settings", return_value=settings_mock), \
         patch("app.api.v1.bookings.acquire_lock", new=AsyncMock(return_value=True)):
        result = await create_booking(req, current_user=user, db=session)

    assert result.status == "pending"
    assert result.slot_id == 1


@pytest.mark.asyncio
async def test_create_booking_accepts_tomorrow(user, venue, club, settings_mock):
    """P1-2: accept a slot from tomorrow."""
    tz = ZoneInfo("Asia/Shanghai")
    future_date = (datetime.now(tz) + timedelta(days=1)).date()
    slot_time = time(10, 0)

    slot = VenueTimeSlot(
        id=1,
        venue_id=venue.id,
        date=future_date,
        start_time=slot_time,
        end_time=_make_end_time(future_date, slot_time),
        status=SlotStatus.available,
    )

    session = FakeSession(rows_map={
        "VenueTimeSlot": slot,
        "Venue": venue,
        "Club": club,
    })

    req = BookingCreateRequest(slot_id=1)

    with patch("app.api.v1.bookings.get_settings", return_value=settings_mock), \
         patch("app.api.v1.bookings.acquire_lock", new=AsyncMock(return_value=True)):
        result = await create_booking(req, current_user=user, db=session)

    assert result.status == "pending"
    assert result.slot_id == 1


# ---------------------------------------------------------------------------
# P1-10: booking config endpoint
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_booking_config_returns_free_cancel_hours():
    """P1-10: /bookings/config should return free_cancel_hours from settings."""
    from app.api.v1.bookings import get_booking_config
    settings_mock = MagicMock()
    settings_mock.FREE_CANCEL_HOURS = 24

    with patch("app.api.v1.bookings.settings", settings_mock):
        result = await get_booking_config()

    assert result == {"free_cancel_hours": 24}
