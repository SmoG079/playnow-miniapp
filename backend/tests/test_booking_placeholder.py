"""Temporary booking confirmation must not activate real collection via environment flags."""
from unittest.mock import AsyncMock, Mock
import pytest
from app.api.v1 import bookings
from app.models.models import VenueTimeSlot
from tests.test_review_fixes import db, pending

@pytest.mark.asyncio
@pytest.mark.parametrize('enabled',[False,True])
async def test_placeholder_confirms_all_slots_without_wechat(db,monkeypatch,enabled):
    order,user=await pending(db,2)
    monkeypatch.setattr(bookings.settings,'WX_PAY_ENABLED',enabled)
    monkeypatch.setattr(bookings,'check_rate_limit',AsyncMock())
    release=AsyncMock();monkeypatch.setattr(bookings,'release_lock',release)
    wx=Mock(side_effect=AssertionError('Real payment must remain paused'))
    monkeypatch.setattr(bookings,'get_wxpay',wx)
    prepay=AsyncMock(side_effect=AssertionError('No unified order'))
    monkeypatch.setattr(bookings,'_wx_prepay',prepay)
    result=await bookings.pay_booking(2,user,db)
    assert result['payment_mode']=='placeholder' and 'pay_params' not in result
    assert order.status=='paid' and order.wx_transaction_id=='dev_review-2'
    for sid in (11,12):
        slot=await db.get(VenueTimeSlot,sid)
        assert slot.status=='booked' and slot.locked_by is None and slot.booking_order_id==order.id
    assert release.await_count==2
    assert (await bookings.pay_booking(2,user,db))['already_paid']
    assert release.await_count==2
    wx.assert_not_called();prepay.assert_not_awaited()
