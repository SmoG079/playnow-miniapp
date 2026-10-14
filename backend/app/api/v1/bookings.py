import json
import uuid
import time as unix_time
import logging
from datetime import datetime, timedelta, timezone, time
from zoneinfo import ZoneInfo
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.core.database import get_db
from app.services.pricing import slot_charge
from app.services.slots import validate_booking_date
from app.services.booking_locks import release_order_slots, locked_order_slots, lock_owner, expire_slot_orders
from app.core.config import get_settings
from app.core.redis import acquire_lock, release_lock, redis_client
from app.core.rate_limit import check_rate_limit
from app.core.wechat_pay import get_wxpay, build_jsapi_params
from app.api.deps import get_current_user, get_club_admin, get_platform_admin, _v
from app.models.models import (
    User, UserRole, Venue, VenueTimeSlot, BookingOrder, OrderStatus, SlotStatus,
    BookingSlot, SettlementRecord, SettlementStatus, Notification, NotificationType, Club, ClubMember,
    Tournament, TournamentRegistration, TournamentRegStatus, RefundRecord, RefundStatus, PaymentLog,
)
from app.schemas.schemas import (
    BookingCreateRequest, BookingDetail, BookingListParams,
    CancelRequest, RefundRequest, PaginatedResponse, SettlementDetail,
)
from app.services.settlement import (
    generate_settlement_out_order_no, execute_settlement, query_settlement_status,
    _to_cents,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/bookings", tags=["bookings"])
settings = get_settings()

# Timezone convention: DB timestamps and internal comparisons use UTC-naive datetimes;
# business calculations convert explicitly from local timezone when needed.


def _utc_now() -> datetime:
    """Return current time as UTC-naive datetime, consistent with DB timestamps."""
    return datetime.utcnow()


def _generate_order_no() -> str:
    return datetime.now().strftime("%Y%m%d%H%M%S") + uuid.uuid4().hex[:8].upper()


@router.post("", response_model=BookingDetail)
async def create_booking(
    req: BookingCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Lock one or more consecutive slots and create a pending booking order."""
    settings = get_settings()
    await check_rate_limit(
        f"rate:booking:{current_user.id}",
        max_requests=settings.RATE_LIMIT_BOOKING_PER_MINUTE,
        window_seconds=60,
    )

    try:
        slot_ids = req.resolved_slot_ids()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    if not slot_ids:
        raise HTTPException(status_code=422, detail="slot_ids is required")

    if len(slot_ids) > 1 and len(set(slot_ids)) != len(slot_ids):
        raise HTTPException(status_code=422, detail="Duplicate slot IDs")

    # Schedule generation also takes venue -> order -> slot locks; follow that
    # order before inserting FK-backed orders to avoid a venue/slot deadlock.
    venue_ids = (await db.execute(select(VenueTimeSlot.venue_id).where(VenueTimeSlot.id.in_(slot_ids)).distinct())).scalars().all()
    await db.execute(select(Venue).where(Venue.id.in_(venue_ids)).order_by(Venue.id)
        .with_for_update().execution_options(populate_existing=True))
    await expire_slot_orders(db, slot_ids=slot_ids)

    # Acquire DB row locks ordered by slot id to prevent deadlock
    result = await db.execute(
        select(VenueTimeSlot).where(VenueTimeSlot.id.in_(slot_ids))
        .order_by(VenueTimeSlot.id).with_for_update().execution_options(populate_existing=True)
    )
    slots = result.scalars().all()
    if len(slots) != len(slot_ids):
        raise HTTPException(status_code=404, detail="One or more slots not found")

    # Sort by start_time to validate consecutiveness and compute range
    slots = sorted(slots, key=lambda s: s.start_time)
    first_slot = slots[0]
    venue_id = first_slot.venue_id
    slot_date = first_slot.date

    tz = ZoneInfo("Asia/Shanghai")
    now_local = datetime.now(tz).replace(microsecond=0)

    # Validate all slots belong to same venue/date, are consecutive, available and not past
    for i, slot in enumerate(slots):
        if slot.venue_id != venue_id or slot.date != slot_date:
            raise HTTPException(status_code=422, detail="All slots must belong to the same venue and date")
        if i > 0 and slot.start_time != slots[i - 1].end_time:
            raise HTTPException(status_code=422, detail="Slots must be consecutive")
        slot_datetime = datetime.combine(slot.date, slot.start_time).replace(tzinfo=tz, microsecond=0)
        if now_local >= slot_datetime:
            raise HTTPException(status_code=400, detail="Slot time has already passed")
        if _v(slot.status) != "available":
            raise HTTPException(status_code=409, detail="One or more slots are not available")

    validate_booking_date(slot_date)

    # Get venue + club
    venue_result = await db.execute(select(Venue).where(Venue.id == venue_id))
    venue = venue_result.scalar_one_or_none()
    if not venue or _v(venue.status) != "active":
        raise HTTPException(status_code=400, detail="Venue not available")

    club_result = await db.execute(select(Club).where(Club.id == venue.club_id))
    club = club_result.scalar_one_or_none()
    if not club or _v(club.status) != "active" or club.approval_status != "approved":
        raise HTTPException(409, "俱乐部暂不可预订")
    opening, closing = club.opening_time or time(8), club.closing_time or time(22)
    if isinstance(opening, timedelta): opening = (datetime.min + opening).time()
    if isinstance(closing, timedelta): closing = (datetime.min + closing).time()
    if any(slot.start_time < opening or slot.end_time > closing or slot.end_time <= slot.start_time for slot in slots):
        raise HTTPException(422, "请选择俱乐部营业时间内的时段")
    duration = sum((s.end_time.hour * 60 + s.end_time.minute) - (s.start_time.hour * 60 + s.start_time.minute) for s in slots)
    if duration < 60:
        raise HTTPException(422, "至少预订连续一小时")


    # Acquire Redis locks for all slots
    acquired_lock_keys = []
    order_no = _generate_order_no()
    lock_value = lock_owner(order_no)
    try:
        for slot in slots:
            lock_key = f"slot:{slot.venue_id}:{slot.date}:{slot.start_time}"
            acquired = await acquire_lock(lock_key, lock_value, settings.BOOKING_LOCK_TTL_SECONDS)
            if not acquired:
                # Release any locks we already acquired
                for released_key in acquired_lock_keys:
                    await release_lock(released_key, lock_value)
                raise HTTPException(status_code=409, detail="One or more slots are being booked by another user")
            acquired_lock_keys.append(lock_key)

        # Mark all slots locked
        total_price = Decimal("0")
        for slot in slots:
            slot.status = SlotStatus.locked
            slot.locked_by = current_user.id
            slot.locked_at = _utc_now()
            total_price += slot_charge(venue, slot)

        if total_price > Decimal("99999999.99"):
            raise HTTPException(422, "订单金额超出允许范围")

        # Create order
        order = BookingOrder(
            order_no=order_no,
            user_id=current_user.id,
            venue_id=venue.id,
            slot_id=first_slot.id,
            slot_ids=slot_ids,
            club_id=venue.club_id,
            amount=total_price,
            status=OrderStatus.pending,
        )
        db.add(order)
        await db.flush()
        await db.refresh(order)
        for slot in slots:
            slot.booking_order_id = order.id
            db.add(BookingSlot(order_id=order.id, slot_id=slot.id, amount=slot_charge(venue, slot)))
        await db.commit()
    except HTTPException:
        for released_key in acquired_lock_keys:
            await release_lock(released_key, lock_value)
        raise
    except Exception:
        for released_key in acquired_lock_keys:
            await release_lock(released_key, lock_value)
        raise

    return BookingDetail(
        id=order.id,
        order_no=order.order_no,
        user_id=order.user_id,
        venue_id=order.venue_id,
        slot_id=order.slot_id,
        slot_ids=order.slot_ids,
        club_id=order.club_id,
        amount=order.amount,
        status=_v(order.status),
        payment_time=order.payment_time,
        wx_transaction_id=order.wx_transaction_id,
        prepay_id=order.prepay_id,
        prepay_id_created_at=order.prepay_id_created_at,
        cancel_reason=order.cancel_reason,
        cancel_time=order.cancel_time,
        created_at=order.created_at,
        venue_name=venue.name,
        club_name=club.name if club else None,
        slot_date=first_slot.date,
        slot_start=first_slot.start_time,
        slot_end=slots[-1].end_time,
        slot_datetime=datetime.combine(first_slot.date, first_slot.start_time).replace(tzinfo=ZoneInfo("Asia/Shanghai")).isoformat(),
        refund_amount=order.refund_amount,
        refund_id=order.refund_id,
        refund_time=order.refund_time,
        refund_status=order.refund_status,
    )


@router.get("/config")
async def get_booking_config():
    """Return public booking configuration (e.g. free cancellation window)."""
    # Historical environment overrides must not restore the old refund policy.
    return {"free_cancel_hours": 1}


@router.get("/{booking_id:int}", response_model=BookingDetail)
async def get_booking(
    booking_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(BookingOrder, Venue, Club)
        .join(Venue, BookingOrder.venue_id == Venue.id)
        .join(Club, BookingOrder.club_id == Club.id)
        .where(BookingOrder.id == booking_id, BookingOrder.business_type == "booking")
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Booking not found")
    order, venue, club = row

    # Load all slots for the booking to compute the full time range
    slot_ids = order.slot_ids or ([order.slot_id] if order.slot_id else [])
    slots_result = await db.execute(
        select(VenueTimeSlot).where(VenueTimeSlot.id.in_(slot_ids))
    )
    slots = sorted(slots_result.scalars().all(), key=lambda s: s.start_time)
    first_slot = slots[0] if slots else None
    last_slot = slots[-1] if slots else None

    # Check ownership or admin
    if order.user_id != current_user.id:
        role = _v(current_user.role)
        if role == "platform_admin":
            pass  # allowed
        elif role == "club_admin":
            # Verify admin manages this club
            member = await db.execute(
                select(ClubMember).where(
                    ClubMember.club_id == order.club_id,
                    ClubMember.user_id == current_user.id,
                )
            )
            if not member.scalar_one_or_none():
                raise HTTPException(status_code=403, detail="Not authorized")
        else:
            raise HTTPException(status_code=403, detail="Not authorized")

    return BookingDetail(
        id=order.id,
        order_no=order.order_no,
        user_id=order.user_id,
        venue_id=order.venue_id,
        slot_id=order.slot_id,
        slot_ids=order.slot_ids,
        club_id=order.club_id,
        amount=order.amount,
        status=_v(order.status),
        payment_time=order.payment_time,
        wx_transaction_id=order.wx_transaction_id,
        prepay_id=order.prepay_id,
        prepay_id_created_at=order.prepay_id_created_at,
        cancel_reason=order.cancel_reason,
        cancel_time=order.cancel_time,
        created_at=order.created_at,
        venue_name=venue.name,
        club_name=club.name,
        slot_date=first_slot.date if first_slot else None,
        slot_start=first_slot.start_time if first_slot else None,
        slot_end=last_slot.end_time if last_slot else None,
        slot_datetime=datetime.combine(first_slot.date, first_slot.start_time).replace(tzinfo=ZoneInfo("Asia/Shanghai")).isoformat() if first_slot else None,
        refund_amount=order.refund_amount,
        refund_id=order.refund_id,
        refund_time=order.refund_time,
        refund_status=order.refund_status,
    )


async def _wx_prepay(order: BookingOrder, user: User) -> dict:
    """Call the WeChat Pay V3 JSAPI unified order API and return the decoded body.

    ``wechatpayv3`` returns ``(http_status, body_text)``. The call is blocking, so
    it runs in a threadpool to keep the event loop free.
    """
    response = await run_in_threadpool(
        get_wxpay().pay,
        description=settings.WX_PAY_DESCRIPTION,
        out_trade_no=order.order_no,
        amount={"total": _to_cents(order.amount), "currency": "CNY"},
        payer={"openid": user.openid},
        notify_url=settings.WX_PAY_NOTIFY_URL or None,
        time_expire=(order.created_at + timedelta(seconds=settings.BOOKING_LOCK_TTL_SECONDS))
            .replace(tzinfo=timezone.utc).isoformat(),
        # 平台为收款方，本笔交易不分账（分账已暂缓，见 docs/wechat-pay-setup.md）。
        # 注意：一旦漏传这个字段，该订单将永久无法分账，事后不可补。
        settle_info={"profit_sharing": False},
    )
    status, body = response
    payload = (json.loads(body) if body else None) or {}
    if status >= 300:
        raise RuntimeError(payload.get("code") or f"WeChat Pay HTTP {status}")
    return payload


@router.post("/{booking_id:int}/pay")
async def pay_booking(
    booking_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """微信 JSAPI 统一下单：返回 wx.requestPayment 参数给小程序调起收银台。

    ``WX_PAY_ENABLED=false`` 时为占位确认（不调用微信、不产生任何真实交易），
    仅用于本地开发与 CI；生产必须是 ``true``，启动日志会打印实际状态。

    订单状态只由 ``/wx-notify`` 回调置为 ``paid`` —— 本接口绝不自行标记已支付。
    """
    await check_rate_limit(
        f"rate:pay:{current_user.id}",
        max_requests=settings.RATE_LIMIT_PAY_PER_MINUTE,
        window_seconds=60,
    )

    result = await db.execute(
        select(BookingOrder).where(BookingOrder.id == booking_id).with_for_update()
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Booking not found")

    if order.business_type == "tournament":
        raise HTTPException(status_code=409, detail="Use tournament payment/refund endpoints")

    if order.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your booking")
    if _v(order.status) == "paid":
        return {"msg": "ok", "order_no": order.order_no, "amount": str(order.amount), "already_paid": True}
    if _v(order.status) != "pending":
        raise HTTPException(status_code=400, detail="Order is not pending")

    slots = await locked_order_slots(db, order)
    now = _utc_now()
    expected_ids = order.slot_ids or ([order.slot_id] if order.slot_id else [])
    if not slots or {slot.id for slot in slots} != set(expected_ids) or order.created_at is None or now >= order.created_at + timedelta(seconds=settings.BOOKING_LOCK_TTL_SECONDS):
        raise HTTPException(409, "订单锁定已过期，请重新预订")
    for slot in slots:
        local_start = datetime.combine(slot.date, slot.start_time).replace(tzinfo=ZoneInfo("Asia/Shanghai"))
        if slot.booking_order_id != order.id or _v(slot.status) != "locked" or slot.locked_by != order.user_id or local_start <= datetime.now(ZoneInfo("Asia/Shanghai")):
            raise HTTPException(409, "订单时段已失效，请重新预订")

    if not settings.WX_PAY_ENABLED:
        # 占位确认：只用于本地开发与 CI，不产生任何真实交易（等于免费订场）。
        # 生产必须 WX_PAY_ENABLED=true，main.py 启动日志会打印实际状态。
        logger.warning(
            "booking placeholder confirmed (WX_PAY_ENABLED=false): order=%s", order.order_no
        )
        order.status = OrderStatus.paid
        order.payment_time = now
        order.wx_transaction_id = f"dev_{order.order_no}"
        for slot in slots:
            slot.status = SlotStatus.booked
            slot.locked_by = None
            slot.locked_at = None
            await release_lock(f"slot:{slot.venue_id}:{slot.date}:{slot.start_time}", lock_owner(order.order_no))
        return {"msg": "ok", "order_no": order.order_no, "amount": str(order.amount), "payment_mode": "placeholder"}

    if not current_user.openid or current_user.openid.startswith("dev_"):
        raise HTTPException(status_code=409, detail="需要真实微信登录后才能支付")

    # 复用仍在有效期内的 prepay_id，避免重复向微信下单
    prepay_id = order.prepay_id
    if (
        not prepay_id
        or order.prepay_id_created_at is None
        or now >= order.prepay_id_created_at + timedelta(seconds=settings.PREPAY_ID_TTL_SECONDS)
    ):
        # Persist the attempt before calling WeChat: even a lost prepay response
        # must remain discoverable by payment recovery after local cancellation.
        db.add(PaymentLog(order_id=order.id, type="pay", event_type="PREPAY_REQUESTED",
                          raw_data={"out_trade_no": order.order_no}))
        await db.commit()
        order = (await db.execute(select(BookingOrder).where(BookingOrder.id == booking_id)
            .with_for_update().execution_options(populate_existing=True))).scalar_one()
        if _v(order.status) != "pending":
            raise HTTPException(409, "订单状态已变化，请刷新后重试")
        try:
            payload = await _wx_prepay(order, current_user)
        except Exception as e:
            logger.error("WeChat prepay failed for %s: %s", order.order_no, e, exc_info=True)
            raise HTTPException(status_code=502, detail="微信下单失败，请稍后重试")
        prepay_id = payload.get("prepay_id")
        if not prepay_id:
            raise HTTPException(status_code=502, detail="微信未返回预支付信息")
        order.prepay_id = prepay_id
        order.prepay_id_created_at = now
        await db.commit()

    # 时段仍保持 locked：只有 /wx-notify 回调验签通过后才会转 booked 并释放锁。
    return {
        "msg": "ok",
        "order_no": order.order_no,
        "amount": str(order.amount),
        "pay_params": build_jsapi_params(get_wxpay(), prepay_id),
    }


@router.post("/{booking_id:int}/sync-payment")
async def sync_booking_payment(
    booking_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """主动查单兜底：向微信查询本单真实支付结果并同步落库。

    正常链路是微信把支付结果回调到 ``/wx-notify``。当回调链路不可达时（例如
    回调域名尚未完成备案、443 被拦截），订单会一直停在 ``pending``，尽管款项
    其实已经进入商户号。本接口让前端在收银台返回后、或用户手动刷新时主动向
    微信查单；命中 ``SUCCESS`` 即复用与回调完全相同的落库逻辑
    （``payment_callback._handle_payment_success``），从而共用同一套状态机与幂等保护。

    只读操作，绝不自行把订单标成已支付 —— 一律以微信返回的 ``trade_state`` 为准。
    """
    await check_rate_limit(
        f"rate:syncpay:{current_user.id}",
        max_requests=settings.RATE_LIMIT_SYNC_PAY_PER_MINUTE,
        window_seconds=60,
    )

    result = await db.execute(
        select(BookingOrder).where(BookingOrder.id == booking_id).with_for_update()
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Booking not found")

    if order.business_type == "tournament":
        raise HTTPException(status_code=409, detail="Use tournament payment/refund endpoints")

    if order.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your booking")

    current_status = _v(order.status)
    # 已是终态（paid/cancelled/refunding/refunded）：无需查单，直接回报（幂等）
    attempted_prepay = bool(order.prepay_id)
    if current_status == "cancelled" and not attempted_prepay:
        attempted_prepay = bool(await db.scalar(select(PaymentLog.id).where(
            PaymentLog.order_id == order.id, PaymentLog.event_type == "PREPAY_REQUESTED").limit(1)))
    if current_status != "pending" and not (current_status == "cancelled" and attempted_prepay):
        return {"msg": "ok", "order_no": order.order_no, "status": current_status}

    # 占位模式没有真实交易，查单没有意义
    if not settings.WX_PAY_ENABLED:
        return {
            "msg": "ok",
            "order_no": order.order_no,
            "status": current_status,
            "payment_mode": "placeholder",
        }

    try:
        status_code, body = await run_in_threadpool(
            get_wxpay().query, out_trade_no=order.order_no
        )
    except Exception as e:
        logger.error("WeChat order query failed for %s: %s", order.order_no, e, exc_info=True)
        raise HTTPException(status_code=502, detail="查询支付结果失败，请稍后重试")

    payload = (json.loads(body) if body else None) or {}
    if status_code >= 300:
        # 例如 ORDER_NOT_EXIST：微信侧还没有这笔支付，保持 pending，等用户继续支付
        logger.info(
            "WeChat order query non-2xx for %s: http=%s code=%s",
            order.order_no, status_code, payload.get("code"),
        )
        return {"msg": "ok", "order_no": order.order_no, "status": current_status}

    trade_state = payload.get("trade_state")
    if trade_state != "SUCCESS":
        # NOTPAY / CLOSED / PAYERROR / REVOKED 等：状态不变，由用户重试或锁定超时释放
        return {
            "msg": "ok",
            "order_no": order.order_no,
            "status": current_status,
            "trade_state": trade_state,
        }

    from app.services.payment_callback import _handle_payment_success

    if payload.get("out_trade_no") != order.order_no:
        raise HTTPException(502, "支付查询结果与本单不匹配")
    outcome = await _handle_payment_success(payload, db)
    if outcome.get("code") != "SUCCESS":
        raise HTTPException(502, "支付查询结果与本单不匹配")
    await db.commit()

    refreshed = (
        await db.execute(select(BookingOrder.status).where(BookingOrder.id == order.id))
    ).scalar_one()
    logger.info("booking payment synced via order query: order=%s", order.order_no)
    return {"msg": "ok", "order_no": order.order_no, "status": _v(refreshed)}


@router.post("/{booking_id:int}/sync-refund")
async def sync_booking_refund(
    booking_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """主动查退款兜底：向微信查询本单退款进度并同步落库。

    退款与支付共用同一个回调地址（``WX_PAY_NOTIFY_URL``），因此回调不可达
    （例如回调域名未完成 ICP 备案、443 被拦截）时，订单会一直停在 ``refunding``，
    而款项其实已经退给用户。Celery 侧已有 ``retry_failed_refunds``（每 300s）与
    ``poll_processing_refunds``（每 5min）做定时兜底，本接口提供用户/管理员可
    **即时触发**的同一个动作；命中终态时复用与回调完全相同的落库逻辑
    （``payment_callback._handle_refund_callback``），从而共用同一套状态机与幂等保护。

    只读操作，绝不自行把退款标成成功 —— 一律以微信返回的 ``status`` 为准。
    """
    await check_rate_limit(
        f"rate:syncrefund:{current_user.id}",
        max_requests=settings.RATE_LIMIT_SYNC_REFUND_PER_MINUTE,
        window_seconds=60,
    )

    result = await db.execute(
        select(BookingOrder).where(BookingOrder.id == booking_id).with_for_update()
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Booking not found")

    if order.business_type == "tournament":
        raise HTTPException(status_code=409, detail="Use tournament payment/refund endpoints")

    # 权限：订单本人 / 平台管理员 / 本俱乐部管理员（与 refund-records 接口一致）
    if order.user_id != current_user.id:
        role = _v(current_user.role)
        if role == "platform_admin":
            pass
        elif role == "club_admin":
            member = await db.execute(
                select(ClubMember).where(
                    ClubMember.club_id == order.club_id,
                    ClubMember.user_id == current_user.id,
                )
            )
            if not member.scalar_one_or_none():
                raise HTTPException(status_code=403, detail="Not authorized")
        else:
            raise HTTPException(status_code=403, detail="Not authorized")

    current_status = _v(order.status)
    current_refund_status = _v(order.refund_status)

    # 已是终态：无需查单，直接回报（幂等）
    if current_status == "refunded" or current_refund_status in ("success", "closed", "abnormal"):
        return {
            "msg": "ok",
            "order_no": order.order_no,
            "status": current_status,
            "refund_status": current_refund_status,
        }

    if not order.refund_id:
        raise HTTPException(status_code=400, detail="该订单没有退款记录")

    # 占位模式没有真实交易，查单没有意义
    if not settings.WX_PAY_ENABLED:
        return {
            "msg": "ok",
            "order_no": order.order_no,
            "status": current_status,
            "refund_status": current_refund_status,
            "payment_mode": "placeholder",
        }

    out_refund_no = order.refund_id
    try:
        status_code, body = await run_in_threadpool(
            get_wxpay().query_refund, out_refund_no=out_refund_no
        )
    except Exception as e:
        logger.error("WeChat refund query failed for %s: %s", out_refund_no, e, exc_info=True)
        raise HTTPException(status_code=502, detail="查询退款结果失败，请稍后重试")

    payload = (json.loads(body) if body else None) or {}
    if status_code >= 300:
        # 例如 RESOURCE_NOT_EXISTS：微信侧还没有这笔退款，保持现状，等定时任务重试
        logger.info(
            "WeChat refund query non-2xx for %s: http=%s code=%s",
            out_refund_no, status_code, payload.get("code"),
        )
        return {
            "msg": "ok",
            "order_no": order.order_no,
            "status": current_status,
            "refund_status": current_refund_status,
        }

    # 防错单：单号必须与本单严格对应，否则绝不落库
    if payload.get("out_refund_no") != out_refund_no or payload.get("out_trade_no") != order.order_no:
        logger.error(
            "Refund query mismatch for order %s: out_refund_no=%s out_trade_no=%s",
            order.order_no, payload.get("out_refund_no"), payload.get("out_trade_no"),
        )
        raise HTTPException(status_code=502, detail="退款查询结果与本单不匹配")

    refund_state = (payload.get("status") or "").upper()
    if refund_state in ("SUCCESS", "CLOSED", "ABNORMAL"):
        from app.services.payment_callback import _handle_refund_callback

        # query_refund 返回 status，回调处理器认 refund_status —— 映射成回调格式后
        # 复用同一落库逻辑，避免出现第三套状态机。
        await _handle_refund_callback(
            {
                "out_refund_no": out_refund_no,
                "out_trade_no": order.order_no,
                "refund_status": refund_state,
                "refund_id": payload.get("refund_id"),
                "amount": payload.get("amount") or {},
            },
            db,
        )
        await db.commit()

    refreshed = (
        await db.execute(
            select(BookingOrder.status, BookingOrder.refund_status).where(BookingOrder.id == order.id)
        )
    ).one()
    logger.info(
        "booking refund synced via refund query: order=%s state=%s",
        order.order_no, refund_state or "(unknown)",
    )
    return {
        "msg": "ok",
        "order_no": order.order_no,
        "status": _v(refreshed[0]),
        "refund_status": _v(refreshed[1]),
        "refund_state": refund_state or None,
    }


@router.post("/wx-notify")
async def wx_pay_notify(request: Request, db: AsyncSession = Depends(get_db)):
    """WeChat payment callback. Verifies and acknowledges immediately, then queues heavy processing to Celery."""
    body = await request.body()

    # P0-4: Verify/decrypt callback BEFORE parsing body or recording nonce
    try:
        wxpay = get_wxpay()
        headers_dict = dict(request.headers)
        decrypted = wxpay.decrypt_callback(headers_dict, body)
        data = json.loads(decrypted)
        envelope = json.loads(body)
        event_type = envelope.get("event_type") or data.get("event_type", "")
    except Exception as e:
        logger.error("Callback verify/decrypt failed: %s", e)
        raise HTTPException(status_code=400, detail="Invalid callback")

    # P0-6: Timestamp and nonce replay protection (after successful verification)
    timestamp = request.headers.get("Wechatpay-Timestamp")
    nonce = request.headers.get("Wechatpay-Nonce")
    now = int(unix_time.time())
    try:
        ts = int(timestamp)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid callback timestamp")
    if not timestamp or abs(now - ts) > 300:
        logger.warning("Callback timestamp invalid: timestamp=%s now=%s", timestamp, now)
        raise HTTPException(status_code=400, detail="Callback timestamp invalid")

    if not nonce:
        logger.warning("Callback missing nonce")
        raise HTTPException(status_code=400, detail="Callback nonce missing")

    # Tournament callbacks perform their short, idempotent database transition
    # before acknowledging. Refund I/O remains in the durable maintenance task.
    order = (await db.execute(select(BookingOrder).where(
        BookingOrder.order_no == data.get("out_trade_no")
    ))).scalar_one_or_none()
    if order and order.business_type == "tournament":
        from app.services import tournament_lifecycle as life
        handlers = {"TRANSACTION.SUCCESS": life.payment_success,
                    "TRANSACTION.CLOSED": life.payment_closed,
                    "REFUND.SUCCESS": life.refund_callback,
                    "REFUND.ABNORMAL": life.refund_callback,
                    "REFUND.CLOSED": life.refund_callback}
        handler = handlers.get(event_type)
        if not handler:
            raise HTTPException(400, "Unsupported tournament callback")
        if event_type == "TRANSACTION.CLOSED" and (
            data.get("mchid") != get_settings().WX_MCH_ID
            or data.get("appid") != get_settings().WX_APP_ID
        ):
            raise HTTPException(400, "Callback merchant or app mismatch")
        result = await handler(db, data)
        db.add(PaymentLog(order_id=order.id, type="callback", event_type=event_type,
                          raw_data={"event_type": event_type, "out_trade_no": order.order_no}))
        await db.commit()
        return result

    redis = redis_client
    nonce_key = f"wx:callback:nonce:{nonce}"
    # SET NX EX atomically; if key exists, SET returns None
    set_result = await redis.set(nonce_key, "1", nx=True, ex=3600)
    if set_result is None:
        logger.warning("Duplicate WeChat callback nonce: %s", nonce)
        return {"code": "SUCCESS"}

    out_trade_no = data.get("out_trade_no")

    # Log all callbacks
    result = await db.execute(
        select(BookingOrder).where(BookingOrder.order_no == out_trade_no)
    )
    order = result.scalar_one_or_none()
    log = PaymentLog(
        order_id=order.id if order else None,
        type="callback",
        event_type=event_type,
        raw_data={"event_type": event_type, "out_trade_no": out_trade_no},
    )
    db.add(log)
    await db.commit()

    # P0-5: Acknowledge SUCCESS immediately, queue heavy work to Celery
    from app.tasks.tasks import process_wx_callback
    try:
        process_wx_callback.delay(event_type, data)
    except Exception:
        await redis.delete(nonce_key)
        logger.error("Callback dispatch failed", exc_info=True)
        raise HTTPException(status_code=503, detail="Retry callback")

    return {"code": "SUCCESS"}


@router.post("/{booking_id:int}/cancel")
async def cancel_booking(
    booking_id: int,
    req: CancelRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(BookingOrder).where(BookingOrder.id == booking_id)
        .with_for_update().execution_options(populate_existing=True))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Booking not found")

    if order.business_type == "tournament":
        raise HTTPException(status_code=409, detail="Use tournament payment/refund endpoints")

    if order.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your booking")

    from app.services.booking_refunds import cancellation_deadline, queue_refund, dispatch_refund, refund_response
    if _v(order.status) in ("refunding", "refunded"):
        return refund_response(order)
    if _v(order.status) == "cancelled":
        return {"msg": "ok", "status": "cancelled"}
    if _v(order.status) not in ("pending", "paid"):
        raise HTTPException(status_code=400, detail="Cannot cancel in current status")

    if _utc_now() >= await cancellation_deadline(db, order):
        raise HTTPException(409, "预约开始前1小时内及开始后不可取消")

    if _v(order.status) == "paid" and not (order.wx_transaction_id or "").startswith("dev_"):
        await queue_refund(db, order, order.amount, req.reason or "用户自助取消，全额退款")
        return await dispatch_refund(db, order)

    order.status = OrderStatus.cancelled
    order.cancel_reason = req.reason
    order.cancel_time = _utc_now()

    await release_order_slots(db, order)

    return {"msg": "ok", "status": "cancelled"}


@router.post("/{booking_id:int}/refund")
async def refund_booking(
    booking_id: int,
    req: RefundRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Refund a paid booking order via WeChat Pay V3 (club/platform admin only)."""
    await check_rate_limit(
        f"rate:refund:{current_user.id}",
        max_requests=settings.RATE_LIMIT_REFUND_PER_MINUTE,
        window_seconds=60,
    )
    result = await db.execute(
        select(BookingOrder).where(BookingOrder.id == booking_id).with_for_update()
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Booking not found")

    if order.business_type == "tournament":
        raise HTTPException(status_code=409, detail="Use tournament payment/refund endpoints")

    # Authorization: club admin for this club or platform admin only
    role = _v(current_user.role)
    if role == "platform_admin":
        pass
    elif role == "club_admin":
        member = await db.execute(
            select(ClubMember).where(
                ClubMember.club_id == order.club_id,
                ClubMember.user_id == current_user.id,
            )
        )
        if not member.scalar_one_or_none():
            raise HTTPException(status_code=403, detail="Not authorized")
    else:
        raise HTTPException(status_code=403, detail="Not authorized")

    if _v(order.status) not in ("paid", "cancelled", "refunding", "refunded"):
        raise HTTPException(409, "Only paid orders can be refunded")
    if req.amount is not None and req.amount <= 0:
        raise HTTPException(400, "Refund amount must be greater than 0")
    refund_amount = req.amount if req.amount is not None else (order.refund_amount or order.amount)
    if refund_amount > order.amount:
        raise HTTPException(400, "Refund amount cannot exceed order amount")
    from app.services.booking_refunds import queue_refund, dispatch_refund
    await queue_refund(db, order, refund_amount, req.reason or "管理员退款", retry=True)
    return await dispatch_refund(db, order)


@router.get("/{booking_id:int}/refund-records")
async def list_refund_records(
    booking_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List refund records for a booking order."""
    result = await db.execute(
        select(BookingOrder).where(BookingOrder.id == booking_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Booking not found")

    # Authorization: booking owner, club admin for the club, or platform admin
    if order.user_id != current_user.id:
        role = _v(current_user.role)
        if role == "platform_admin":
            pass
        elif role == "club_admin":
            member = await db.execute(
                select(ClubMember).where(
                    ClubMember.club_id == order.club_id,
                    ClubMember.user_id == current_user.id,
                )
            )
            if not member.scalar_one_or_none():
                raise HTTPException(status_code=403, detail="Not authorized")
        else:
            raise HTTPException(status_code=403, detail="Not authorized")

    result = await db.execute(
        select(RefundRecord)
        .where(RefundRecord.order_id == order.id)
        .order_by(RefundRecord.created_at.desc())
    )
    records = result.scalars().all()

    return [
        {
            "id": r.id,
            "order_id": r.order_id,
            "out_refund_no": r.out_refund_no,
            "wx_refund_id": r.wx_refund_id,
            "amount": str(r.amount),
            "reason": r.reason,
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        }
        for r in records
    ]


@router.get("/club/{club_id}", response_model=PaginatedResponse)
async def club_orders(
    club_id: int,
    status: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    _: User = Depends(get_club_admin),
    db: AsyncSession = Depends(get_db),
):
    query = select(BookingOrder, Venue.name) \
        .join(Venue, BookingOrder.venue_id == Venue.id) \
        .where(BookingOrder.club_id == club_id, BookingOrder.business_type == "booking")

    count_query = select(func.count(BookingOrder.id)).where(BookingOrder.club_id == club_id, BookingOrder.business_type == "booking")

    if status:
        try:
            order_status = OrderStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid status")
        query = query.where(BookingOrder.status == order_status)
        count_query = count_query.where(BookingOrder.status == order_status)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    offset = (page - 1) * page_size
    result = await db.execute(query.order_by(BookingOrder.created_at.desc()).offset(offset).limit(page_size))
    rows = result.all()

    items = []
    for row in rows:
        order, venue_name = row
        # Load all slots for this booking to show the full consecutive range
        slot_ids = order.slot_ids or ([order.slot_id] if order.slot_id else [])
        slots_result = await db.execute(
            select(VenueTimeSlot).where(VenueTimeSlot.id.in_(slot_ids))
        )
        slots = sorted(slots_result.scalars().all(), key=lambda s: s.start_time)
        first_slot = slots[0] if slots else None
        last_slot = slots[-1] if slots else None
        slot_date = first_slot.date if first_slot else None
        slot_start = first_slot.start_time if first_slot else None
        slot_end = last_slot.end_time if last_slot else None
        slot_datetime = datetime.combine(slot_date, slot_start).replace(tzinfo=ZoneInfo("Asia/Shanghai")).isoformat() if first_slot else None
        items.append(BookingDetail(
            id=order.id, order_no=order.order_no, user_id=order.user_id,
            venue_id=order.venue_id, slot_id=order.slot_id, slot_ids=order.slot_ids,
            club_id=order.club_id,
            amount=order.amount, status=_v(order.status), payment_time=order.payment_time,
            wx_transaction_id=order.wx_transaction_id, prepay_id=order.prepay_id,
            prepay_id_created_at=order.prepay_id_created_at, cancel_reason=order.cancel_reason,
            cancel_time=order.cancel_time, created_at=order.created_at,
            venue_name=venue_name, club_name=None, slot_date=slot_date,
            slot_start=slot_start, slot_end=slot_end, slot_datetime=slot_datetime,
            refund_amount=order.refund_amount, refund_id=order.refund_id,
            refund_time=order.refund_time, refund_status=order.refund_status,
        ))

    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/settlements", response_model=PaginatedResponse)
async def list_settlements(
    status: str = Query(None),
    club_id: int = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    _: User = Depends(get_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(SettlementRecord, BookingOrder.order_no)
        .join(BookingOrder, SettlementRecord.order_id == BookingOrder.id)
        .order_by(SettlementRecord.created_at.desc())
    )
    count_stmt = (
        select(func.count(SettlementRecord.id))
        .join(BookingOrder, SettlementRecord.order_id == BookingOrder.id)
    )

    if status:
        stmt = stmt.where(SettlementRecord.status == status)
        count_stmt = count_stmt.where(SettlementRecord.status == status)
    if club_id:
        stmt = stmt.where(BookingOrder.club_id == club_id)
        count_stmt = count_stmt.where(BookingOrder.club_id == club_id)

    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    offset = (page - 1) * page_size
    result = await db.execute(stmt.offset(offset).limit(page_size))
    rows = result.all()

    items = []
    for rec, order_no in rows:
        items.append(SettlementDetail(
            id=rec.id,
            order_id=rec.order_id,
            order_no=order_no,
            total_amount=rec.total_amount,
            platform_amount=rec.platform_amount,
            club_amount=rec.club_amount,
            split_ratio=rec.split_ratio,
            status=_v(rec.status),
            wx_split_order_no=rec.wx_split_order_no,
            out_order_no=rec.out_order_no,
            retry_count=rec.retry_count,
            scheduled_at=rec.scheduled_at,
            completed_at=rec.completed_at,
            fail_reason=rec.fail_reason,
            created_at=rec.created_at,
        ))

    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("/settlements/{settlement_id}/query", response_model=SettlementDetail)
async def query_settlement(
    settlement_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_platform_admin),
):
    rec = await query_settlement_status(db, settlement_id)
    await db.commit()

    # Fetch order_no for the response
    order_result = await db.execute(
        select(BookingOrder.order_no).where(BookingOrder.id == rec.order_id)
    )
    order_no = order_result.scalar() or ""

    return SettlementDetail(
        id=rec.id,
        order_id=rec.order_id,
        order_no=order_no,
        total_amount=rec.total_amount,
        platform_amount=rec.platform_amount,
        club_amount=rec.club_amount,
        split_ratio=rec.split_ratio,
        status=_v(rec.status),
        wx_split_order_no=rec.wx_split_order_no,
        out_order_no=rec.out_order_no,
        retry_count=rec.retry_count,
        scheduled_at=rec.scheduled_at,
        completed_at=rec.completed_at,
        fail_reason=rec.fail_reason,
        created_at=rec.created_at,
    )


@router.post("/settlements/{settlement_id}/retry", response_model=SettlementDetail)
async def retry_settlement(
    settlement_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_platform_admin),
):
    rec = await db.get(SettlementRecord, settlement_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Settlement not found")
    if _v(rec.status) == "completed":
        raise HTTPException(status_code=400, detail="Settlement already completed")
    rec.status = SettlementStatus.pending
    rec.retry_count = 0
    await db.commit()
    rec = await execute_settlement(db, settlement_id)
    await db.commit()  # persist processing state / wx_split_order_no
    if _v(rec.status) == "processing":
        try:
            rec = await query_settlement_status(db, settlement_id)
            await db.commit()
        except Exception:
            logger.exception("Settlement %s query status failed during retry, but processing state is committed", settlement_id)
    await db.commit()

    # Fetch order_no for the response
    order_result = await db.execute(
        select(BookingOrder.order_no).where(BookingOrder.id == rec.order_id)
    )
    order_no = order_result.scalar() or ""

    return SettlementDetail(
        id=rec.id,
        order_id=rec.order_id,
        order_no=order_no,
        total_amount=rec.total_amount,
        platform_amount=rec.platform_amount,
        club_amount=rec.club_amount,
        split_ratio=rec.split_ratio,
        status=_v(rec.status),
        wx_split_order_no=rec.wx_split_order_no,
        out_order_no=rec.out_order_no,
        retry_count=rec.retry_count,
        scheduled_at=rec.scheduled_at,
        completed_at=rec.completed_at,
        fail_reason=rec.fail_reason,
        created_at=rec.created_at,
    )
