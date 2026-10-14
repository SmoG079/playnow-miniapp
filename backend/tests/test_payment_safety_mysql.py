"""Payment races against a disposable MySQL and Redis, with WeChat mocked."""
import asyncio
import json
from datetime import datetime, timedelta
from unittest.mock import Mock
import pytest
from sqlalchemy import select, func
from app.models.models import User, BookingOrder, RefundRecord, VenueTimeSlot, Notification
from app.api.v1 import bookings
from app.schemas.schemas import BookingCreateRequest, RefundRequest, CancelRequest
from app.services import payment_callback
from app.tasks import tasks
from app.tasks.runtime import task_session_factory
from tests.test_review_booking_mysql import resources, pytestmark


async def booking(resources, *, expired=False, paid=False):
    factory, client, user_ids, slot_ids, *_ = resources
    async with factory() as db:
        user = await db.get(User, user_ids[0])
        user.role = 'platform_admin'
        result = await bookings.create_booking(BookingCreateRequest(slot_ids=slot_ids), user, db)
        order = await db.get(BookingOrder, result.id)
        if expired:
            order.created_at = datetime.utcnow() - timedelta(minutes=20)
            for sid in slot_ids:
                slot = await db.get(VenueTimeSlot, sid)
                await client.delete(f'slot:{slot.venue_id}:{slot.date}:{slot.start_time}')
        if paid:
            order.status, order.wx_transaction_id = 'paid', 'real-mysql-transaction'
        await db.commit()
        return order.id, order.order_no


@pytest.mark.asyncio
@pytest.mark.parametrize("methods", [("refund", "refund"), ("cancel", "cancel"), ("cancel", "refund")])
async def test_concurrent_cancellations_and_admin_refunds_share_one_intent(resources, monkeypatch, methods):
    factory, client, user_ids, slot_ids, *_ = resources
    ident, _ = await booking(resources, paid=True)
    monkeypatch.setattr(tasks.retry_failed_refunds, 'delay', Mock())
    gate = asyncio.Event()
    async def refund(method):
        async with factory() as db:
            user = await db.get(User, user_ids[0])
            await gate.wait()
            if method == "cancel":
                return await bookings.cancel_booking(ident, CancelRequest(), user, db)
            return await bookings.refund_booking(ident, RefundRequest(), user, db)
    calls = [asyncio.create_task(refund(method)) for method in methods]
    gate.set()
    results = await asyncio.gather(*calls)
    assert len({r['out_refund_no'] for r in results}) == 1
    async with factory() as db:
        assert await db.scalar(select(func.count(RefundRecord.id)).where(RefundRecord.order_id == ident)) == 1
        assert (await db.get(BookingOrder, ident)).status == 'refunding'


@pytest.mark.asyncio
async def test_late_payment_racing_rebooking_never_takes_new_slots(resources):
    factory, client, user_ids, slot_ids, *_ = resources
    ident, number = await booking(resources, expired=True)
    gate = asyncio.Event()
    async def callback():
        async with factory() as db:
            await gate.wait()
            outcome = await payment_callback._handle_payment_success({'out_trade_no':number,
                'transaction_id':'late-mysql-payment','amount':{'total':10000}}, db)
            await db.commit()
            return outcome
    async def rebook():
        async with factory() as db:
            user = await db.get(User,user_ids[0])
            await gate.wait()
            return await bookings.create_booking(BookingCreateRequest(slot_ids=slot_ids),user,db)
    calls = [asyncio.create_task(callback()), asyncio.create_task(rebook())]
    gate.set()
    outcome, new = await asyncio.gather(*calls)
    assert outcome['code'] == 'SUCCESS'
    async with factory() as db:
        assert (await db.get(BookingOrder,ident)).status == 'refunding'
        assert (await db.get(BookingOrder,new.id)).status == 'pending'
        for sid in slot_ids:
            slot = await db.get(VenueTimeSlot,sid)
            assert slot.booking_order_id == new.id and slot.status == 'locked'
            assert await client.get(f'slot:{slot.venue_id}:{slot.date}:{slot.start_time}') == f'booking:{new.order_no}'


@pytest.mark.asyncio
async def test_refund_callback_and_poll_are_serialized(resources,monkeypatch):
    factory, client, user_ids, slot_ids, *_ = resources
    ident, number = await booking(resources,paid=True)
    monkeypatch.setattr(tasks.retry_failed_refunds,'delay',Mock())
    async with factory() as db:
        response = await bookings.refund_booking(ident,RefundRequest(),await db.get(User,user_ids[0]),db)
    payload = {'out_trade_no':number,'out_refund_no':response['out_refund_no'],
        'status':'SUCCESS','refund_status':'SUCCESS','amount':{'refund':10000}}
    wx = Mock(); wx.query_refund.return_value=(200,json.dumps(payload))
    monkeypatch.setattr('app.core.wechat_pay.get_wxpay',Mock(return_value=wx))
    gate = asyncio.Event()
    async def callback():
        async with factory() as db:
            await gate.wait()
            result = await payment_callback._handle_refund_callback(payload,db)
            await db.commit()
            return result
    async def poll():
        token = task_session_factory.set(factory)
        try:
            await gate.wait()
            return await tasks._retry_failed_refunds_impl()
        finally:
            task_session_factory.reset(token)
    calls = [asyncio.create_task(callback()),asyncio.create_task(poll())]
    gate.set()
    await asyncio.gather(*calls)
    async with factory() as db:
        assert (await db.get(BookingOrder,ident)).status == 'refunded'
        assert await db.scalar(select(func.count(Notification.id)).where(Notification.ref_id == ident,
            Notification.ref_type == 'booking',Notification.title == '退款成功')) == 1
        for sid in slot_ids:
            assert (await db.get(VenueTimeSlot,sid)).booking_order_id is None
