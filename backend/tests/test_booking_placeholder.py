"""订场支付契约：WX_PAY_ENABLED=false 走占位，=true 走真实微信预支付。

生产必须是 true（启动日志会打印实际状态）；本地与 CI 未配置商户号，
默认 false 时 pay_booking 只做占位确认，绝不触碰任何微信接口。
"""
from unittest.mock import AsyncMock, Mock
import pytest
from app.api.v1 import bookings
from app.models.models import VenueTimeSlot
from tests.test_review_fixes import db, pending


@pytest.mark.asyncio
async def test_placeholder_confirms_all_slots_without_wechat(db, monkeypatch):
    """开关关闭：占位确认，订单直接置 paid，不调用任何微信接口。"""
    order, user = await pending(db, 2)
    monkeypatch.setattr(bookings.settings, "WX_PAY_ENABLED", False)
    monkeypatch.setattr(bookings, "check_rate_limit", AsyncMock())
    release = AsyncMock(); monkeypatch.setattr(bookings, "release_lock", release)
    wx = Mock(side_effect=AssertionError("WX_PAY_ENABLED=false 时不得调用微信接口"))
    monkeypatch.setattr(bookings, "get_wxpay", wx)
    prepay = AsyncMock(side_effect=AssertionError("WX_PAY_ENABLED=false 时不得统一下单"))
    monkeypatch.setattr(bookings, "_wx_prepay", prepay)
    result = await bookings.pay_booking(2, user, db)
    assert result["payment_mode"] == "placeholder" and "pay_params" not in result
    assert order.status == "paid" and order.wx_transaction_id == "dev_review-2"
    for sid in (11, 12):
        slot = await db.get(VenueTimeSlot, sid)
        assert slot.status == "booked" and slot.locked_by is None and slot.booking_order_id == order.id
    assert release.await_count == 2
    assert (await bookings.pay_booking(2, user, db))["already_paid"]
    assert release.await_count == 2
    wx.assert_not_called(); prepay.assert_not_awaited()


@pytest.mark.asyncio
async def test_enabled_pay_returns_jsapi_params_and_waits_for_callback(db, monkeypatch):
    """开关打开：统一下单并把收银台参数交给前端；订单与时段锁留给回调改写。"""
    order, user = await pending(db, 2)
    assert user.openid and not user.openid.startswith("dev_")
    monkeypatch.setattr(bookings.settings, "WX_PAY_ENABLED", True)
    monkeypatch.setattr(bookings, "check_rate_limit", AsyncMock())
    release = AsyncMock(); monkeypatch.setattr(bookings, "release_lock", release)
    prepay = AsyncMock(return_value={"prepay_id": "prepay_real_1"})
    monkeypatch.setattr(bookings, "_wx_prepay", prepay)
    monkeypatch.setattr(bookings, "get_wxpay", Mock(return_value="wxpay-client"))
    monkeypatch.setattr(
        bookings,
        "build_jsapi_params",
        Mock(return_value={"package": "prepay_id=prepay_real_1", "paySign": "sig"}),
    )
    result = await bookings.pay_booking(2, user, db)
    assert result["pay_params"]["paySign"] == "sig"
    assert order.status == "pending" and order.payment_time is None
    assert order.prepay_id == "prepay_real_1" and order.prepay_id_created_at is not None
    prepay.assert_awaited_once()
    release.assert_not_awaited()
    for sid in (11, 12):
        slot = await db.get(VenueTimeSlot, sid)
        assert slot.status == "locked" and slot.booking_order_id == order.id
