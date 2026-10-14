"""Regression tests for real booking funds and cancelled tournament reviews."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from decimal import Decimal
from unittest.mock import AsyncMock, Mock
import json
import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from app.api.v1 import bookings, tournaments
from app.models.models import BookingOrder, RefundRecord, VenueTimeSlot, User, Notification, PaymentLog
from app.schemas.schemas import RefundRequest, CancelRequest
from app.schemas.tournament import TournamentConfig, ReviewCommand, ReasonCommand
from app.services import payment_callback, tournament_lifecycle as life
from app.services.booking_locks import expire_slot_orders
from app.services.booking_payment_recovery import maintain
from app.tasks import tasks
from tests.test_review_fixes import db, pending
from tests.test_tournaments import db as tournament_db, event, register
from tests.test_refund_sync_task import _run, _stale


def success(order):
    return {'out_trade_no':order.order_no, 'transaction_id':'real-payment',
            'trade_state':'SUCCESS', 'amount':{'total':10000}}


@pytest.mark.asyncio
async def test_real_paid_cancel_queues_full_refund_and_preserves_slots_until_success(db, monkeypatch):
    order, user = await pending(db, 2)
    order.status, order.wx_transaction_id = 'paid', 'real-payment'
    slot = await db.get(VenueTimeSlot, 11)
    slot.status = 'booked'
    release = AsyncMock()
    monkeypatch.setattr('app.services.booking_locks.release_lock', release)
    monkeypatch.setattr(tasks.retry_failed_refunds, 'delay', Mock())
    result = await bookings.cancel_booking(2, CancelRequest(reason='cancel'), user, db)
    assert result['status'] == 'refunding' and Decimal(result['refund_amount']) == 100
    assert order.status == 'refunding' and slot.status == 'booked'
    release.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('seconds_before', [3601, 3600, 3599, 0, -1])
@pytest.mark.parametrize('kind', ['paid', 'pending', 'placeholder'])
async def test_self_cancel_one_hour_boundary_uses_first_slot(db, monkeypatch, seconds_before, kind):
    order, user = await pending(db, 2)
    if kind != 'pending':
        order.status = 'paid'
        order.wx_transaction_id = 'real-payment' if kind == 'paid' else 'dev_test'
    first = await db.get(VenueTimeSlot, 11)
    utc_start = datetime.combine(first.date, first.start_time).replace(tzinfo=ZoneInfo('Asia/Shanghai'))\
        .astimezone(timezone.utc).replace(tzinfo=None)
    monkeypatch.setattr(bookings, '_utc_now', lambda: utc_start - timedelta(seconds=seconds_before))
    monkeypatch.setattr(tasks.retry_failed_refunds, 'delay', Mock())
    monkeypatch.setattr('app.services.booking_locks.release_lock', AsyncMock())
    if seconds_before <= 3600:
        with pytest.raises(HTTPException) as exc:
            await bookings.cancel_booking(2, CancelRequest(reason='boundary'), user, db)
        assert exc.value.status_code == 409
        assert (await db.get(VenueTimeSlot, 12)).status == 'locked'
        assert not (await db.scalars(select(RefundRecord))).all()
    else:
        result = await bookings.cancel_booking(2, CancelRequest(reason='boundary'), user, db)
        if kind == 'paid':
            assert result['status'] == 'refunding' and Decimal(result['refund_amount']) == order.amount
        else:
            assert order.status == 'cancelled'


@pytest.mark.asyncio
async def test_self_cancel_retries_after_cutoff_do_not_duplicate_refund(db, monkeypatch):
    order, user = await pending(db, 2)
    order.status, order.wx_transaction_id = 'paid', 'real-payment'
    monkeypatch.setattr(tasks.retry_failed_refunds, 'delay', Mock())
    first = await bookings.cancel_booking(2, CancelRequest(), user, db)
    monkeypatch.setattr(bookings, '_utc_now', lambda: datetime.utcnow() + timedelta(days=10))
    second = await bookings.cancel_booking(2, CancelRequest(), user, db)
    assert second == first
    assert len((await db.scalars(select(RefundRecord).where(RefundRecord.order_id == 2))).all()) == 1


@pytest.mark.asyncio
async def test_self_cancel_cannot_cancel_someone_elses_paid_booking(db, monkeypatch):
    order, user = await pending(db, 2)
    order.status, order.wx_transaction_id = 'paid', 'real-payment'
    with pytest.raises(HTTPException) as exc:
        await bookings.cancel_booking(2, CancelRequest(), await db.get(User, '2'), db)
    assert exc.value.status_code == 403 and order.status == 'paid'


@pytest.mark.asyncio
async def test_placeholder_cancel_still_releases_own_slots(db, monkeypatch):
    order, user = await pending(db, 2)
    order.status, order.wx_transaction_id = 'paid', 'dev_test'
    monkeypatch.setattr('app.services.booking_locks.release_lock', AsyncMock())
    await bookings.cancel_booking(2, CancelRequest(reason='cancel'), user, db)
    assert order.status == 'cancelled'
    assert (await db.get(VenueTimeSlot, 11)).booking_order_id is None


@pytest.mark.asyncio
async def test_timeout_then_success_creates_one_refund_without_reclaiming_slots(db, monkeypatch):
    order, user = await pending(db, 2, age=20)
    monkeypatch.setattr('app.services.booking_locks.release_lock', AsyncMock())
    await expire_slot_orders(db, slot_ids=[11,12])
    assert order.status == 'cancelled'
    new, _ = await pending(db, 3)
    for sid in (11, 12):
        slot = await db.get(VenueTimeSlot, sid)
        slot.status, slot.locked_by = 'locked', user.id
    for _ in range(2):
        assert (await payment_callback._handle_payment_success(success(order), db))['code'] == 'SUCCESS'
    assert order.status == 'refunding' and order.wx_transaction_id == 'real-payment'
    refs = (await db.scalars(select(RefundRecord).where(RefundRecord.order_id == order.id))).all()
    assert len(refs) == 1 and refs[0].amount == 100
    assert refs[0].out_refund_no == order.refund_id
    assert (await db.get(VenueTimeSlot,11)).booking_order_id == new.id
    assert (await db.get(VenueTimeSlot,11)).status == 'locked'
    assert len((await db.scalars(select(Notification))).all()) == 1


@pytest.mark.asyncio
async def test_slot_conflict_never_books_only_part_of_order(db, monkeypatch):
    old, user = await pending(db, 2)
    second = await db.get(VenueTimeSlot, 12)
    second.booking_order_id = 999
    monkeypatch.setattr('app.services.booking_locks.release_lock', AsyncMock())
    await payment_callback._handle_payment_success(success(old), db)
    assert old.status == 'refunding'
    assert (await db.get(VenueTimeSlot, 11)).status == 'available'
    assert second.status == 'locked' and second.booking_order_id == 999


@pytest.mark.asyncio
async def test_refund_is_durable_and_idempotent_even_if_dispatch_fails(db, monkeypatch):
    order, user = await pending(db, 2)
    user.role = 'platform_admin'
    order.status, order.wx_transaction_id = 'paid', 'real-payment'
    monkeypatch.setattr(bookings, 'check_rate_limit', AsyncMock())
    monkeypatch.setattr(tasks.retry_failed_refunds, 'delay', Mock(side_effect=RuntimeError('broker down')))
    req = RefundRequest(amount=Decimal('40'), reason='partial')
    first = await bookings.refund_booking(2, req, user, db)
    second = await bookings.refund_booking(2, req, user, db)
    assert first['status'] == second['status'] == 'refunding'
    refs = (await db.scalars(select(RefundRecord).where(RefundRecord.order_id == 2))).all()
    assert len(refs) == 1 and order.refund_amount == 40
    assert first['out_refund_no'] == second['out_refund_no'] == order.refund_id
    with pytest.raises(HTTPException):
        await bookings.refund_booking(2, RefundRequest(amount=50), user, db)


@pytest.mark.asyncio
async def test_refund_response_lost_then_query_success_uses_same_intent(db, monkeypatch):
    order, rec = await _stale(db, 2)
    wx = Mock()
    wx.query_refund.return_value = (404, json.dumps({'code':'RESOURCE_NOT_EXISTS'}))
    wx.refund.side_effect = httpx.ReadTimeout('response lost')
    assert (await _run(tasks._retry_failed_refunds_impl, db, monkeypatch, wx))['errors'] == 1
    number = rec.out_refund_no
    assert order.status == 'refunding' and rec.retry_count == 1
    rec.scheduled_at = datetime.utcnow() - timedelta(seconds=1)
    await db.commit()
    wx.query_refund.return_value = (200,json.dumps({'out_refund_no':number,
        'out_trade_no':order.order_no, 'status':'SUCCESS', 'amount':{'refund':10000}}))
    assert (await _run(tasks._retry_failed_refunds_impl, db, monkeypatch, wx))['processed'] == 1
    assert order.status == 'refunded' and rec.out_refund_no == number
    assert wx.refund.call_count == 1


@pytest.mark.asyncio
async def test_refund_task_cannot_release_new_order_for_same_user(db, monkeypatch):
    old, user = await pending(db, 2)
    old.status = 'refunding'
    new, _ = await pending(db, 3)
    release = AsyncMock()
    monkeypatch.setattr('app.services.booking_locks.release_lock', release)
    db.add(RefundRecord(order_id=old.id,out_refund_no='BR2',amount=100,status='processing'))
    await db.flush()
    assert (await payment_callback._handle_refund_callback({'out_trade_no':old.order_no,
        'out_refund_no':'BR2','refund_status':'SUCCESS','amount':{'refund':10000}},db))['code'] == 'SUCCESS'
    for sid in (11,12):
        slot = await db.get(VenueTimeSlot,sid)
        assert slot.status == 'locked' and slot.booking_order_id == new.id
    release.assert_not_awaited()


@pytest.mark.asyncio
async def test_refund_success_uses_booking_owner_and_clears_slot_owner(db, monkeypatch):
    order, user = await pending(db, 2)
    order.status = 'refunding'
    release = AsyncMock()
    monkeypatch.setattr('app.services.booking_locks.release_lock', release)
    db.add(RefundRecord(order_id=order.id,out_refund_no='BR2',amount=100,status='processing'))
    await db.flush()
    await payment_callback._handle_refund_callback({'out_trade_no':order.order_no,
        'out_refund_no':'BR2','refund_status':'SUCCESS','amount':{'refund':10000}},db)
    assert release.await_count == 2
    assert all(call.args[1] == 'booking:review-2' for call in release.await_args_list)
    assert (await db.get(VenueTimeSlot,11)).booking_order_id is None


@pytest.mark.asyncio
async def test_cancelled_review_registration_cannot_be_resurrected(tournament_db):
    db = tournament_db
    tid, owner = await event(db, 2, TournamentConfig(approval_required=True))
    row = await register(db,tid,2)
    user = await db.get(User,'2')
    await tournaments.cancel_registration(tid,row['registration_id'],ReasonCommand(reason='退出'),user,db)
    with pytest.raises(HTTPException) as exc:
        await tournaments.review(tid,row['registration_id'],ReviewCommand(approved=True,reason='旧页面审核'),owner,db)
    assert exc.value.status_code == 409
    r = await tournaments.own(db,await life.locked_event(db,tid),user)
    assert r.admission == 'cancelled' and r.status == 'cancelled'


@pytest.mark.asyncio
async def test_cancelled_prepay_can_sync_late_money(db, monkeypatch):
    order, user = await pending(db,2)
    order.status, order.prepay_id = 'cancelled', 'prepay'
    monkeypatch.setattr(bookings.settings,'WX_PAY_ENABLED',True)
    monkeypatch.setattr(bookings,'check_rate_limit',AsyncMock())
    monkeypatch.setattr('app.services.booking_locks.release_lock',AsyncMock())
    wx = Mock(); wx.query.return_value=(200,json.dumps(success(order)))
    monkeypatch.setattr(bookings,'get_wxpay',Mock(return_value=wx))
    assert (await bookings.sync_booking_payment(2,user,db))['status'] == 'refunding'


@pytest.mark.asyncio
async def test_booking_recovery_queries_success_before_close(db,monkeypatch):
    order,user = await pending(db,2)
    order.status,order.prepay_id = 'cancelled','prepay'
    await db.commit()
    monkeypatch.setattr(bookings.settings,'WX_PAY_ENABLED',True)
    monkeypatch.setattr('app.services.booking_locks.release_lock',AsyncMock())
    wx = Mock(); wx.query.return_value=(200,json.dumps(success(order)))
    monkeypatch.setattr('app.services.booking_payment_recovery.get_wxpay',Mock(return_value=wx))
    assert (await maintain(db))['processed'] == 1
    assert order.status == 'refunding'
    wx.close.assert_not_called()


@pytest.mark.asyncio
async def test_booking_recovery_closes_unpaid_cancelled_order(db,monkeypatch):
    order,user = await pending(db,2)
    order.status,order.prepay_id = 'cancelled','prepay'
    await db.commit()
    monkeypatch.setattr(bookings.settings,'WX_PAY_ENABLED',True)
    wx = Mock(); wx.query.return_value=(200,json.dumps({'trade_state':'NOTPAY'})); wx.close.return_value=(204,'')
    monkeypatch.setattr('app.services.booking_payment_recovery.get_wxpay',Mock(return_value=wx))
    assert (await maintain(db))['processed'] == 1
    assert order.status == 'cancelled' and order.prepay_id is None
    wx.close.assert_called_once_with(out_trade_no=order.order_no)


@pytest.mark.asyncio
async def test_lost_prepay_response_leaves_durable_recovery_intent(db,monkeypatch):
    order,user = await pending(db,2)
    monkeypatch.setattr(bookings.settings,'WX_PAY_ENABLED',True)
    monkeypatch.setattr(bookings,'check_rate_limit',AsyncMock())
    monkeypatch.setattr(bookings,'_wx_prepay',AsyncMock(side_effect=httpx.ReadTimeout('lost prepay')))
    with pytest.raises(HTTPException) as exc:
        await bookings.pay_booking(2,user,db)
    assert exc.value.status_code == 502
    await db.rollback()
    order = await db.get(BookingOrder,2)
    assert await db.scalar(select(PaymentLog.id).where(PaymentLog.order_id == 2,
        PaymentLog.event_type == 'PREPAY_REQUESTED'))
    assert order.prepay_id is None
    order.status = 'cancelled'
    await db.commit()
    monkeypatch.setattr('app.services.booking_locks.release_lock',AsyncMock())
    wx = Mock(); wx.query.return_value=(200,json.dumps(success(order)))
    monkeypatch.setattr('app.services.booking_payment_recovery.get_wxpay',Mock(return_value=wx))
    assert (await maintain(db))['processed'] == 1
    assert order.status == 'refunding'


@pytest.mark.asyncio
async def test_prepay_has_local_lock_expiration(db,monkeypatch):
    order,user = await pending(db,2)
    wx = Mock(); wx.pay.return_value=(200,json.dumps({'prepay_id':'isolated'}))
    monkeypatch.setattr(bookings,'get_wxpay',Mock(return_value=wx))
    await bookings._wx_prepay(order,user)
    expiry = datetime.fromisoformat(wx.pay.call_args.kwargs['time_expire'])
    assert expiry == (order.created_at + timedelta(seconds=bookings.settings.BOOKING_LOCK_TTL_SECONDS)).replace(tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_failed_slot_release_does_not_commit_partial_refund_transition(db,monkeypatch):
    order,rec = await _stale(db,2)
    wx = Mock(); wx.query_refund.return_value=(200,json.dumps({'out_refund_no':rec.out_refund_no,
        'out_trade_no':order.order_no,'status':'SUCCESS','amount':{'refund':10000}}))
    # _run mocks Redis release; fail the shared slot release above that boundary.
    monkeypatch.setattr(payment_callback,'release_order_slots',AsyncMock(side_effect=RuntimeError('Redis down')))
    assert (await _run(tasks._retry_failed_refunds_impl,db,monkeypatch,wx))['errors'] == 1
    await db.refresh(order); await db.refresh(rec)
    assert order.status == 'refunding' and rec.status == 'pending'


@pytest.mark.asyncio
async def test_signed_historical_refund_without_intent_is_recorded(db,monkeypatch):
    order,user = await pending(db,2)
    order.status,order.wx_transaction_id = 'paid','historical-real'
    monkeypatch.setattr('app.services.booking_locks.release_lock',AsyncMock())
    outcome = await payment_callback._handle_refund_callback({'out_trade_no':order.order_no,
        'out_refund_no':'console-refund','refund_status':'SUCCESS','amount':{'refund':10000}},db)
    assert outcome['code'] == 'SUCCESS' and order.status == 'refunded'
    assert await db.scalar(select(RefundRecord.id).where(RefundRecord.out_refund_no == 'console-refund'))
