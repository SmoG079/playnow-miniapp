"""Admission and tournament funds. Lock tournament before touching registrations/orders."""

import asyncio
import json
import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select
from app.api.deps import _v
from app.core.config import get_settings
from app.core.logger import get_logger
from app.core.wechat_pay import get_wxpay, build_jsapi_params
from app.models.models import (
    Tournament,
    TournamentRegistration,
    TournamentRegStatus,
    BookingOrder,
    OrderStatus,
    RefundRecord,
    TournamentAudit,
    Notification,
    NotificationType,
    User,
)
from app.schemas.tournament import TournamentConfig
from app.services.settlement import _to_cents
from app.services import tournament_entries as entries

logger = get_logger(__name__)


def now():
    return datetime.utcnow()


def audit(db, t, user, action, detail):
    db.add(
        TournamentAudit(
            tournament_id=t.id,
            actor_id=user.id if user else None,
            action=action,
            detail=detail,
        )
    )
    logger.info("Tournament %s: %s", t.id, action)


async def locked_event(db, ident):
    t = (
        await db.execute(
            select(Tournament)
            .where(Tournament.id == ident)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if not t:
        raise HTTPException(404, "赛事不存在")
    return t


async def locked_order(db, ident):
    return (
        await db.execute(
            select(BookingOrder)
            .where(BookingOrder.id == ident)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()


async def registrations(db, t):
    return list(
        (
            await db.execute(
                select(TournamentRegistration)
                .where(TournamentRegistration.tournament_id == t.id)
                .order_by(TournamentRegistration.created_at, TournamentRegistration.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .all()
    )


def config(t):
    if not t.config:
        raise HTTPException(409, "请先配置赛事赛制")
    return TournamentConfig.model_validate(t.config)


def online_fee(t):
    return t.entry_fee > 0 and t.payment_method == "online"


def eligible(r):
    return (
        r.admission == "active"
        and r.approval == "approved"
        and r.payment in ("none", "offline", "paid", "verified")
        and _v(r.status) == "confirmed"
    )


def group_capacity(t, group):
    cfg = config(t) if t.config else TournamentConfig()
    if group < 0 or group > cfg.group_count:
        raise HTTPException(422, "请选择有效分组")
    if not group:
        return t.max_participants or 128
    size = 1 if cfg.discipline == "singles" else 2
    total = (t.max_participants or 128) // size
    return (total // cfg.group_count + int(group <= total % cfg.group_count)) * size


def group_available(t, r, active):
    g = r.requested_group or 0
    cap = group_capacity(t, g)
    if not g:
        return True
    peers = [p for p in active if p.id != r.id and p.requested_group == g]
    if len(peers) >= cap:
        return False
    if t.config and config(t).discipline == "mixed":
        return sum(p.gender == r.gender for p in peers) < cap // 2
    return True


async def reserve(db, t, r):
    if t.config and not r.entry_team_id:
        await entries.claim(db, t, r)
    r.admission = "active"
    if online_fee(t):
        r.payment = "pending"
        r.status = TournamentRegStatus.registered
        r.seat_expires_at = min(
            now() + timedelta(seconds=get_settings().TOURNAMENT_SEAT_TTL_SECONDS),
            t.registration_deadline or t.start_time,
        )
        o = BookingOrder(
            order_no="T" + secrets.token_hex(15),
            business_type="tournament",
            tournament_id=t.id,
            user_id=r.user_id,
            venue_id=None,
            club_id=t.club_id,
            amount=t.entry_fee,
            status=OrderStatus.pending,
        )
        db.add(o)
        await db.flush()
        r.order_id = o.id
    else:
        r.payment = "offline" if t.entry_fee > 0 else "none"
        r.status = TournamentRegStatus.confirmed
        r.seat_expires_at = None


async def refresh_admissions(db, t):
    rows = await registrations(db, t)
    current = now()
    cfg = config(t) if t.config else None
    if current >= min(t.registration_deadline or t.start_time, t.end_time):
        t.registration_closed = True
        t.roster_frozen = True
    for r in rows:
        if (
            r.admission == "active"
            and r.payment == "pending"
            and r.seat_expires_at
            and r.seat_expires_at <= current
        ):
            r.admission = "expired"
            r.status = TournamentRegStatus.cancelled
            r.invite_token = None
            await unpair(db, t, r)
            audit(db, t, None, "seat_expired", {"registration_id": r.id})
    if cfg and not t.registration_closed and _v(t.status) == "open":
        active = [
            r for r in rows if r.admission == "active" and r.approval == "approved"
        ]
        for r in rows:
            if len(active) >= t.max_participants:
                break
            if r.admission != "waitlisted" or r.approval != "approved":
                continue
            if (
                cfg.discipline == "mixed"
                and sum(p.gender == r.gender for p in active) >= t.max_participants // 2
            ):
                continue
            if not group_available(t, r, active):
                continue
            if t.config and not await entries.available(db, t, r):
                continue
            await reserve(db, t, r)
            active.append(r)
            db.add(
                Notification(
                    user_id=r.user_id,
                    type=NotificationType.tournament,
                    title="赛事候补递补",
                    content="您已获得参赛名额，" + ("请及时完成线上支付" if online_fee(t) else "请查看活动安排，费用由组织者线下收取" if t.entry_fee > 0 else "请查看活动安排"),
                    ref_id=t.id,
                    ref_type="tournament",
                )
            )
    t.current_participants = sum(eligible(r) for r in rows)
    await db.flush()
    return rows


async def admit(db, t, r):
    rows = await refresh_admissions(db, t)
    cfg = config(t) if t.config else None
    active = [
        p
        for p in rows
        if p.admission == "active" and p.approval == "approved" and p.id != r.id
    ]
    full = len(active) >= (t.max_participants or 128) or not group_available(
        t, r, active
    )
    if t.config and not await entries.available(db, t, r):
        full = True
    if cfg and cfg.discipline == "mixed":
        full = (
            full or sum(p.gender == r.gender for p in active) >= t.max_participants // 2
        )
    if full:
        if not cfg or not cfg.waitlist_enabled:
            raise HTTPException(409, "名额已满")
        r.admission = "waitlisted"
        r.payment = "none"
        r.status = TournamentRegStatus.registered
    else:
        await reserve(db, t, r)
    await db.flush()
    t.current_participants = sum(eligible(p) for p in rows if p.id != r.id) + int(
        eligible(r)
    )


async def unpair(db, t, r):
    await entries.release(db, t, r)


async def request_refund(db, order, reason):
    if not order.wx_transaction_id or order.wx_transaction_id.startswith("dev_"):
        raise HTTPException(409, "历史订单未核验真实收款，不能发起微信退款")
    record = (
        (
            await db.execute(
                select(RefundRecord).where(RefundRecord.order_id == order.id)
            )
        )
        .scalars()
        .first()
    )
    if not record:
        record = RefundRecord(
            order_id=order.id,
            out_refund_no=f"TR{order.id}",
            amount=order.amount,
            reason=reason,
            status="pending",
            retry_count=0,
            scheduled_at=now(),
        )
        db.add(record)
    elif _v(record.status) in ("abnormal", "closed"):
        raise HTTPException(409, "退款异常或已关闭，请在微信商户平台处理并核对最终结果")
    elif _v(record.status) == "failed":
        record.status = "pending"
        record.retry_count = 0
        record.scheduled_at = now()
    order.status = OrderStatus.refunding
    order.refund_amount = order.amount
    order.refund_status = record.status
    order.cancel_reason = reason
    order.cancel_time = now()
    return record


# WeChat refund rejections are surfaced to the caller instead of being queued,
# because a rejected refund must not cost the player their seat.
REFUND_REJECT_REASONS = {
    "NOT_ENOUGH": "商户号可用余额不足",
    "PARAM_ERROR": "退款参数有误",
    "ORDER_NOT_EXIST": "微信侧查无此订单",
    "INVALID_REQUEST": "退款请求无效",
    "FREQUENCY_LIMITED": "退款请求过于频繁",
    "SYSTEMERROR": "微信系统繁忙",
    "SIGN_ERROR": "微信支付签名校验失败",
    "APPID_NOT_EXIST": "AppID 配置有误",
    "MCHID_NOT_EXIST": "商户号配置有误",
    "REFUND_FEE_INVALID": "退款金额超出原订单",
}


def reject_reason(error):
    code = str(error or "").strip()
    if code in REFUND_REJECT_REASONS:
        return REFUND_REJECT_REASONS[code]
    if "Payment query does not match" in code:
        return "微信订单状态与本地记录不一致"
    if "Refund response does not match" in code:
        return "微信退款回执与本地订单不一致"
    return "微信拒绝了退款请求"


async def notify_refund_failure(db, t, order, reason):
    """Tell the organizer who could not be refunded, why, and for which order."""
    nickname = (
        await db.scalar(select(User.nickname).where(User.id == order.user_id))
        if order.user_id
        else None
    )
    db.add(
        Notification(
            user_id=t.user_id,
            type=NotificationType.tournament,
            title="退款失败",
            content=(
                f"{nickname or '参赛用户'} 退款失败：{reason}；"
                f"订单号 {order.order_no}（金额 ¥{order.amount}），请到微信商户平台核对后重试"
            ),
            ref_id=t.id,
            ref_type="tournament",
        )
    )
    logger.warning(
        "Tournament %s refund failed for order %s: %s", t.id, order.id, reason
    )


async def submit_refund(db, order, record):
    """Submit a queued refund to WeChat immediately and persist the outcome.

    Raises HTTPException(502) when WeChat rejects the request. Callers must keep
    the registration valid in that case and let the organizer resolve it.
    """
    settings = get_settings()
    if not order.wx_transaction_id or order.wx_transaction_id.startswith("dev_"):
        raise HTTPException(409, "历史订单未核验真实收款，不能发起微信退款")
    try:
        if _v(record.status) == "processing":
            response = await wx_call(
                "query_refund", out_refund_no=record.out_refund_no
            )
        else:
            paid = await wx_call("query", out_trade_no=order.order_no)
            if (
                paid.get("trade_state") != "SUCCESS"
                or paid.get("transaction_id") != order.wx_transaction_id
                or paid.get("mchid") != settings.WX_MCH_ID
                or paid.get("appid") != settings.WX_APP_ID
                or paid.get("amount", {}).get("total") != _to_cents(order.amount)
            ):
                raise RuntimeError("Payment query does not match refundable order")
            response = await wx_call(
                "refund",
                out_refund_no=record.out_refund_no,
                transaction_id=order.wx_transaction_id,
                amount={
                    "refund": _to_cents(record.amount),
                    "total": _to_cents(order.amount),
                    "currency": "CNY",
                },
                reason=record.reason,
            )
        state = response.get("status", "").lower()
        if (
            state not in ("success", "processing", "closed", "abnormal")
            or response.get("out_refund_no") != record.out_refund_no
            or response.get("out_trade_no") != order.order_no
            or response.get("amount", {}).get("refund") != _to_cents(record.amount)
        ):
            raise RuntimeError("Refund response does not match order")
    except Exception as exc:
        message = reject_reason(exc)
        if str(exc) in REFUND_REJECT_REASONS or "does not match" in str(exc):
            # WeChat answered and refused: stop retrying until an organizer acts.
            record.status = "failed"
            record.fail_reason = message
            record.retry_count = settings.REFUND_MAX_RETRIES
            record.scheduled_at = now() + timedelta(
                minutes=settings.REFUND_POLL_INTERVAL_MINUTES
            )
            order.status = OrderStatus.paid
            order.refund_status = "failed"
            order.refund_amount = None
            order.cancel_reason = None
            order.cancel_time = None
        else:
            # Ambiguous (network/timeout): the refund may still exist at WeChat,
            # so keep the queued record retryable instead of declaring failure.
            record.status = "pending"
            record.retry_count = 0
            record.fail_reason = message
            record.scheduled_at = now()
        raise HTTPException(502, f"退款失败：{message}") from exc
    payload = dict(
        response,
        refund_status=state.upper(),
        mchid=response.get("mchid", settings.WX_MCH_ID),
    )
    if _v(order.business_type) == "post":
        from app.services.post_payments import refund_callback as post_refund_callback

        await post_refund_callback(db, payload)
    else:
        await refund_callback(db, payload)
    record.scheduled_at = now() + timedelta(
        minutes=settings.REFUND_POLL_INTERVAL_MINUTES
    )
    return record


async def cancel_registration(db, t, r, reason, actor=None):
    """Cancel a registration, refunding a paid online order in the same request.

    A refund WeChat rejects aborts the cancellation: the player keeps the seat,
    the organizer is notified with the reason and order number, and the caller
    receives HTTPException(502) so the client can show the failure.
    """
    order = await locked_order(db, r.order_id) if r.order_id else None
    if order and _v(order.status) in ("paid", "refunding"):
        if not order.wx_transaction_id or order.wx_transaction_id.startswith("dev_"):
            r.payment = "unverified"
            order.refund_status = "abnormal"
            audit(
                db,
                t,
                actor,
                "refund_manual_review",
                {"order_id": order.id, "reason": "历史收款未核验"},
            )
        else:
            try:
                record = await request_refund(db, order, reason)
                await db.flush()
                await submit_refund(db, order, record)
            except HTTPException as exc:
                if exc.status_code != 502:
                    # Refund abnormal/closed: nothing can be submitted automatically.
                    order.refund_status = "abnormal"
                    audit(
                        db,
                        t,
                        actor,
                        "refund_manual_review",
                        {"order_id": order.id, "reason": exc.detail},
                    )
                else:
                    await notify_refund_failure(db, t, order, str(exc.detail))
                    audit(
                        db,
                        t,
                        actor,
                        "refund_failed",
                        {"order_id": order.id, "reason": exc.detail},
                    )
                    raise
    r.admission = "cancelled"
    r.status = TournamentRegStatus.cancelled
    r.seat_expires_at = None
    r.invite_token = None
    await unpair(db, t, r)
    audit(
        db,
        t,
        actor,
        "registration_cancelled",
        {"registration_id": r.id, "reason": reason},
    )
    await refresh_admissions(db, t)


async def wx_call(method, **kwargs):
    response = await asyncio.to_thread(getattr(get_wxpay(), method), **kwargs)
    if isinstance(response, tuple):
        status, body = response
        result = json.loads(body) if body else {}
        if status >= 300:
            raise RuntimeError(result.get("code", "WeChat API failed"))
        return result
    if not isinstance(response, dict):
        raise RuntimeError("Invalid WeChat response")
    return response


async def pay(db, t, r, user):
    if not get_settings().WX_PAY_ENABLED:
        raise HTTPException(503, "赛事线上支付尚未开放")
    await refresh_admissions(db, t)
    if (
        t.registration_closed
        or _v(t.status) != "open"
        or r.admission != "active"
        or r.approval != "approved"
        or r.payment != "pending"
    ):
        raise HTTPException(409, "当前报名不能支付")
    if not user.openid or user.openid.startswith("dev_"):
        raise HTTPException(409, "需要真实微信登录")
    order = await locked_order(db, r.order_id)
    if not order or _v(order.status) != "pending":
        raise HTTPException(409, "无待支付订单")
    expiry = r.seat_expires_at.replace(tzinfo=timezone.utc).isoformat()
    response = await wx_call(
        "pay",
        description=t.title,
        out_trade_no=order.order_no,
        amount={"total": _to_cents(order.amount), "currency": "CNY"},
        payer={"openid": user.openid},
        time_expire=expiry,
    )
    if not response.get("prepay_id"):
        raise HTTPException(502, "微信未返回预支付信息")
    return build_jsapi_params(get_wxpay(), response["prepay_id"])


async def payment_success(db, data):
    # Find immutable event identity first, then lock event -> order everywhere (including callbacks).
    ref = (
        await db.execute(
            select(BookingOrder.id, BookingOrder.tournament_id).where(
                BookingOrder.order_no == data.get("out_trade_no")
            )
        )
    ).first()
    if not ref or not ref.tournament_id:
        return {"code": "FAIL", "message": "Order not found"}
    t = await locked_event(db, ref.tournament_id)
    order = (
        await db.execute(
            select(BookingOrder)
            .where(BookingOrder.id == ref.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    settings = get_settings()
    if (
        data.get("mchid") != settings.WX_MCH_ID
        or data.get("appid") != settings.WX_APP_ID
        or data.get("amount", {}).get("total") != _to_cents(order.amount)
        or not data.get("transaction_id")
    ):
        raise HTTPException(400, "支付通知身份或金额不匹配")
    if data.get("amount", {}).get("currency", "CNY") != "CNY" or data.get(
        "transaction_id", ""
    ).startswith("dev_"):
        raise HTTPException(400, "无效支付交易")
    if _v(order.status) in ("paid", "refunding", "refunded"):
        if order.wx_transaction_id != data["transaction_id"]:
            raise HTTPException(400, "支付交易标识不匹配")
        return {"code": "SUCCESS"}
    r = (
        await db.execute(
            select(TournamentRegistration).where(
                TournamentRegistration.tournament_id == t.id,
                TournamentRegistration.user_id == order.user_id,
            )
        )
    ).scalar_one_or_none()
    order.status = OrderStatus.paid
    order.wx_transaction_id = data["transaction_id"]
    order.payment_time = now()
    from app.services.activity_wallet import capture
    await capture(db, order)
    await refresh_admissions(db, t)
    if (
        not r
        or r.order_id != order.id
        or r.admission != "active"
        or r.approval != "approved"
        or t.roster_frozen
        or _v(t.status) != "open"
    ):
        await request_refund(db, order, "名额已失效，支付原路退回")
    else:
        r.payment = "paid"
        r.status = TournamentRegStatus.confirmed
        r.seat_expires_at = None
        t.current_participants += 1
    audit(db, t, None, "payment_confirmed", {"order_id": order.id})
    return {"code": "SUCCESS"}


async def refund_callback(db, data):
    ref = (
        await db.execute(
            select(BookingOrder.id, BookingOrder.tournament_id).where(
                BookingOrder.order_no == data.get("out_trade_no")
            )
        )
    ).first()
    if not ref or not ref.tournament_id:
        return {"code": "FAIL", "message": "Order not found"}
    t = await locked_event(db, ref.tournament_id)
    order = (
        await db.execute(
            select(BookingOrder)
            .where(BookingOrder.id == ref.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    rec = (
        await db.execute(
            select(RefundRecord).where(
                RefundRecord.order_id == order.id,
                RefundRecord.out_refund_no == data.get("out_refund_no"),
            )
        )
    ).scalar_one_or_none()
    if (
        not rec
        or data.get("mchid") != get_settings().WX_MCH_ID
        or data.get("amount", {}).get("refund") != _to_cents(rec.amount)
    ):
        raise HTTPException(400, "退款通知不匹配")
    if _v(rec.status) == "success":
        return {"code": "SUCCESS"}
    state = data.get("refund_status", "").lower()
    if state not in ("success", "closed", "abnormal", "processing"):
        raise HTTPException(400, "未知退款状态")
    rec.status = state
    rec.wx_refund_id = data.get("refund_id")
    order.refund_status = state
    if state == "success":
        rec.completed_at = now()
        # A success must never keep the text of an earlier failed attempt.
        rec.fail_reason = None
        order.status = OrderStatus.refunded
        order.refund_time = now()
        if order.user_id:
            db.add(
                Notification(
                    user_id=order.user_id,
                    type=NotificationType.tournament,
                    title="退款成功",
                    content=(
                        f"你的报名费 ¥{rec.amount} 已原路退回，"
                        f"订单号 {order.order_no}"
                    ),
                    ref_id=t.id,
                    ref_type="tournament",
                )
            )
    # A failed refund never restores participation or touches venue slots.
    audit(db, t, None, "refund_updated", {"order_id": order.id, "status": state})
    return {"code": "SUCCESS"}


async def payment_closed(db, data):
    ref = (
        await db.execute(
            select(BookingOrder.id, BookingOrder.tournament_id).where(
                BookingOrder.order_no == data.get("out_trade_no")
            )
        )
    ).first()
    if not ref or not ref.tournament_id:
        return {"code": "FAIL", "message": "Order not found"}
    t = await locked_event(db, ref.tournament_id)
    order = (
        await db.execute(
            select(BookingOrder)
            .where(BookingOrder.id == ref.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    if _v(order.status) != "pending":
        return {"code": "SUCCESS"}
    for r in await registrations(db, t):
        if r.order_id == order.id and r.payment == "pending":
            r.admission = "expired"
            r.status = TournamentRegStatus.cancelled
            r.invite_token = None
            await unpair(db, t, r)
    order.status = OrderStatus.cancelled
    await refresh_admissions(db, t)
    return {"code": "SUCCESS"}
