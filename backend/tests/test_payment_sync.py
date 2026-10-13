"""主动查单兜底契约：POST /bookings/{id}/sync-payment。

微信回调链路不可达时（例如回调域名未完成 ICP 备案、443 被拦截），订单会一直
停在 pending，尽管款项已进入商户号。该接口让前端主动向微信查单，命中成功则
复用回调的落库逻辑（``_handle_payment_success``），共用同一套状态机与幂等保护。

这里只锁定行为契约，不真连微信：``get_wxpay`` 与限流都被替换掉。
"""
import json
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.api.v1 import bookings
from app.models.models import RefundRecord, VenueTimeSlot
from tests.test_review_fixes import db, pending


def _wx_with_query(return_value=None, side_effect=None):
    """构造一个 wxpay 替身，其 query() 返回 (http_status, body_text)。"""
    wx = Mock()
    wx.query = Mock(return_value=return_value, side_effect=side_effect)
    return wx


def _wx_with_refund_query(payload=None, status=200, side_effect=None):
    """构造一个 wxpay 替身；query_refund() 返回 (http_status, body_text) 元组。

    传入 ``payload``（dict）时会封装成指定 HTTP 状态的 JSON 响应体，
    用例只需关心业务字段。
    """
    wx = Mock()
    if side_effect is not None:
        wx.query_refund = Mock(side_effect=side_effect)
    else:
        wx.query_refund = Mock(return_value=(status, json.dumps(payload)))
    return wx


@pytest.mark.asyncio
async def test_sync_is_noop_in_placeholder_mode(db, monkeypatch):
    """占位模式没有真实交易：不查单，状态保持 pending。"""
    order, user = await pending(db, 2)
    monkeypatch.setattr(bookings.settings, "WX_PAY_ENABLED", False)
    monkeypatch.setattr(bookings, "check_rate_limit", AsyncMock())
    wx = Mock(side_effect=AssertionError("占位模式不得调用微信"))
    monkeypatch.setattr(bookings, "get_wxpay", wx)

    result = await bookings.sync_booking_payment(2, user, db)

    assert result["status"] == "pending"
    assert result["payment_mode"] == "placeholder"
    assert order.status == "pending"
    wx.assert_not_called()


@pytest.mark.asyncio
async def test_sync_returns_terminal_status_without_querying(db, monkeypatch):
    """已终态的订单直接回报，不再查单（幂等且省一次外部调用）。"""
    order, user = await pending(db, 2)
    order.status = "paid"
    await db.flush()
    monkeypatch.setattr(bookings.settings, "WX_PAY_ENABLED", True)
    monkeypatch.setattr(bookings, "check_rate_limit", AsyncMock())
    wx = Mock(side_effect=AssertionError("终态订单不应再查单"))
    monkeypatch.setattr(bookings, "get_wxpay", wx)

    result = await bookings.sync_booking_payment(2, user, db)

    assert result["status"] == "paid"
    wx.assert_not_called()


@pytest.mark.asyncio
async def test_sync_rejects_other_users_order(db, monkeypatch):
    """只能同步自己的订单。"""
    await pending(db, 2)
    monkeypatch.setattr(bookings, "check_rate_limit", AsyncMock())
    intruder = Mock()
    intruder.id = "999"

    with pytest.raises(HTTPException) as exc:
        await bookings.sync_booking_payment(2, intruder, db)

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_sync_success_marks_paid_through_shared_callback_logic(db, monkeypatch):
    """查单命中 SUCCESS：走与回调完全相同的落库逻辑，订单转 paid、时段转 booked。"""
    order, user = await pending(db, 2)
    monkeypatch.setattr(bookings.settings, "WX_PAY_ENABLED", True)
    monkeypatch.setattr(bookings, "check_rate_limit", AsyncMock())
    # 落库走的是 payment_callback._handle_payment_success，它引用的是该模块自己的
    # release_lock；必须 patch 那一处，否则会真连 Redis（模块级单例绑定首个 event
    # loop，后续用例复用会抛 "Event loop is closed"）。
    monkeypatch.setattr("app.services.payment_callback.release_lock", AsyncMock())
    payload = {
        "out_trade_no": "review-2",
        "transaction_id": "42000012345678901234567890",
        "trade_state": "SUCCESS",
        # order.amount = 100 元 → 10000 分，金额必须与下单一致
        "amount": {"total": 10000, "payer_total": 10000, "currency": "CNY"},
    }
    wx = _wx_with_query(return_value=(200, json.dumps(payload)))
    monkeypatch.setattr(bookings, "get_wxpay", Mock(return_value=wx))

    result = await bookings.sync_booking_payment(2, user, db)

    assert result["status"] == "paid"
    assert order.status == "paid"
    assert order.wx_transaction_id == "42000012345678901234567890"
    assert order.payment_time is not None
    for sid in (11, 12):
        slot = await db.get(VenueTimeSlot, sid)
        assert slot.status == "booked" and slot.locked_by is None
    wx.query.assert_called_once_with(out_trade_no="review-2")


@pytest.mark.asyncio
async def test_sync_keeps_pending_when_wechat_says_not_paid(db, monkeypatch):
    """微信侧仍是 NOTPAY：不改状态，前端据此提示用户继续支付。"""
    order, user = await pending(db, 2)
    monkeypatch.setattr(bookings.settings, "WX_PAY_ENABLED", True)
    monkeypatch.setattr(bookings, "check_rate_limit", AsyncMock())
    wx = _wx_with_query(
        return_value=(200, json.dumps({"out_trade_no": "review-2", "trade_state": "NOTPAY"}))
    )
    monkeypatch.setattr(bookings, "get_wxpay", Mock(return_value=wx))

    result = await bookings.sync_booking_payment(2, user, db)

    assert result["status"] == "pending" and result["trade_state"] == "NOTPAY"
    assert order.status == "pending"
    assert order.payment_time is None


@pytest.mark.asyncio
async def test_sync_keeps_pending_on_non_2xx(db, monkeypatch):
    """微信返回 4xx（如 ORDER_NOT_EXIST）：保持 pending，不抛错打扰用户。"""
    order, user = await pending(db, 2)
    monkeypatch.setattr(bookings.settings, "WX_PAY_ENABLED", True)
    monkeypatch.setattr(bookings, "check_rate_limit", AsyncMock())
    wx = _wx_with_query(
        return_value=(404, json.dumps({"code": "ORDER_NOT_EXIST", "message": "订单不存在"}))
    )
    monkeypatch.setattr(bookings, "get_wxpay", Mock(return_value=wx))

    result = await bookings.sync_booking_payment(2, user, db)

    assert result["status"] == "pending"
    assert order.status == "pending"


@pytest.mark.asyncio
async def test_sync_returns_502_when_wechat_unreachable(db, monkeypatch):
    """调用微信失败：报 502 让前端稍后重试，绝不错标为已支付。"""
    order, user = await pending(db, 2)
    monkeypatch.setattr(bookings.settings, "WX_PAY_ENABLED", True)
    monkeypatch.setattr(bookings, "check_rate_limit", AsyncMock())
    wx = _wx_with_query(side_effect=RuntimeError("network down"))
    monkeypatch.setattr(bookings, "get_wxpay", Mock(return_value=wx))

    with pytest.raises(HTTPException) as exc:
        await bookings.sync_booking_payment(2, user, db)

    assert exc.value.status_code == 502
    assert order.status == "pending"


# ---------------------------------------------------------------------------
# 退款主动查单兜底：POST /bookings/{id}/sync-refund
#
# 退款与支付共用同一个回调地址，回调不可达时订单会一直停在 refunding，
# 而款项其实已退回。该接口让用户/管理员即时向微信查退款进度，命中终态时复用
# 回调的落库逻辑（``_handle_refund_callback``），避免出现第三套状态机。
# ---------------------------------------------------------------------------


async def refunding(db, ident, refund_status="processing"):
    """构造一笔已发起退款的订单：订单 refunding + 退款单记录。"""
    order, user = await pending(db, ident)
    order.status = "refunding"
    order.refund_id = f"{order.order_no}-refund"
    order.refund_amount = order.amount
    order.wx_transaction_id = "42000012345678901234567890"
    db.add(
        RefundRecord(
            order_id=order.id,
            out_refund_no=order.refund_id,
            amount=order.amount,
            status=refund_status,
        )
    )
    await db.flush()
    return order, user


@pytest.mark.asyncio
async def test_sync_refund_is_noop_in_placeholder_mode(db, monkeypatch):
    """占位模式没有真实交易：不查退款，状态保持 refunding。"""
    order, user = await refunding(db, 2)
    monkeypatch.setattr(bookings.settings, "WX_PAY_ENABLED", False)
    monkeypatch.setattr(bookings, "check_rate_limit", AsyncMock())
    wx = Mock(side_effect=AssertionError("占位模式不得调用微信"))
    monkeypatch.setattr(bookings, "get_wxpay", wx)

    result = await bookings.sync_booking_refund(2, user, db)

    assert result["status"] == "refunding"
    assert result["payment_mode"] == "placeholder"
    assert order.status == "refunding"
    wx.assert_not_called()


@pytest.mark.asyncio
async def test_sync_refund_returns_terminal_without_querying(db, monkeypatch):
    """已退款的订单直接回报，不再查单（幂等且省一次外部调用）。"""
    order, user = await refunding(db, 2, refund_status="success")
    order.status = "refunded"
    order.refund_status = "success"
    await db.flush()
    monkeypatch.setattr(bookings.settings, "WX_PAY_ENABLED", True)
    monkeypatch.setattr(bookings, "check_rate_limit", AsyncMock())
    wx = Mock(side_effect=AssertionError("终态订单不应再查单"))
    monkeypatch.setattr(bookings, "get_wxpay", wx)

    result = await bookings.sync_booking_refund(2, user, db)

    assert result["status"] == "refunded" and result["refund_status"] == "success"
    wx.assert_not_called()


@pytest.mark.asyncio
async def test_sync_refund_rejects_unrelated_user(db, monkeypatch):
    """与退款无关的普通用户不得查询该单退款。"""
    await refunding(db, 2)
    monkeypatch.setattr(bookings, "check_rate_limit", AsyncMock())
    intruder = Mock()
    intruder.id = "999"

    with pytest.raises(HTTPException) as exc:
        await bookings.sync_booking_refund(2, intruder, db)

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_sync_refund_allows_platform_admin(db, monkeypatch):
    """平台管理员可查任意订单退款（运维需要）。"""
    order, _ = await refunding(db, 2)
    monkeypatch.setattr(bookings.settings, "WX_PAY_ENABLED", True)
    monkeypatch.setattr(bookings, "check_rate_limit", AsyncMock())
    wx = _wx_with_refund_query(payload={"out_refund_no": order.refund_id,
                                        "out_trade_no": order.order_no,
                                        "status": "PROCESSING"})
    monkeypatch.setattr(bookings, "get_wxpay", Mock(return_value=wx))
    admin = Mock()
    admin.id = "999"
    admin.role = "platform_admin"

    result = await bookings.sync_booking_refund(2, admin, db)

    assert result["status"] == "refunding"
    assert result["refund_state"] == "PROCESSING"
    wx.query_refund.assert_called_once_with(out_refund_no=order.refund_id)


@pytest.mark.asyncio
async def test_sync_refund_success_marks_refunded_through_shared_callback_logic(db, monkeypatch):
    """查退款命中 SUCCESS：走与回调完全相同的落库逻辑，订单转 refunded、时段释放。"""
    order, user = await refunding(db, 2)
    monkeypatch.setattr(bookings.settings, "WX_PAY_ENABLED", True)
    monkeypatch.setattr(bookings, "check_rate_limit", AsyncMock())
    # 落库走 payment_callback._handle_refund_callback → release_order_slots，
    # 其中的 release_lock 必须 patch，否则会真连 Redis（模块级单例绑定首个
    # event loop，后续用例复用会抛 "Event loop is closed"）。
    monkeypatch.setattr("app.services.booking_locks.release_lock", AsyncMock())
    wx = _wx_with_refund_query(payload={
        "out_refund_no": order.refund_id,
        "out_trade_no": order.order_no,
        "refund_id": "50300012345678901234567890",
        "status": "SUCCESS",
        "amount": {"total": 10000, "refund": 10000, "currency": "CNY"},
    })
    monkeypatch.setattr(bookings, "get_wxpay", Mock(return_value=wx))

    result = await bookings.sync_booking_refund(2, user, db)

    assert result["status"] == "refunded"
    assert result["refund_status"] == "success"
    assert order.status == "refunded"
    assert order.refund_time is not None
    record = (
        await db.execute(
            select(RefundRecord).where(RefundRecord.out_refund_no == order.refund_id)
        )
    ).scalar_one()
    assert record.status == "success"
    assert record.wx_refund_id == "50300012345678901234567890"
    for sid in (11, 12):
        slot = await db.get(VenueTimeSlot, sid)
        assert slot.status == "available" and slot.locked_by is None


@pytest.mark.asyncio
async def test_sync_refund_keeps_refunding_while_processing(db, monkeypatch):
    """微信侧仍是 PROCESSING：不改状态，前端据此提示退款仍在处理中。"""
    order, user = await refunding(db, 2)
    monkeypatch.setattr(bookings.settings, "WX_PAY_ENABLED", True)
    monkeypatch.setattr(bookings, "check_rate_limit", AsyncMock())
    wx = _wx_with_refund_query(payload={"out_refund_no": order.refund_id,
                                        "out_trade_no": order.order_no,
                                        "status": "PROCESSING"})
    monkeypatch.setattr(bookings, "get_wxpay", Mock(return_value=wx))

    result = await bookings.sync_booking_refund(2, user, db)

    assert result["status"] == "refunding"
    assert order.status == "refunding"
    assert order.refund_time is None


@pytest.mark.asyncio
async def test_sync_refund_rejects_mismatched_refund_no(db, monkeypatch):
    """微信返回的退款单与本单不对应：报 502，绝不落库（防错单）。"""
    order, user = await refunding(db, 2)
    monkeypatch.setattr(bookings.settings, "WX_PAY_ENABLED", True)
    monkeypatch.setattr(bookings, "check_rate_limit", AsyncMock())
    wx = _wx_with_refund_query(payload={
        "out_refund_no": "someone-elses-refund",
        "out_trade_no": order.order_no,
        "status": "SUCCESS",
    })
    monkeypatch.setattr(bookings, "get_wxpay", Mock(return_value=wx))

    with pytest.raises(HTTPException) as exc:
        await bookings.sync_booking_refund(2, user, db)

    assert exc.value.status_code == 502
    assert order.status == "refunding"


@pytest.mark.asyncio
async def test_sync_refund_requires_a_refund_record(db, monkeypatch):
    """从未发起退款的订单：报 400，不做无意义的查单。"""
    order, user = await pending(db, 2)
    monkeypatch.setattr(bookings.settings, "WX_PAY_ENABLED", True)
    monkeypatch.setattr(bookings, "check_rate_limit", AsyncMock())
    wx = Mock(side_effect=AssertionError("无退款记录时不应查单"))
    monkeypatch.setattr(bookings, "get_wxpay", wx)

    with pytest.raises(HTTPException) as exc:
        await bookings.sync_booking_refund(2, user, db)

    assert exc.value.status_code == 400
    wx.assert_not_called()


@pytest.mark.asyncio
async def test_sync_refund_returns_502_when_wechat_unreachable(db, monkeypatch):
    """调用微信失败：报 502，绝不自行把退款标成成功。"""
    order, user = await refunding(db, 2)
    monkeypatch.setattr(bookings.settings, "WX_PAY_ENABLED", True)
    monkeypatch.setattr(bookings, "check_rate_limit", AsyncMock())
    wx = _wx_with_refund_query(side_effect=RuntimeError("network down"))
    monkeypatch.setattr(bookings, "get_wxpay", Mock(return_value=wx))

    with pytest.raises(HTTPException) as exc:
        await bookings.sync_booking_refund(2, user, db)

    assert exc.value.status_code == 502
    assert order.status == "refunding"


@pytest.mark.asyncio
async def test_sync_refund_keeps_refunding_on_non_2xx(db, monkeypatch):
    """微信返回 4xx（如单号不存在）：保持 refunding，不抛错打扰用户。"""
    order, user = await refunding(db, 2)
    monkeypatch.setattr(bookings.settings, "WX_PAY_ENABLED", True)
    monkeypatch.setattr(bookings, "check_rate_limit", AsyncMock())
    wx = _wx_with_refund_query(
        payload={"code": "RESOURCE_NOT_EXISTS", "message": "退款单不存在"},
        status=404,
    )
    monkeypatch.setattr(bookings, "get_wxpay", Mock(return_value=wx))

    result = await bookings.sync_booking_refund(2, user, db)

    assert result["status"] == "refunding"
    assert order.status == "refunding"
