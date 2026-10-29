"""Paid post admission: post -> order locking, real receipts and durable refunds."""
import secrets
from datetime import timedelta, timezone
from fastapi import HTTPException
from sqlalchemy import select
from app.api.deps import _v
from app.core.config import get_settings
from app.core.logger import get_logger
from app.core.wechat_pay import get_wxpay, build_jsapi_params
from app.models.models import MatchPost, MatchRegistration, BookingOrder, OrderStatus, RegistrationStatus, MatchPostStatus, RefundRecord
from app.services import tournament_lifecycle as money
from app.services.activity_visibility import post_registration_closed
from app.services.settlement import _to_cents


logger = get_logger(__name__)

def online(post):
    return bool(post.price and post.price > 0 and post.payment_method == 'online')


async def locked_post(db, ident):
    post = await db.scalar(select(MatchPost).where(MatchPost.id == ident).with_for_update().execution_options(populate_existing=True))
    if not post:
        raise HTTPException(404, '约球不存在')
    return post


async def own(db, post, user):
    reg = await db.scalar(select(MatchRegistration).where(MatchRegistration.post_id == post.id, MatchRegistration.user_id == user.id))
    if not reg:
        raise HTTPException(404, '尚未报名')
    return reg


async def refresh(db, post):
    regs = list((await db.scalars(select(MatchRegistration).where(MatchRegistration.post_id == post.id))).all())
    for r in regs:
        if r.payment == 'pending' and (post_registration_closed(post) or _v(post.status) == 'closed' or (r.seat_expires_at and r.seat_expires_at <= money.now())):
            r.status = RegistrationStatus.cancelled
            r.payment = 'expired'
            r.seat_expires_at = None
    await db.flush()
    if _v(post.status) != 'closed':
        occupied = sum(_v(r.status) == 'approved' or (r.payment == 'pending' and _v(r.status) == 'pending') for r in regs)
        post.status = MatchPostStatus.full if occupied + 1 >= post.max_players else MatchPostStatus.open
    return regs


async def start(db, post, reg):
    if not get_settings().WX_PAY_ENABLED:
        raise HTTPException(503, '线上支付尚未开放')
    reg.payment = 'pending'
    reg.status = RegistrationStatus.pending
    reg.seat_expires_at = money.now() + timedelta(seconds=get_settings().TOURNAMENT_SEAT_TTL_SECONDS)
    order = BookingOrder(order_no='P'+secrets.token_hex(15), business_type='post', post_id=post.id,
                         user_id=reg.user_id, club_id=post.club_id, amount=post.price, status=OrderStatus.pending)
    db.add(order)
    await db.flush()
    reg.order_id = order.id
    logger.info("Post %s registration %s: pending order %s", post.id, reg.id, order.id)


async def pay(db, post, reg, user):
    if not get_settings().WX_PAY_ENABLED:
        raise HTTPException(503, '线上支付尚未开放')
    await refresh(db, post)
    if not online(post) or reg.payment != 'pending' or _v(reg.status) != 'pending':
        raise HTTPException(409, '当前报名不能支付')
    if not user.openid or user.openid.startswith('dev_'):
        raise HTTPException(409, '需要真实微信登录')
    order = await money.locked_order(db, reg.order_id)
    if not order or _v(order.status) != 'pending':
        raise HTTPException(409, '无待支付订单')
    response = await money.wx_call('pay', description=post.title, out_trade_no=order.order_no,
        amount={'total':_to_cents(order.amount),'currency':'CNY'}, payer={'openid':user.openid},
        time_expire=reg.seat_expires_at.replace(tzinfo=timezone.utc).isoformat())
    if not response.get('prepay_id'):
        raise HTTPException(502, '微信未返回预支付信息')
    return build_jsapi_params(get_wxpay(), response['prepay_id'])


async def payment_success(db, data):
    ref = (await db.execute(select(BookingOrder.id, BookingOrder.post_id).where(BookingOrder.order_no == data.get('out_trade_no')))).first()
    if not ref or not ref.post_id:
        raise HTTPException(404, '约球订单不存在')
    post = await locked_post(db, ref.post_id)
    order = await money.locked_order(db, ref.id)
    settings = get_settings()
    if (data.get('mchid') != settings.WX_MCH_ID or data.get('appid') != settings.WX_APP_ID
        or data.get('amount',{}).get('total') != _to_cents(order.amount)
        or data.get('amount',{}).get('currency','CNY') != 'CNY'
        or not data.get('transaction_id') or data['transaction_id'].startswith('dev_')):
        raise HTTPException(400, '支付通知身份或金额不匹配')
    if _v(order.status) in ('paid','refunding','refunded'):
        if order.wx_transaction_id != data['transaction_id']:
            raise HTTPException(400, '支付交易标识不匹配')
        return {'code':'SUCCESS'}
    regs = await refresh(db, post)
    reg = next((r for r in regs if r.order_id == order.id), None)
    order.status = OrderStatus.paid
    order.wx_transaction_id = data['transaction_id']
    order.payment_time = money.now()
    if not reg or _v(reg.status) != 'pending' or reg.payment != 'pending' or _v(post.status) == 'closed' or post_registration_closed(post):
        await money.request_refund(db, order, '报名已失效，原路退回')
    else:
        reg.payment = 'paid'
        reg.seat_expires_at = None
        reg.status = RegistrationStatus.pending if post.approval_required else RegistrationStatus.approved
        await refresh(db, post)
    logger.info("Post %s order %s: payment confirmed, status %s", post.id, order.id, _v(order.status))
    return {'code':'SUCCESS'}


async def cancel(db, post, reg, reason):
    if reg.order_id:
        order = await money.locked_order(db, reg.order_id)
        if order and _v(order.status) == 'paid':
            await money.request_refund(db, order, reason)
    reg.status = RegistrationStatus.cancelled
    reg.seat_expires_at = None
    await db.flush()
    await refresh(db, post)


async def payment_closed(db, data):
    ref = (await db.execute(select(BookingOrder.id, BookingOrder.post_id).where(BookingOrder.order_no == data.get('out_trade_no')))).first()
    if not ref or not ref.post_id:
        return {'code':'SUCCESS'}
    post = await locked_post(db, ref.post_id)
    order = await money.locked_order(db, ref.id)
    if _v(order.status) != 'pending':
        return {'code':'SUCCESS'}
    reg = await db.scalar(select(MatchRegistration).where(MatchRegistration.order_id == order.id))
    if reg:
        reg.payment = 'expired'
        reg.status = RegistrationStatus.cancelled
        reg.seat_expires_at = None
    order.status = OrderStatus.cancelled
    await refresh(db, post)
    return {'code':'SUCCESS'}


async def refund_callback(db, data):
    # Only order/refund state is touched here, matching the generic refund worker's lock order.
    order = await db.scalar(select(BookingOrder).where(BookingOrder.order_no == data.get('out_trade_no'), BookingOrder.business_type == 'post').with_for_update().execution_options(populate_existing=True))
    if not order:
        raise HTTPException(404, '约球订单不存在')
    rec = await db.scalar(select(RefundRecord).where(RefundRecord.order_id == order.id, RefundRecord.out_refund_no == data.get('out_refund_no')).with_for_update().execution_options(populate_existing=True))
    if (not rec or data.get('amount',{}).get('refund') != _to_cents(rec.amount)
        or ('mchid' in data and data['mchid'] != get_settings().WX_MCH_ID)):
        raise HTTPException(400, '退款通知不匹配')
    if _v(rec.status) == 'success':
        return {'code':'SUCCESS'}
    state = data.get('refund_status','').lower()
    if state not in ('success','closed','abnormal','processing'):
        raise HTTPException(400, '未知退款状态')
    rec.status = order.refund_status = state
    rec.wx_refund_id = data.get('refund_id')
    order.status = OrderStatus.refunded if state == 'success' else OrderStatus.refunding
    if state == 'success':
        rec.completed_at = order.refund_time = money.now()
    return {'code':'SUCCESS'}


async def maintain(db):
    processed = errors = 0
    orders = (await db.execute(select(BookingOrder.id, BookingOrder.post_id).where(BookingOrder.business_type == 'post', BookingOrder.status == 'pending').order_by(BookingOrder.updated_at, BookingOrder.id).limit(100))).all()
    await db.rollback()
    for ident, post_id in orders:
        try:
            post = await locked_post(db, post_id)
            order = await money.locked_order(db, ident)
            if _v(order.status) != 'pending':
                await db.rollback()
                continue
            regs = await refresh(db, post)
            reg = next((r for r in regs if r.order_id == order.id), None)
            response = await money.wx_call('query', out_trade_no=order.order_no)
            state = response.get('trade_state')
            if state == 'SUCCESS':
                await payment_success(db, response)
            elif state in ('CLOSED','REVOKED') or not reg or reg.payment != 'pending' or _v(reg.status) != 'pending':
                if state not in ('CLOSED','REVOKED'):
                    await money.wx_call('close',out_trade_no=order.order_no)
                await payment_closed(db, {'out_trade_no':order.order_no})
            order.updated_at = money.now()
            await db.commit()
            processed += 1
        except Exception:
            await db.rollback()
            errors += 1
            logger.error('Post payment recovery failed: %s', ident, exc_info=True)
            from sqlalchemy import update
            await db.execute(update(BookingOrder).where(BookingOrder.id == ident).values(updated_at=money.now()))
            await db.commit()
    return {"processed": processed, "errors": errors}
