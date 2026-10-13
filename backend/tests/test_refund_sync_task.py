"""退款兜底任务契约：``retry_failed_refunds`` / ``poll_processing_refunds``。

这两条 Celery 定时链路是「微信回调不可达」时的最后一道保险（回调域名未备案、
443 被拦截时，退款只能在服务端主动查询）。历史上它们把微信 SDK 返回的
``(http_status, text)`` 元组直接当成 dict 使用（``resp.get(...)``），后果是：

* 每次查询都抛 AttributeError，被 ``except`` 吞掉 —— 退款兜底**完全失效**；
* 更糟的是原异常分支会把订单从 ``refunding`` 回退成 ``paid``，而款项其实已经退回，
  造成资金与订单状态不一致。

这里锁定修复后的行为契约：正确解析 SDK 响应；查询失败绝不回退订单。
"""
import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import select, text

from app.models.models import RefundRecord
from tests.test_payment_sync import refunding
from tests.test_review_fixes import db  # noqa: F401  fixture 复用


async def _stale(db, ident, status="pending"):
    """构造一笔「到点该重试」的退款记录（scheduled_at / updated_at 都已过期）。

    ``updated_at`` 带 ``onupdate``，走 ORM 更新会被自动改成当前时间，因此这里用
    原生 SQL 回填时间戳，绕过 onupdate，让定时任务的「到期/冷却」条件成立。
    """
    order, _ = await refunding(db, ident, refund_status=status)
    rec = (
        await db.execute(select(RefundRecord).where(RefundRecord.order_id == order.id))
    ).scalar_one()
    await db.execute(
        text("UPDATE refund_records SET scheduled_at = :t, updated_at = :t WHERE id = :i"),
        {"t": datetime.utcnow() - timedelta(minutes=5), "i": rec.id},
    )
    await db.commit()
    return order, rec


async def _run(impl, db, monkeypatch, wxpay):
    """在注入的 session 与 wxpay 替身下运行一个任务实现。"""
    from app.tasks.runtime import task_session_factory

    monkeypatch.setattr("app.core.wechat_pay.get_wxpay", Mock(return_value=wxpay))
    # 落库路径会释放时段锁；不 patch 会真连 Redis（模块级单例绑定首个 event loop）
    monkeypatch.setattr("app.tasks.tasks.release_lock", AsyncMock())

    @asynccontextmanager
    async def session():
        yield db

    token = task_session_factory.set(session)
    try:
        return await impl()
    finally:
        task_session_factory.reset(token)


@pytest.mark.asyncio
async def test_retry_refunds_parses_tuple_response_and_marks_success(db, monkeypatch):
    """回归：SDK 返回 (200, json) 元组时必须能正确解析并落库。

    修复前这里会抛 ``AttributeError: 'tuple' object has no attribute 'get'``，
    被外层 except 吞掉后退款永远不会被确认为成功。
    """
    from app.tasks.tasks import _retry_failed_refunds_impl

    order, rec = await _stale(db, 2)
    wxpay = Mock()
    wxpay.query_refund = Mock(return_value=(200, json.dumps({
        "out_refund_no": rec.out_refund_no,
        "out_trade_no": order.order_no,
        "refund_id": "50300012345678901234567890",
        "status": "SUCCESS",
    })))

    result = await _run(_retry_failed_refunds_impl, db, monkeypatch, wxpay)

    assert result["processed"] == 1
    assert result["errors"] == 0
    assert rec.status == "success"
    assert rec.wx_refund_id == "50300012345678901234567890"
    assert order.status == "refunded"
    assert order.refund_status == "success"
    assert order.refund_time is not None
    wxpay.query_refund.assert_called_once_with(out_refund_no=rec.out_refund_no)


@pytest.mark.asyncio
async def test_retry_refunds_query_failure_keeps_order_refunding(db, monkeypatch):
    """回归：查询退款状态失败时绝不把订单回退成 paid（款项可能其实已退成功）。"""
    from app.tasks.tasks import _retry_failed_refunds_impl

    order, rec = await _stale(db, 2)
    wxpay = Mock()
    wxpay.query_refund = Mock(side_effect=RuntimeError("network down"))

    result = await _run(_retry_failed_refunds_impl, db, monkeypatch, wxpay)

    assert result["errors"] == 1
    assert order.status == "refunding"
    assert order.refund_status != "failed"
    assert rec.status == "pending"
    assert rec.retry_count == 1


@pytest.mark.asyncio
async def test_retry_refunds_resubmits_when_wechat_has_no_record(db, monkeypatch):
    """微信侧查不到这笔退款单（4xx）→ 视作尚未成功提交，重新提交（同号幂等）。"""
    from app.tasks.tasks import _retry_failed_refunds_impl

    order, rec = await _stale(db, 2)
    wxpay = Mock()
    wxpay.query_refund = Mock(return_value=(404, json.dumps({"code": "RESOURCE_NOT_EXISTS"})))
    wxpay.refund = Mock(return_value=(200, json.dumps({
        "out_refund_no": rec.out_refund_no,
        "out_trade_no": order.order_no,
        "status": "PROCESSING",
    })))

    result = await _run(_retry_failed_refunds_impl, db, monkeypatch, wxpay)

    assert result["processed"] == 1
    wxpay.refund.assert_called_once()
    assert rec.status == "processing"
    assert order.status == "refunding"


@pytest.mark.asyncio
async def test_retry_refunds_rejected_resubmit_reverts_order(db, monkeypatch):
    """微信明确拒绝提交退款（4xx）→ 退款确实没成功，订单回退为已支付。"""
    from app.tasks.tasks import _retry_failed_refunds_impl

    order, rec = await _stale(db, 2)
    wxpay = Mock()
    wxpay.query_refund = Mock(return_value=(200, json.dumps({
        "out_refund_no": rec.out_refund_no,
        "out_trade_no": order.order_no,
        "status": "NOT_EXIST",
    })))
    wxpay.refund = Mock(return_value=(400, json.dumps({"code": "PARAM_ERROR"})))

    result = await _run(_retry_failed_refunds_impl, db, monkeypatch, wxpay)

    assert result["errors"] == 1
    assert rec.status == "failed"
    assert order.status == "paid"
    assert order.refund_status == "failed"


@pytest.mark.asyncio
async def test_poll_processing_refunds_marks_success(db, monkeypatch):
    """PROCESSING 轮询拿到终态后正确落库。"""
    from app.tasks.tasks import _poll_processing_refunds_impl

    order, rec = await _stale(db, 2, status="processing")
    wxpay = Mock()
    wxpay.query_refund = Mock(return_value=(200, json.dumps({
        "out_refund_no": rec.out_refund_no,
        "out_trade_no": order.order_no,
        "refund_id": "50300012345678901234567890",
        "status": "SUCCESS",
    })))

    result = await _run(_poll_processing_refunds_impl, db, monkeypatch, wxpay)

    assert result["processed"] == 1
    assert rec.status == "success"
    assert order.status == "refunded"


@pytest.mark.asyncio
async def test_poll_processing_refunds_unknown_state_keeps_order(db, monkeypatch):
    """回归：轮询到未知状态时保持 refunding，不武断回退订单。"""
    from app.tasks.tasks import _poll_processing_refunds_impl

    order, rec = await _stale(db, 2, status="processing")
    wxpay = Mock()
    wxpay.query_refund = Mock(return_value=(200, json.dumps({
        "out_refund_no": rec.out_refund_no,
        "out_trade_no": order.order_no,
        "status": "WEIRD_STATE",
    })))

    result = await _run(_poll_processing_refunds_impl, db, monkeypatch, wxpay)

    assert result["errors"] == 1
    # 该分支内部 rollback 会让 ORM 对象过期，断言行状态前先重新加载
    await db.refresh(order)
    await db.refresh(rec)
    assert order.status == "refunding"
    assert order.refund_status != "failed"
    assert rec.status == "processing"


@pytest.mark.asyncio
async def test_poll_processing_refunds_query_error_keeps_order(db, monkeypatch):
    """回归：轮询查询异常时保持 refunding。"""
    from app.tasks.tasks import _poll_processing_refunds_impl

    order, rec = await _stale(db, 2, status="processing")
    wxpay = Mock()
    wxpay.query_refund = Mock(side_effect=RuntimeError("network down"))

    result = await _run(_poll_processing_refunds_impl, db, monkeypatch, wxpay)

    assert result["errors"] == 1
    await db.refresh(order)
    await db.refresh(rec)
    assert order.status == "refunding"
    assert rec.status == "processing"
