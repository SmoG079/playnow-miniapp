# ruff: noqa: F811
"""Regression coverage for stale bookings, privacy boundaries and new API contracts."""

from datetime import datetime, date, time, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
import pytest
from fastapi import HTTPException, FastAPI
from httpx import AsyncClient, ASGITransport
from pydantic import ValidationError
from sqlalchemy import select
from tests.test_post_booking_permissions import db  # noqa: F401
from app.models.models import (
    User,
    Club,
    VenueTimeSlot,
    BookingOrder,
    BookingSlot,
    Activity,
    MatchPost,
    MatchRegistration,
    Comment,
)
from app.api.v1 import bookings, posts, clubs, users
from app.schemas.schemas import (
    BookingCreateRequest,
    CancelRequest,
    VenueUpdate,
    PostUpdate,
    SlotGenerateRequest,
    ReviewRegistrationRequest,
)
from app.services.public_identity import public_user_id
from app.services.slots import validate_booking_date
from app.core.database import get_db
from app.api.deps import get_optional_user, get_current_user


@pytest.mark.asyncio
async def test_registration_review_resolves_public_user_id(db):
    owner, participant = await db.get(User, "1"), await db.get(User, "2")
    db.add(Activity(id=901, kind="post"))
    await db.flush()
    db.add(
        MatchPost(
            id=901,
            user_id=owner.id,
            title="公开编号审核",
            players_needed=2,
            price=0,
            status="open",
        )
    )
    await db.flush()
    reg = MatchRegistration(post_id=901, user_id=participant.id, status="pending")
    db.add(reg)
    await db.flush()
    with pytest.raises(HTTPException) as error:
        await posts.review_registration(
            901, participant.id, ReviewRegistrationRequest(status="approved"), owner, db
        )
    assert error.value.status_code == 404
    await posts.review_registration(
        901,
        participant.public_id,
        ReviewRegistrationRequest(status="approved"),
        owner,
        db,
    )
    assert getattr(reg.status, "value", reg.status) == "approved"
    from app.models.models import Notification

    notification = await db.scalar(
        select(Notification).where(Notification.ref_id == 901)
    )
    assert notification.user_id == participant.id


async def pending(db, ident, age=0, owner=None):
    day = datetime.now().date() + timedelta(days=1)
    user = await db.get(User, "1")
    if await db.get(VenueTimeSlot, 11) is None:
        db.add_all(
            [
                VenueTimeSlot(
                    id=11,
                    venue_id=1,
                    date=day,
                    start_time=time(10),
                    end_time=time(10, 30),
                    status="locked",
                    locked_by=user.id,
                ),
                VenueTimeSlot(
                    id=12,
                    venue_id=1,
                    date=day,
                    start_time=time(10, 30),
                    end_time=time(11),
                    status="locked",
                    locked_by=user.id,
                ),
            ]
        )
        await db.flush()
    order = BookingOrder(
        id=ident,
        order_no=f"review-{ident}",
        user_id=user.id,
        venue_id=1,
        club_id=1,
        slot_id=11,
        slot_ids=[11, 12],
        amount=100,
        status="pending",
        created_at=datetime.utcnow() - timedelta(minutes=age),
    )
    db.add(order)
    await db.flush()
    for sid in (11, 12):
        db.add(BookingSlot(order_id=ident, slot_id=sid, amount=50))
        slot = await db.get(VenueTimeSlot, sid)
        slot.booking_order_id = owner or ident
        slot.locked_at = order.created_at
    await db.flush()
    return order, user


@pytest.mark.asyncio
@pytest.mark.parametrize("age", [0, 20])
async def test_stale_order_cannot_pay_or_release_new_same_user_order(
    db, monkeypatch, age
):
    old, user = await pending(db, 2, age)
    new, _ = await pending(db, 3)
    release = AsyncMock()
    monkeypatch.setattr("app.services.booking_locks.release_lock", release)
    with pytest.raises(HTTPException) as exc:
        await bookings.pay_booking(2, user, db)
    assert exc.value.status_code == 409
    await bookings.cancel_booking(2, CancelRequest(reason="旧订单"), user, db)
    for sid in (11, 12):
        slot = await db.get(VenueTimeSlot, sid)
        assert slot.booking_order_id == 3 and slot.status == "locked"
    release.assert_not_awaited()
    assert new.status == "pending"


@pytest.mark.asyncio
async def test_current_order_pays_all_slots_once_and_releases_only_its_token(
    db, monkeypatch
):
    order, user = await pending(db, 2)
    release = AsyncMock()
    monkeypatch.setattr(bookings, "release_lock", release)
    await bookings.pay_booking(2, user, db)
    assert order.status == "paid"
    for sid in (11, 12):
        slot = await db.get(VenueTimeSlot, sid)
        assert slot.status == "booked" and slot.booking_order_id == 2
    assert release.await_count == 2
    assert all(c.args[1] == "booking:review-2" for c in release.await_args_list)
    assert (await bookings.pay_booking(2, user, db))["already_paid"]
    assert release.await_count == 2


@pytest.mark.asyncio
async def test_expiry_cancels_old_order_without_touching_new_owner(db, monkeypatch):
    from app.tasks import tasks
    from sqlalchemy.ext.asyncio import async_sessionmaker

    old, user = await pending(db, 2, 20)
    await pending(db, 3)
    await db.commit()
    release = AsyncMock()
    monkeypatch.setattr("app.services.booking_locks.release_lock", release)
    monkeypatch.setattr(
        tasks,
        "async_session_factory",
        async_sessionmaker(db.bind, expire_on_commit=False),
    )
    assert await tasks._release_expired_locks_impl() == 0
    await db.refresh(old)
    assert old.status == "cancelled"
    await db.refresh(await db.get(VenueTimeSlot, 11))
    assert (await db.get(VenueTimeSlot, 11)).booking_order_id == 3
    release.assert_not_awaited()


@pytest.mark.asyncio
async def test_after_hours_request_can_book_next_day_open_hours_with_price_snapshots(
    db, monkeypatch
):
    from app.services import slots

    class LateNight(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2030, 1, 2, 23, 30, tzinfo=tz)

    monkeypatch.setattr(bookings, "datetime", LateNight)
    monkeypatch.setattr(slots, "datetime", LateNight)
    club = await db.get(Club, 1)
    club.opening_time, club.closing_time = time(8), time(22)
    for ident, start, end in [
        (11, time(10), time(10, 30)),
        (12, time(10, 30), time(11)),
    ]:
        db.add(
            VenueTimeSlot(
                id=ident,
                venue_id=1,
                date=date(2030, 1, 3),
                start_time=start,
                end_time=end,
            )
        )
    await db.flush()
    monkeypatch.setattr(bookings, "check_rate_limit", AsyncMock())
    monkeypatch.setattr(bookings, "acquire_lock", AsyncMock(return_value=True))
    result = await bookings.create_booking(
        BookingCreateRequest(slot_ids=[11, 12]), await db.get(User, "1"), db
    )
    details = (
        (await db.execute(select(BookingSlot).where(BookingSlot.order_id == result.id)))
        .scalars()
        .all()
    )
    assert len(details) == 2 and sum(r.amount for r in details) == result.amount


@pytest.mark.parametrize(
    "rules",
    [
        [
            {
                "type": "daily_time",
                "start_time": "08:00",
                "end_time": "22:00",
                "price": -1,
            }
        ],
        [
            {
                "type": "daily_time",
                "start_time": "22:00",
                "end_time": "08:00",
                "price": 1,
            }
        ],
        [
            {
                "type": "date_range",
                "start_date": "2030-02-30",
                "end_date": "2030-03-01",
                "price": 1,
            }
        ],
        [
            {
                "type": "daily_time",
                "start_time": "08:00",
                "end_time": "22:00",
                "price": "NaN",
            }
        ],
    ],
)
def test_invalid_price_rules_rejected(rules):
    with pytest.raises(ValidationError):
        VenueUpdate(price_rules=rules)


def test_zero_rule_price_remains_supported_and_legacy_booking_contract_rejected():
    assert VenueUpdate(
        price_rules=[
            dict(type="daily_time", start_time="08:00", end_time="22:00", price=0)
        ]
    )
    with pytest.raises(ValidationError):
        BookingCreateRequest(slot_id=1)
    with pytest.raises(ValidationError):
        BookingCreateRequest(slot_ids=[1])
    with pytest.raises(ValidationError):
        SlotGenerateRequest(
            date_from="2030-01-01", date_to="2030-01-01", interval_minutes=60
        )


@pytest.mark.asyncio
async def test_closed_post_retains_messages_and_cannot_reopen_or_reduce_approved_capacity(
    db,
):
    db.add(Activity(id=1, kind="post"))
    await db.flush()
    db.add(MatchPost(id=1, user_id="1", title="历史", players_needed=2, price=0))
    await db.flush()
    db.add_all(
        [
            MatchRegistration(
                post_id=1, user_id="2", status="approved", message="公开留言"
            ),
            MatchRegistration(
                post_id=1, user_id="1", status="approved", message="报名"
            ),
            Comment(post_id=1, user_id="2", content="历史评论"),
        ]
    )
    await db.flush()
    user = await db.get(User, "1")
    with pytest.raises(HTTPException):
        await posts.update_post(1, PostUpdate(players_needed=1), user, db)
    await posts.close_post(1, user, db)
    assert (await db.get(MatchPost, 1)).status == "closed"
    with pytest.raises(HTTPException) as exc:
        await posts.update_post(1, PostUpdate(status="open"), user, db)
    assert exc.value.status_code == 409
    detail = await posts.get_post(1, db, None)
    assert detail.registrations[0].message == "公开留言"
    assert (await posts.list_comments(1, 1, 20, db)).total == 1


@pytest.mark.asyncio
async def test_phone_visibility_public_ids_and_club_document_scope(db):
    user = await db.get(User, "1")
    user.phone = "13800138000"
    club = await db.get(Club, 1)
    club.documents = [dict(name="认证", url="https://private.example/doc")]
    club.created_by = "1"
    db.add(Activity(id=1, kind="post"))
    await db.flush()
    db.add(
        MatchPost(id=1, user_id="1", club_id=1, title="隐私", players_needed=2, price=0)
    )
    await db.flush()
    db.add(
        MatchRegistration(post_id=1, user_id="2", status="pending", message="人人可见")
    )
    await db.flush()
    anonymous = await posts.get_post(1, db, None)
    assert anonymous.user_phone is None and anonymous.club_documents is None
    assert anonymous.registrations[0].message == "人人可见"
    assert (
        anonymous.model_dump(mode="json")["user_id"]
        == user.public_id
        == public_user_id("1")
    )
    assert (await posts.get_post(1, db, user)).user_phone == user.phone
    participant = await db.get(User, "2")
    participant.role = "user"
    assert (await posts.get_post(1, db, participant)).user_phone is None
    reg = (await db.execute(select(MatchRegistration))).scalar_one()
    reg.status = "approved"
    await db.flush()
    assert (await posts.get_post(1, db, participant)).user_phone == user.phone
    assert (await clubs.get_club(1, db, None)).documents is None
    assert (await clubs.get_club(1, db, user)).documents == club.documents


def test_production_jwt_rejects_missing_default_and_short_secrets():
    from app.core.config import Settings

    for secret in [
        "",
        "generate-a-random-secret-key-here",
        "generate-a-random-secret-key-here-at-least-32-chars",
        "short",
    ]:
        with pytest.raises(ValidationError):
            Settings(_env_file=None, DEBUG=False, JWT_SECRET_KEY=secret)
    Settings(
        _env_file=None,
        DEBUG=False,
        JWT_SECRET_KEY="isolated-review-valid-32-character-secret",
    )


def test_celery_invocations_get_distinct_resources_and_close_each_loop(monkeypatch):
    from app.tasks import runtime

    engines = []
    clients = []
    factories = []

    def engine(*args, **kw):
        item = SimpleNamespace(dispose=AsyncMock())
        engines.append(item)
        return item

    def redis(*args, **kw):
        item = SimpleNamespace(aclose=AsyncMock())
        clients.append(item)
        return item

    monkeypatch.setattr(runtime, "create_async_engine", engine)
    monkeypatch.setattr(runtime.aioredis, "from_url", redis)
    monkeypatch.setattr(runtime, "async_sessionmaker", lambda *args, **kw: object())

    async def task():
        factories.append(runtime.task_session_factory.get())
        assert runtime.task_redis_client.get() is clients[-1]

    runtime.run_async_task(task)
    runtime.run_async_task(task)
    assert (
        factories[0] is not factories[1] and runtime.task_session_factory.get() is None
    )
    for item in engines:
        item.dispose.assert_awaited_once()
    for item in clients:
        item.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_public_http_responses_never_expose_internal_user_ids(db):
    from app.core.public_identity import PublicIdentityMiddleware

    user = await db.get(User, "1")
    user.nickname = "公开昵称"
    db.add(Activity(id=1, kind="post"))
    await db.flush()
    db.add(MatchPost(id=1, user_id="1", title="公开活动", price=0))
    await db.flush()
    app = FastAPI()
    app.include_router(posts.router, prefix="/api/v1")
    app.include_router(users.router, prefix="/api/v1")
    app.add_middleware(PublicIdentityMiddleware)

    async def database():
        yield db

    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_optional_user] = lambda: None
    app.dependency_overrides[get_current_user] = lambda: user
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/posts/1")
        assert response.status_code == 200, response.text
        assert response.json()["user_id"] == user.public_id
        profile = await client.get("/api/v1/users/me")
        assert profile.json()["id"] == user.public_id
    assert '"user_id":"1"' not in response.text


@pytest.mark.asyncio
async def test_private_pdf_upload_is_not_static_and_requires_authorization(
    db, monkeypatch, tmp_path
):
    from app import main
    from app.services import storage
    from starlette.datastructures import UploadFile
    from io import BytesIO
    from app.models.models import PrivateUpload

    monkeypatch.setattr(storage, "is_configured", lambda: False)
    monkeypatch.setattr(storage, "PRIVATE_LOCAL_DIR", str(tmp_path / "private"))
    owner = await db.get(User, "1")
    result = await main.upload_file(
        UploadFile(filename="认证.pdf", file=BytesIO(b"%PDF-1.7\nfixture")),
        "doc",
        owner,
        db,
    )
    filename = result["filename"]
    record = await db.get(PrivateUpload, filename)
    assert record.user_id == owner.id and record.backend == "local"
    assert (tmp_path / "private" / filename).exists()
    other = await db.get(User, "2")
    other.role = "user"
    with pytest.raises(HTTPException) as exc:
        await main.private_document(filename, other, db)
    assert exc.value.status_code == 403
    assert (await main.private_document(filename, owner, db)).headers[
        "cache-control"
    ] == "private, no-store"
    with pytest.raises(HTTPException):
        await main.private_document("../escape", owner, db)
    with pytest.raises(HTTPException):
        await main.upload_file(
            UploadFile(filename="假.pdf", file=BytesIO(b"not a pdf")), "doc", owner, db
        )
    with pytest.raises(HTTPException):
        await main.LegacyStaticFiles(directory=tmp_path).get_response("doc/old.pdf", {})


def test_private_cos_documents_refuse_the_public_bucket(monkeypatch):
    from app.services import storage

    monkeypatch.setattr(storage, "is_configured", lambda: True)
    monkeypatch.setattr(
        storage.settings, "COS_PRIVATE_BUCKET_NAME", storage.settings.OSS_BUCKET_NAME
    )
    client = Mock()
    monkeypatch.setattr(storage, "_get_client", lambda: client)
    with pytest.raises(storage.StorageUnavailable):
        storage.put_private_document("x.pdf", b"%PDF-1.7", ".pdf")
    client.put_object.assert_not_called()
    monkeypatch.setattr(
        storage.settings, "COS_PRIVATE_BUCKET_NAME", "isolated-private-bucket"
    )
    assert storage.put_private_document("x.pdf", b"%PDF-1.7", ".pdf") == "cos"
    assert client.put_object.call_args.kwargs["ACL"] == "private"
    assert client.put_object.call_args.kwargs["Bucket"] == "isolated-private-bucket"


def test_business_booking_window_is_three_days(monkeypatch):
    from app.services import slots

    class Today(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2030, 1, 2, 23, 30, tzinfo=tz)

    monkeypatch.setattr(slots, "datetime", Today)
    for day in (2, 3, 4):
        validate_booking_date(date(2030, 1, day))
    for day in (1, 5):
        with pytest.raises(HTTPException):
            validate_booking_date(date(2030, 1, day))


@pytest.mark.asyncio
async def test_late_payment_close_callback_cannot_release_new_booking(db, monkeypatch):
    from app.services.payment_callback import _handle_payment_closed

    old, user = await pending(db, 2, 20)
    new, _ = await pending(db, 3)
    release = AsyncMock()
    monkeypatch.setattr("app.services.booking_locks.release_lock", release)
    assert (await _handle_payment_closed({"out_trade_no": old.order_no}, db))[
        "code"
    ] == "SUCCESS"
    for sid in (11, 12):
        assert (await db.get(VenueTimeSlot, sid)).booking_order_id == new.id
        assert (await db.get(VenueTimeSlot, sid)).status == "locked"
    release.assert_not_awaited()


@pytest.mark.asyncio
async def test_refund_callback_only_releases_its_order_slots(db, monkeypatch):
    from app.services.payment_callback import _handle_refund_callback
    from app.models.models import RefundRecord

    old, user = await pending(db, 2)
    old.status = "refunding"
    new, _ = await pending(db, 3)
    db.add(
        RefundRecord(
            order_id=old.id,
            out_refund_no="review-refund",
            amount=100,
            status="processing",
        )
    )
    await db.flush()
    release = AsyncMock()
    monkeypatch.setattr("app.services.booking_locks.release_lock", release)
    response = await _handle_refund_callback(
        {
            "out_trade_no": old.order_no,
            "out_refund_no": "review-refund",
            "refund_status": "SUCCESS",
        },
        db,
    )
    assert response["code"] == "SUCCESS"
    for sid in (11, 12):
        assert (await db.get(VenueTimeSlot, sid)).booking_order_id == new.id
        assert (await db.get(VenueTimeSlot, sid)).status == "locked"
    release.assert_not_awaited()


@pytest.mark.asyncio
async def test_booking_payment_callback_is_idempotent_and_uses_order_owner(
    db, monkeypatch
):
    from app.services.payment_callback import _handle_payment_success
    from app.models.models import SettlementRecord

    order, user = await pending(db, 2)
    release = AsyncMock()
    monkeypatch.setattr("app.services.payment_callback.release_lock", release)
    data = {
        "out_trade_no": order.order_no,
        "transaction_id": "isolated-transaction",
        "amount": {"total": 10000},
    }
    await _handle_payment_success(data, db)
    await _handle_payment_success(data, db)
    assert len((await db.execute(select(SettlementRecord))).scalars().all()) == 1
    assert release.await_count == 2
    assert all(call.args[1] == "booking:review-2" for call in release.await_args_list)
    for sid in (11, 12):
        assert (await db.get(VenueTimeSlot, sid)).status == "booked"


@pytest.mark.asyncio
async def test_late_real_payment_callback_records_anomaly_without_taking_new_slots(
    db, monkeypatch
):
    from app.services.payment_callback import _handle_payment_success
    from app.models.models import Notification

    old, user = await pending(db, 2, 20)
    new, _ = await pending(db, 3)
    release = AsyncMock()
    monkeypatch.setattr("app.services.booking_locks.release_lock", release)
    await _handle_payment_success(
        {
            "out_trade_no": old.order_no,
            "transaction_id": "isolated-late",
            "amount": {"total": 10000},
        },
        db,
    )
    for sid in (11, 12):
        slot = await db.get(VenueTimeSlot, sid)
        assert slot.booking_order_id == new.id and slot.status == "locked"
    release.assert_not_awaited()
    assert len((await db.execute(select(Notification))).scalars().all()) == 1


@pytest.mark.asyncio
async def test_failed_first_recovery_batch_does_not_starve_later_orders(
    db, monkeypatch
):
    from app.models.models import Tournament
    from app.services import tournament_maintenance as maintenance

    db.add(Activity(id=10, kind="tournament"))
    await db.flush()
    db.add(
        Tournament(
            id=10,
            club_id=1,
            title="隔离恢复",
            status="draft",
            start_time=datetime.utcnow() + timedelta(days=1),
            end_time=datetime.utcnow() + timedelta(days=2),
        )
    )
    await db.flush()
    for ident in range(2, 203):
        db.add(
            BookingOrder(
                id=ident,
                order_no=f"recovery-{ident}",
                user_id="1",
                club_id=1,
                tournament_id=10,
                business_type="tournament",
                amount=1,
                status="pending",
                updated_at=datetime(2020, 1, 1),
            )
        )
    await db.commit()
    query = AsyncMock(side_effect=RuntimeError("isolated remote failure"))
    monkeypatch.setattr(maintenance.life, "wx_call", query)
    result = await maintenance.maintain_db(db, bookings.get_settings())
    first = {call.kwargs["out_trade_no"] for call in query.await_args_list}
    assert result["errors"] == 100 and len(first) == 100
    query.reset_mock()
    result = await maintenance.maintain_db(db, bookings.get_settings())
    second = {call.kwargs["out_trade_no"] for call in query.await_args_list}
    assert result["errors"] == 100 and len(second) == 100 and not first & second
