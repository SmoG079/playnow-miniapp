"""Real SQL persistence tests on disposable SQLite; MySQL row locks need separate integration."""

from datetime import datetime, timedelta
from decimal import Decimal
import pytest
import pytest_asyncio
from contextlib import asynccontextmanager
from app.services import activity_ids
from sqlalchemy import BigInteger, select
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from fastapi import HTTPException
from app.models.models import (
    Base,
    Club,
    User,
    UserRole,
    BookingOrder,
    OrderStatus,
    TournamentRegistration,
    Tournament,
    RefundRecord,
)
from app.schemas.tournament import *
from app.api.v1 import tournaments as api
from app.services import tournament_lifecycle as life


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
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        s.add(Club(id=1, name="测试俱乐部"))
        s.add(Club(id=2, name="其他俱乐部"))
        for i in range(1, 18):
            s.add(
                User(
                    id=str(i),
                    openid=f"wx{i}",
                    nickname=f"选手{i}",
                    role=UserRole.platform_admin if i == 1 else UserRole.user,
                )
            )
        await s.commit()
        yield s
    await engine.dispose()


async def event(db, people=8, cfg=None, fee=0):
    user = await db.get(User, 1)
    req = TournamentCreate(
        address="测试网球场",
        club_id=1,
        title="测试比赛",
        start_time=datetime.utcnow() + timedelta(days=2),
        end_time=datetime.utcnow() + timedelta(days=3),
        max_participants=people,
        entry_fee=fee,
        config=cfg or TournamentConfig(),
    )
    row = await api.create_tournament(req, user, db)
    await db.commit()
    return row["id"], user


async def register(db, tid, uid, **kwargs):
    return await api.register_tournament(
        tid, RegistrationCommand(**kwargs), await db.get(User, uid), db
    )


@pytest.mark.asyncio
async def test_six_player_bracket_privacy_idempotence_progression(db):
    tid, admin = await event(db, 6)
    for uid in range(2, 8):
        await register(db, tid, uid)
    await api.close_registration(tid, admin, db)
    req = DrawCommand(idempotency_key="stable-key", expected_version=0)
    first = await api.create_draw(tid, req, admin, db)
    assert (await api.create_draw(tid, req, admin, db)) == {"version": first["version"]}
    public = await api.get_tournament(tid, None, db)
    assert public["matches"] == [] and public["teams"] == []
    assert all(
        "payment" not in r and "gender" not in r for r in public["registrations"]
    )
    await api.publish_draw(tid, VersionCommand(expected_version=1), admin, db)
    detail = await api.get_tournament(tid, None, db)
    assert len(detail["teams"]) == 6
    assert sum(m["status"] == "bye" for m in detail["matches"]) == 2
    for m in detail["matches"]:
        current = (await api.get_tournament(tid, admin, db))["matches"]
        m = next(x for x in current if x["id"] == m["id"])
        if m["status"] == "pending":
            await api.record_result(
                tid,
                m["id"],
                ResultCommand(
                    expected_version=1, winner_id=m["team_a_id"], score="6:4"
                ),
                admin,
                db,
            )
    await api.finish(tid, VersionCommand(expected_version=1), admin, db)
    detail = await api.get_tournament(tid, None, db)
    assert detail["status"] == "finished"
    assert sorted(r["rank"] for r in detail["rankings"]) == [1, 2, 3, 3, 5, 5]


@pytest.mark.asyncio
async def test_waitlist_review_and_cancellation(db):
    cfg = TournamentConfig(approval_required=True, waitlist_enabled=True)
    tid, admin = await event(db, 2, cfg)
    for uid in (2, 3, 4):
        await register(db, tid, uid)
    rows = await life.registrations(db, await life.locked_event(db, tid))
    for r in rows:
        await api.review(
            tid, r.id, ReviewCommand(reason="审核通过", approved=True), admin, db
        )
    assert [r.admission for r in rows] == ["active", "active", "waitlisted"]
    await api.cancel_registration(
        tid, rows[0].id, ReasonCommand(reason="有事退出"), await db.get(User, 2), db
    )
    assert rows[2].admission == "active"
    t = await life.locked_event(db, tid)
    assert t.current_participants == 2


@pytest.mark.asyncio
async def test_pair_invitation_and_partner_cancel(db):
    tid, admin = await event(db, 4, TournamentConfig(discipline="mixed"))
    await register(db, tid, 2, gender="male", pairing="fixed")
    await register(db, tid, 3, gender="female")
    u2 = await db.get(User, 2)
    u3 = await db.get(User, 3)
    invite = await api.pairing(tid, RegistrationCommand(pairing="fixed"), u2, db)
    await api.accept_invitation(tid, invite["invite_token"], u3, db)
    t = await life.locked_event(db, tid)
    r = await api.own(db, t, u2)
    partner = await api.own(db, t, u3)
    assert partner.partner_user_id == "2"
    await api.cancel_registration(tid, r.id, ReasonCommand(reason="退出"), u2, db)
    assert (
        partner.partner_user_id is None
        and partner.pairing == "fixed"
        and partner.status.value == "confirmed"
    )


@pytest.mark.asyncio
async def test_payment_gate_duplicates_late_callback_and_refund(db, monkeypatch):
    settings = life.get_settings()
    monkeypatch.setattr(settings, "TOURNAMENT_PREPAY_ENABLED", True)
    monkeypatch.setattr(settings, "WX_MCH_ID", "mch")
    monkeypatch.setattr(settings, "WX_APP_ID", "app")
    tid, admin = await event(db, 2, fee=Decimal("20"))
    await register(db, tid, 2)
    t = await life.locked_event(db, tid)
    r = await api.own(db, t, await db.get(User, 2))
    o = await db.get(BookingOrder, r.order_id)
    payload = dict(
        out_trade_no=o.order_no,
        mchid="mch",
        appid="app",
        amount={"total": 2000},
        transaction_id="real-wx-tx",
    )
    await life.payment_success(db, payload)
    await life.payment_success(db, payload)
    assert t.current_participants == 1 and r.payment == "paid"
    await api.cancel_registration(
        tid, r.id, ReasonCommand(reason="退赛"), await db.get(User, 2), db
    )
    refund = (
        await db.execute(select(RefundRecord).where(RefundRecord.order_id == o.id))
    ).scalar_one()
    assert o.status == OrderStatus.refunding
    await life.refund_callback(
        db,
        dict(
            out_trade_no=o.order_no,
            out_refund_no=refund.out_refund_no,
            mchid="mch",
            amount={"refund": 2000},
            refund_status="ABNORMAL",
        ),
    )
    assert r.admission == "cancelled" and t.current_participants == 0
    await life.refund_callback(
        db,
        dict(
            out_trade_no=o.order_no,
            out_refund_no=refund.out_refund_no,
            mchid="mch",
            amount={"refund": 2000},
            refund_status="SUCCESS",
        ),
    )
    assert o.status == OrderStatus.refunded
    await register(db, tid, 3)
    r2 = await api.own(db, t, await db.get(User, 3))
    o2 = await db.get(BookingOrder, r2.order_id)
    r2.seat_expires_at = datetime.utcnow() - timedelta(seconds=1)
    await life.payment_success(
        db, dict(payload, out_trade_no=o2.order_no, transaction_id="late-tx")
    )
    assert (
        r2.admission == "expired"
        and o2.status == OrderStatus.refunding
        and t.current_participants == 0
    )


@pytest.mark.asyncio
async def test_non_admin_cannot_draw_and_version_conflict(db):
    tid, admin = await event(db, 2)
    with pytest.raises(HTTPException) as err:
        await api.close_registration(tid, await db.get(User, 2), db)
    assert err.value.status_code == 403
    for uid in (2, 3):
        await register(db, tid, uid)
    await api.close_registration(tid, admin, db)
    await api.create_draw(tid, DrawCommand(idempotency_key="initial-key"), admin, db)
    with pytest.raises(HTTPException) as err:
        await api.create_draw(
            tid,
            DrawCommand(
                idempotency_key="another-key", expected_version=0, reason="调整"
            ),
            admin,
            db,
        )
    assert err.value.status_code == 409


@pytest.mark.asyncio
async def test_combination_stage_redraw_and_history(db):
    tid, admin = await event(
        db,
        8,
        TournamentConfig(format="groups_knockout", group_count=2, third_place=True),
    )
    for uid in range(2, 10):
        await register(db, tid, uid)
    await api.close_registration(tid, admin, db)
    await api.create_draw(tid, DrawCommand(idempotency_key="combo-initial"), admin, db)
    await api.publish_draw(tid, VersionCommand(expected_version=1), admin, db)
    for m in (await api.get_tournament(tid, admin, db))["matches"]:
        await api.record_result(
            tid,
            m["id"],
            ResultCommand(
                expected_version=1,
                winner_id=min(m["team_a_id"], m["team_b_id"]),
                score="6:4",
            ),
            admin,
            db,
        )
    await api.create_draw(
        tid,
        DrawCommand(
            idempotency_key="combo-knockout", expected_version=1, stage="knockout"
        ),
        admin,
        db,
    )
    detail = await api.get_tournament(tid, admin, db)
    teams = {t["id"]: t for t in detail["teams"]}
    assert len(teams) == 4
    for m in detail["matches"]:
        if m["round_no"] == 1:
            assert (
                teams[m["team_a_id"]]["origin_group"]
                != teams[m["team_b_id"]]["origin_group"]
            )
    with pytest.raises(HTTPException):
        await api.create_draw(
            tid,
            DrawCommand(idempotency_key="rollback-initial", expected_version=2),
            admin,
            db,
        )
    await api.create_draw(
        tid,
        DrawCommand(
            idempotency_key="redraw-knockout",
            expected_version=2,
            stage="knockout",
            reason="重新抽签",
        ),
        admin,
        db,
    )
    assert len((await api.get_draw(tid, 1, admin, db))["matches"]) == 12


@pytest.mark.asyncio
async def test_schedule_conflict_and_downstream_reset(db):
    tid, admin = await event(db, 4)
    for uid in range(2, 6):
        await register(db, tid, uid)
    await api.close_registration(tid, admin, db)
    await api.create_draw(tid, DrawCommand(idempotency_key="schedule-test"), admin, db)
    await api.publish_draw(tid, VersionCommand(expected_version=1), admin, db)
    ms = (await api.get_tournament(tid, admin, db))["matches"]
    with pytest.raises(HTTPException):
        await api.schedule_match(
            tid,
            ms[1]["id"],
            ScheduleCommand(
                expected_version=1,
                court=ms[0]["court"],
                start_time=ms[0]["scheduled_at"],
            ),
            admin,
            db,
        )
    for m in ms:
        fresh = next(
            x
            for x in (await api.get_tournament(tid, admin, db))["matches"]
            if x["id"] == m["id"]
        )
        await api.record_result(
            tid,
            m["id"],
            ResultCommand(
                expected_version=1, winner_id=fresh["team_a_id"], score="6:0"
            ),
            admin,
            db,
        )
    with pytest.raises(HTTPException):
        await api.reset_result(
            tid,
            ms[0]["id"],
            ResultCommand(expected_version=1, reason="纠错"),
            admin,
            db,
        )
    await api.reset_result(
        tid,
        ms[-1]["id"],
        ResultCommand(expected_version=1, reason="先撤销决赛"),
        admin,
        db,
    )
    await api.reset_result(
        tid, ms[0]["id"], ResultCommand(expected_version=1, reason="纠错"), admin, db
    )
    final = next(
        x
        for x in (await api.get_tournament(tid, admin, db))["matches"]
        if x["id"] == ms[-1]["id"]
    )
    assert final["team_a_id"] is None


@pytest.mark.asyncio
async def test_paid_capacity_identity_and_placeholder_rejection(db, monkeypatch):
    monkeypatch.setattr(life.get_settings(), "TOURNAMENT_PREPAY_ENABLED", True)
    tid, admin = await event(db, 2, fee=20)
    for uid in (2, 3):
        await register(db, tid, uid)
    with pytest.raises(HTTPException):
        await register(db, tid, 4)
    r = await api.own(db, await life.locked_event(db, tid), await db.get(User, 2))
    o = await db.get(BookingOrder, r.order_id)
    with pytest.raises(HTTPException):
        await life.payment_success(
            db,
            dict(
                out_trade_no=o.order_no,
                mchid="wrong",
                appid="wrong",
                amount={"total": 1},
                transaction_id="wrong",
            ),
        )
    assert o.status == OrderStatus.pending
    from app.api.v1.bookings import pay_booking

    with pytest.raises(HTTPException):
        await pay_booking(o.id, await db.get(User, 2), db)


@pytest.mark.asyncio
async def test_default_payment_gate_and_mixed_gender_capacity(db, monkeypatch):
    monkeypatch.setattr(life.get_settings(), "TOURNAMENT_PREPAY_ENABLED", False)
    paid, admin = await event(db, 2, fee=20)
    with pytest.raises(HTTPException) as err:
        await register(db, paid, 2)
    assert err.value.status_code == 503
    tid, admin = await event(
        db, 4, TournamentConfig(discipline="mixed", waitlist_enabled=True)
    )
    for uid in (2, 3, 4):
        await register(db, tid, uid, gender="male")
    await register(db, tid, 5, gender="female")
    rows = await life.registrations(db, await life.locked_event(db, tid))
    assert rows[2].admission == "waitlisted"
    await api.close_registration(tid, admin, db)
    with pytest.raises(HTTPException):
        await api.create_draw(
            tid, DrawCommand(idempotency_key="unbalanced-mixed"), admin, db
        )


@pytest.mark.asyncio
async def test_refund_worker_verifies_response_and_dev_payment(db, monkeypatch):
    from app.services.tournament_maintenance import maintain_db

    settings = life.get_settings()
    monkeypatch.setattr(settings, "TOURNAMENT_PREPAY_ENABLED", True)
    monkeypatch.setattr(settings, "WX_MCH_ID", "mch")
    monkeypatch.setattr(settings, "WX_APP_ID", "app")
    tid, admin = await event(db, 2, fee=20)
    await register(db, tid, 2)
    r = await api.own(db, await life.locked_event(db, tid), await db.get(User, 2))
    o = await db.get(BookingOrder, r.order_id)
    o.wx_transaction_id = "dev_legacy"
    with pytest.raises(HTTPException):
        await life.request_refund(db, o, "核验")
    await life.payment_success(
        db,
        dict(
            out_trade_no=o.order_no,
            mchid="mch",
            appid="app",
            amount={"total": 2000},
            transaction_id="real-tx",
        ),
    )
    await api.cancel_registration(
        tid, r.id, ReasonCommand(reason="退赛"), await db.get(User, 2), db
    )
    order_id, order_no = o.id, o.order_no
    await db.commit()

    async def wx(method, **kwargs):
        if method == "query":
            return dict(
                trade_state="SUCCESS",
                transaction_id="real-tx",
                mchid="mch",
                appid="app",
                amount={"total": 2000},
            )
        assert method == "refund"
        return dict(
            status="SUCCESS",
            out_refund_no=kwargs["out_refund_no"],
            out_trade_no=order_no,
            amount={"refund": 2000},
            mchid="mch",
        )

    monkeypatch.setattr(life, "wx_call", wx)
    assert (await maintain_db(db, settings))["errors"] == 0
    assert (await db.get(BookingOrder, order_id)).status == OrderStatus.refunded


@pytest.mark.asyncio
async def test_tournament_callback_commits_before_ack_and_is_idempotent(
    db, monkeypatch
):
    import json
    import time
    from starlette.requests import Request
    from app.api.v1 import bookings

    settings = life.get_settings()
    for field, value in [
        ("TOURNAMENT_PREPAY_ENABLED", True),
        ("WX_MCH_ID", "mch"),
        ("WX_APP_ID", "app"),
    ]:
        monkeypatch.setattr(settings, field, value)
    tid, admin = await event(db, 2, fee=20)
    await register(db, tid, 2)
    r = await api.own(db, await life.locked_event(db, tid), await db.get(User, 2))
    order_id = r.order_id
    o = await db.get(BookingOrder, order_id)
    payload = dict(
        out_trade_no=o.order_no,
        mchid="mch",
        appid="app",
        amount={"total": 2000},
        transaction_id="verified-tx",
    )

    class WX:
        def decrypt_callback(self, headers, body):
            return json.dumps(payload)

    monkeypatch.setattr(bookings, "get_wxpay", lambda: WX())

    def request():
        async def receive():
            return {
                "type": "http.request",
                "body": b'{"event_type":"TRANSACTION.SUCCESS"}',
                "more_body": False,
            }

        return Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/wx-notify",
                "headers": [
                    (b"wechatpay-timestamp", str(int(time.time())).encode()),
                    (b"wechatpay-nonce", b"same-nonce"),
                ],
            },
            receive,
        )

    assert (await bookings.wx_pay_notify(request(), db))["code"] == "SUCCESS"
    assert (await bookings.wx_pay_notify(request(), db))["code"] == "SUCCESS"
    assert (await db.get(BookingOrder, order_id)).status == OrderStatus.paid
    assert (await life.locked_event(db, tid)).current_participants == 1
    payload["transaction_id"] = "different-tx"
    with pytest.raises(HTTPException):
        await bookings.wx_pay_notify(request(), db)


@pytest.mark.asyncio
async def test_legacy_visibility_requires_explicit_payment_verification(db):
    tid, admin = await event(db, 2)
    await register(db, tid, 2)
    t = await life.locked_event(db, tid)
    r = await api.own(db, t, await db.get(User, 2))
    t.config = None
    t.entry_fee = Decimal("20")
    r.payment = "unverified"
    await db.flush()
    public = await api.get_tournament(tid, None, db)
    assert len(public["registrations"]) == 1 and public["teams"] == []
    assert "payment" not in public["registrations"][0]
    t.config = TournamentConfig().model_dump()
    assert not life.eligible(r)
    await api.verify_legacy(
        tid, r.id, ReasonCommand(reason="管理员核对历史报名"), admin, db
    )
    assert life.eligible(r) and r.order_id is None


@pytest.mark.asyncio
async def test_tournament_orders_do_not_pollute_booking_pagination(db, monkeypatch):
    from app.api.v1.users import my_bookings
    from app.api.v1.bookings import club_orders

    monkeypatch.setattr(life.get_settings(), "TOURNAMENT_PREPAY_ENABLED", True)
    tid, admin = await event(db, 2, fee=20)
    await register(db, tid, 2)
    result = await my_bookings(None, 1, 20, await db.get(User, 2), db)
    assert result.total == 0 and result.items == []
    result = await club_orders(1, None, 1, 20, admin, db)
    assert result.total == 0 and result.items == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,membership,target,allowed",
    [
        ("user", None, 1, True),
        ("user", 1, 1, True),
        ("club_admin", None, 1, True),
        ("club_admin", 1, 1, True),
        ("club_admin", 1, 2, True),
        ("platform_admin", None, 2, True),
    ],
)
async def test_all_roles_can_publish_and_preview_existing_club(
    db, role, membership, target, allowed
):
    from app.models.models import ClubMember, ClubMemberRole

    user = await db.get(User, 2)
    user.role = UserRole(role)
    if membership:
        db.add(
            ClubMember(club_id=membership, user_id=user.id, role=ClubMemberRole.owner)
        )
    await db.flush()
    req = TournamentCreate(
        address="测试网球场",
        club_id=target,
        title="权限测试",
        start_time=datetime.utcnow() + timedelta(days=1),
        end_time=datetime.utcnow() + timedelta(days=2),
        max_participants=2,
        config=TournamentConfig(),
    )
    if allowed:
        assert (await api.preview(req, user, db))["total_matches"] == 1
        assert (await api.create_tournament(req, user, db))["club_id"] == target
    else:
        for action in (api.preview, api.create_tournament):
            with pytest.raises(HTTPException) as err:
                await action(req, user, db)
            assert err.value.status_code == 403


@pytest.mark.asyncio
async def test_selected_groups_survive_live_redraw_and_personal_records(db):
    from app.api.v1.users import my_tournaments

    tid, admin = await event(db, 8, TournamentConfig(group_count=2))
    for uid in range(2, 10):
        await register(db, tid, uid, requested_group=1 if uid < 6 else 2)
    await api.close_registration(tid, admin, db)
    await api.create_draw(
        tid, DrawCommand(idempotency_key="chosen-group-first", publish=True), admin, db
    )
    original = await api.get_tournament(tid, admin, db)
    for team in original["teams"]:
        assert team["group_no"] == (1 if int(team["user_ids"][0]) < 6 else 2)
    m = original["matches"][0]
    await api.record_result(
        tid,
        m["id"],
        ResultCommand(expected_version=1, winner_id=m["team_a_id"], score="6:4"),
        admin,
        db,
    )
    with pytest.raises(HTTPException):
        await api.create_draw(
            tid,
            DrawCommand(
                idempotency_key="unsafe-new-draw",
                expected_version=1,
                reason="开始后重抽",
            ),
            admin,
            db,
        )
    await api.create_draw(
        tid,
        DrawCommand(
            idempotency_key="archive-new-draw",
            expected_version=1,
            reason="开始后调整签表",
            archive_results=True,
            publish=True,
        ),
        admin,
        db,
    )
    current = await api.get_tournament(tid, await db.get(User, 2), db)
    assert current["draw_version"] == current["published_version"] == 2
    assert all(not m["score"] for m in current["matches"])
    assert (
        next(
            x
            for x in (await api.get_draw(tid, 1, admin, db))["matches"]
            if x["id"] == m["id"]
        )["score"]
        == "6:4"
    )
    records = await my_tournaments(1, 20, await db.get(User, 2), db)
    assert records.total == 1 and records.items[0]["draw_version"] == 2
    personal = records.items[0]["my_draw"]
    assert personal["group_no"] == 1
    assert {m["id"] for m in personal["matches"]}.issubset(
        {m["id"] for m in current["matches"]}
    )


@pytest.mark.asyncio
async def test_group_capacity_waitlist_and_invitation_mismatch(db):
    tid, admin = await event(
        db, 4, TournamentConfig(group_count=2, waitlist_enabled=True)
    )
    for uid in (2, 3, 4):
        await register(db, tid, uid, requested_group=1)
    rows = await life.registrations(db, await life.locked_event(db, tid))
    assert rows[2].admission == "waitlisted"
    await api.cancel_registration(
        tid, rows[0].id, ReasonCommand(reason="退出"), await db.get(User, 2), db
    )
    assert rows[2].admission == "active"
    with pytest.raises(HTTPException):
        await api.select_group(
            tid, RegistrationCommand(requested_group=3), await db.get(User, 3), db
        )
    doubles, admin = await event(
        db, 8, TournamentConfig(group_count=2, discipline="doubles")
    )
    for uid, g in ((2, 1), (3, 2)):
        await register(db, doubles, uid, requested_group=g, pairing="fixed")
    invite = await api.pairing(
        doubles, RegistrationCommand(pairing="fixed"), await db.get(User, 2), db
    )
    with pytest.raises(HTTPException):
        await api.accept_invitation(
            doubles, invite["invite_token"], await db.get(User, 3), db
        )


@pytest.mark.asyncio
async def test_auto_players_fill_selected_mixed_groups(db):
    tid, admin = await event(db, 8, TournamentConfig(group_count=2, discipline="mixed"))
    for uid, g, gender in (
        (2, 1, "male"),
        (3, 1, "female"),
        (4, 2, "male"),
        (5, 2, "female"),
        (6, 0, "male"),
        (7, 0, "female"),
        (8, 0, "male"),
        (9, 0, "female"),
    ):
        await register(db, tid, uid, requested_group=g, gender=gender)
    await api.close_registration(tid, admin, db)
    await api.create_draw(
        tid, DrawCommand(idempotency_key="mixed-group-fill", publish=True), admin, db
    )
    detail = await api.get_tournament(tid, admin, db)
    for team in detail["teams"]:
        if "2" in team["user_ids"] or "3" in team["user_ids"]:
            assert team["group_no"] == 1
        if "4" in team["user_ids"] or "5" in team["user_ids"]:
            assert team["group_no"] == 2
    assert len(detail["teams"]) == 4


@pytest.mark.asyncio
async def test_provisional_real_opponents_are_not_formal_draws(db):
    from app.api.v1.users import my_tournaments
    from app.models.models import TournamentDraw

    tid, admin = await event(db, 4)
    for uid in (2, 3, 4, 5):
        await register(db, tid, uid)
    detail = await api.get_tournament(tid, await db.get(User, 2), db)
    provisional = detail["participant_preview"]
    assert provisional and detail["published_version"] == 0 and detail["matches"] == []
    assert set(uid for team in provisional["teams"] for uid in team["user_ids"]) == {"2", "3", "4", "5"}
    assert (
        not (
            await db.execute(
                select(TournamentDraw).where(TournamentDraw.tournament_id == tid)
            )
        )
        .scalars()
        .all()
    )
    records = await my_tournaments(1, 20, await db.get(User, 2), db)
    assert records.items[0]["provisional"] and records.items[0]["my_draw"]["matches"]
    await api.close_registration(tid, admin, db)
    await api.create_draw(
        tid, DrawCommand(idempotency_key="formal-from-preview", publish=True), admin, db
    )
    records = await my_tournaments(1, 20, await db.get(User, 2), db)
    assert not records.items[0]["provisional"] and records.items[0]["draw_version"] == 1

@pytest.mark.asyncio
async def test_personal_tournament_without_club_supports_listing_management_and_payment_order(db, monkeypatch):
    monkeypatch.setattr(life.get_settings(), "TOURNAMENT_PREPAY_ENABLED", True)
    creator = await db.get(User, '2')
    req = TournamentCreate(title='个人地图比赛', address='地图选点球场', city='南京市', latitude=32.06, longitude=118.76,
        start_time=datetime.utcnow()+timedelta(days=2), end_time=datetime.utcnow()+timedelta(days=3),
        max_participants=4, entry_fee=10, config=TournamentConfig())
    await api.preview(req, creator, db)
    row = await api.create_tournament(req, creator, db)
    assert row['club_id'] is None
    detail = await api.get_tournament(row['id'], creator, db)
    assert detail['club_name'] is None and detail['can_manage']
    await api.admin(db, await db.get(Tournament, row['id']), creator)
    with pytest.raises(HTTPException) as denied:
        await api.admin(db, await db.get(Tournament, row['id']), await db.get(User, '3'))
    assert denied.value.status_code == 403
    result = await api.list_tournaments(city='南京市', sort_by='created', lat=None, lng=None, page=1, page_size=20, db=db)
    assert row['id'] in [r['id'] for r in result['items']]
    await register(db, row['id'], '3')
    registration = await db.scalar(select(TournamentRegistration).where(TournamentRegistration.tournament_id==row['id']))
    order = await db.get(BookingOrder, registration.order_id)
    assert order.club_id is None and order.business_type == 'tournament' and order.amount == 10

@pytest.mark.asyncio
async def test_linked_tournament_location_is_authoritative_and_cannot_be_removed(db):
    from app.models.models import Venue
    creator = await db.get(User, '2')
    db.add(Venue(id=100, club_id=1, name='预订球场', sport_type='tennis', price_per_hour=10,
        address='球场真实位置', city='南京市', latitude=32, longitude=118));await db.flush()
    req = TournamentCreate(title='关联球场比赛', venue_id=100, start_time=datetime.utcnow()+timedelta(days=2),
        end_time=datetime.utcnow()+timedelta(days=3), max_participants=4, config=TournamentConfig())
    row = await api.create_tournament(req, creator, db)
    req.address='不能覆盖的假地址';req.latitude=1;req.longitude=1
    await api.update_tournament(row['id'], req, creator, db)
    detail = await api.get_tournament(row['id'], creator, db)
    assert detail['address']=='球场真实位置' and detail['latitude']==32 and detail['longitude']==118
    req.venue_id=None
    with pytest.raises(HTTPException) as denied:
        await api.update_tournament(row['id'], req, creator, db)
    assert denied.value.status_code==409
