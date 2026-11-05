"""Activity money in integer cents; refunds remain independent of payout delivery.

Locks: owner -> transfer -> orders in increasing ID order. Receipt capture only
needs its already-locked order, never locks the owner. No network before a durable
bill number has been committed. Unknown delivery results keep funds reserved.
"""
import json
import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from wechatpayv3.type import RequestType
from app.api.deps import _v
from app.core.config import get_settings
from app.core.logger import get_logger
from app.core.wechat_pay import get_wxpay, WeChatPayError
from app.models.models import User, BookingOrder, MatchPost, Tournament, RefundRecord, ActivityEarning, ActivityWithdrawal, ActivityTransfer

logger = get_logger(__name__)
TERMINAL = {'SUCCESS', 'FAIL', 'CANCELLED'}
STATES = TERMINAL | {'ACCEPTED','PROCESSING','WAIT_USER_CONFIRM','TRANSFERING','CANCELING'}
SHANGHAI = ZoneInfo('Asia/Shanghai')


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def cents(value):
    return int((Decimal(value) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def fee(gross, rate):
    return int((Decimal(gross) * Decimal(rate)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def config_ready():
    s = get_settings()
    try:
        rate_ok = Decimal('0') <= Decimal(s.ACTIVITY_PAYMENT_FEE_RATE) < Decimal('1')
    except Exception:
        rate_ok = False
    return bool(s.ACTIVITY_TRANSFER_ENABLED and s.ACTIVITY_TRANSFER_SCENE_VERIFIED and
        s.ACTIVITY_FEE_RATE_VERIFIED and s.ACTIVITY_TRANSFER_LIMITS_VERIFIED and s.WX_PAY_ENABLED and
        s.WX_MCH_ID and s.WX_APP_ID and s.ACTIVITY_TRANSFER_SCENE_ID and s.ACTIVITY_TRANSFER_REPORT_INFOS and
        10 <= s.ACTIVITY_TRANSFER_MIN_CENTS <= s.ACTIVITY_TRANSFER_MAX_CENTS <= 20000 and
        s.ACTIVITY_TRANSFER_DAILY_CENTS >= s.ACTIVITY_TRANSFER_MIN_CENTS and rate_ok)


def activity_unlock(activity, kind):
    if kind == 'post':
        if not activity.preferred_date or not activity.preferred_end: return None
        end = datetime.combine(activity.preferred_date,activity.preferred_end).replace(tzinfo=SHANGHAI).astimezone(timezone.utc).replace(tzinfo=None)
    else: end = activity.end_time
    return end + timedelta(hours=24) if end else None


async def capture(db, order):
    if order.business_type not in ('post','tournament') or not order.wx_transaction_id or order.wx_transaction_id.startswith('dev_'):
        return
    if await db.scalar(select(ActivityEarning.id).where(ActivityEarning.order_id == order.id)):
        return
    activity = await db.get(MatchPost if order.business_type == 'post' else Tournament, order.post_id if order.business_type == 'post' else order.tournament_id)
    if activity:
        db.add(ActivityEarning(order_id=order.id, owner_id=activity.user_id, unlock_at=activity_unlock(activity, order.business_type)))
        await db.flush()


def split(amount, minimum, maximum):
    if amount < minimum:
        return []
    parts = []
    while amount > maximum:
        piece = maximum if amount - maximum >= minimum else amount - minimum
        parts.append(piece)
        amount -= piece
    parts.append(amount)
    return parts


async def snapshot(db, owner_id, lock=False):
    query = select(ActivityEarning, BookingOrder).join(BookingOrder, BookingOrder.id == ActivityEarning.order_id).where(ActivityEarning.owner_id == owner_id).order_by(BookingOrder.id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    rows = (await db.execute(query)).all()
    withdrawal_query = select(ActivityWithdrawal).where(ActivityWithdrawal.owner_id == owner_id).order_by(ActivityWithdrawal.id)
    bill_query = select(ActivityTransfer).join(ActivityWithdrawal).where(ActivityWithdrawal.owner_id == owner_id).order_by(ActivityTransfer.id)
    if lock:
        # MySQL REPEATABLE READ may already have a snapshot from auth. Every
        # balance input must be a current locking read after the owner mutex.
        withdrawal_query = withdrawal_query.with_for_update().execution_options(populate_existing=True)
        bill_query = bill_query.with_for_update().execution_options(populate_existing=True)
    withdrawals = (await db.scalars(withdrawal_query)).all()
    bills = (await db.scalars(bill_query)).all()
    used = {}; paid = 0; pending = 0
    for w in withdrawals:
        consumed = sum(b.amount_cents for b in bills if b.withdrawal_id == w.id and b.state not in ('FAIL','CANCELLED'))
        for allocation in w.allocations:
            take = min(consumed, allocation['amount_cents'])
            used[allocation['earning_id']] = used.get(allocation['earning_id'], 0) + take
            consumed -= take
    for b in bills:
        if b.state == 'SUCCESS': paid += b.amount_cents
        elif b.state not in ('FAIL','CANCELLED'): pending += b.amount_cents
    items = []; s = get_settings(); current = now()
    for earning, order in rows:
        activity = await db.get(MatchPost if order.business_type == 'post' else Tournament, order.post_id if order.business_type == 'post' else order.tournament_id)
        if not activity: continue
        current_unlock = activity_unlock(activity,order.business_type)
        # Never unlock earlier by shortening the activity after receiving money.
        unlock = max(earning.unlock_at,current_unlock) if earning.unlock_at and current_unlock else None
        if earning.id in s.ACTIVITY_TRANSFER_EARLY_UNLOCK_EARNING_IDS:
            unlock = earning.created_at
        end = current_unlock - timedelta(hours=24) if current_unlock else None
        gross = cents(order.amount)
        rate = earning.fee_rate or s.ACTIVITY_PAYMENT_FEE_RATE
        estimated_fee = fee(gross, rate)
        refunded = _v(order.status) in ('refunding','refunded') or bool(await db.scalar(select(RefundRecord.id).where(RefundRecord.order_id == order.id)))
        real = bool(order.wx_transaction_id and not order.wx_transaction_id.startswith('dev_'))
        eligible = real and not refunded and _v(order.status) in ('paid','completed')
        net = max(0, gross - estimated_fee) if eligible else 0
        available = net if unlock and current >= unlock else 0
        consumed = used.get(earning.id, 0)
        items.append(dict(earning_id=earning.id, order_id=order.id, activity_id=activity.id, kind=order.business_type,
            club_id=activity.club_id, title=activity.title, date=end.replace(tzinfo=timezone.utc).astimezone(SHANGHAI).date().isoformat() if end else None,
            gross_cents=gross, fee_cents=estimated_fee, rate=rate, refund_cents=gross if refunded else 0,
            locked_cents=net if not unlock or current < unlock else 0, available_cents=available-consumed,
            used_cents=consumed, unlock_at=unlock.isoformat()+'Z' if unlock else None))
    return items, bills, paid, pending


async def overview(db, owner_id, start=None, end=None, club_id=None):
    items, bills, paid, pending = await snapshot(db, owner_id)
    account_available = sum(i['available_cents'] for i in items)
    selected = [i for i in items if (not club_id or i['club_id'] == club_id) and (not start or i['date'] and i['date'] >= start.isoformat()) and (not end or i['date'] and i['date'] <= end.isoformat())]
    activities = {}
    for i in selected:
        key = (i['kind'], i['activity_id'])
        group = activities.setdefault(key, dict(activity_id=i['activity_id'], kind=i['kind'], title=i['title'], date=i['date'], gross_cents=0, fee_cents=0, refund_cents=0, locked_cents=0, available_cents=0, count=0, unlock_at=i['unlock_at']))
        for field in ('gross_cents','fee_cents','refund_cents','locked_cents','available_cents'): group[field] += i[field]
        group['count'] += 1
    s = get_settings()
    return dict(activities=sorted(activities.values(), key=lambda i:i['activity_id'], reverse=True),
        available_cents=max(0,account_available), debt_cents=max(0,-account_available), paid_cents=paid, pending_cents=pending,
        gross_cents=sum(i['gross_cents'] for i in selected), refund_cents=sum(i['refund_cents'] for i in selected),
        fee_cents=sum(i['fee_cents'] for i in selected if not i['refund_cents']), locked_cents=sum(i['locked_cents'] for i in selected),
        platform_fee_cents=0, fee_rate=s.ACTIVITY_PAYMENT_FEE_RATE, fee_verified=s.ACTIVITY_FEE_RATE_VERIFIED,
        enabled=config_ready(), disabled_reason='' if config_ready() else '活动提现暂未开放，请稍后再试',
        minimum_cents=s.ACTIVITY_TRANSFER_MIN_CENTS, maximum_cents=s.ACTIVITY_TRANSFER_MAX_CENTS, daily_limit_cents=s.ACTIVITY_TRANSFER_DAILY_CENTS,
        transfers=[dict(id=b.id, amount_cents=b.amount_cents, state=b.state, created_at=b.created_at.isoformat()+'Z', error_code=b.error_code) for b in reversed(bills)])


async def reserve(db, user, request_key, activity_ids=None):
    await db.scalar(select(User).where(User.id == user.id).with_for_update())
    existing = await db.scalar(select(ActivityWithdrawal).where(ActivityWithdrawal.owner_id == user.id, ActivityWithdrawal.request_key == request_key).with_for_update())
    if existing:
        return existing
    if not config_ready(): raise HTTPException(503, '活动提现暂未开放，请稍后再试')
    if not user.openid or user.openid.startswith('dev_'): raise HTTPException(409, '请使用真实微信账号登录')
    items, bills, _, _ = await snapshot(db, user.id, lock=True)
    if sum(i['available_cents'] for i in items) < get_settings().ACTIVITY_TRANSFER_MIN_CENTS:
        raise HTTPException(409, '可提现余额不足或存在待抵扣金额')
    # New unlocked receipts offset refunded payouts before another transfer.
    current_day = now().replace(tzinfo=timezone.utc).astimezone(SHANGHAI).date()
    quota_used = sum(b.amount_cents for b in bills if b.state not in ('SUCCESS','FAIL','CANCELLED') or b.state == 'SUCCESS' and b.completed_at and b.completed_at.replace(tzinfo=timezone.utc).astimezone(SHANGHAI).date() == current_day)
    s = get_settings(); remaining = max(0,s.ACTIVITY_TRANSFER_DAILY_CENTS-quota_used)
    selected = [i for i in items if i['available_cents'] > 0 and (not activity_ids or i['activity_id'] in activity_ids)]
    amount = min(remaining, sum(i['available_cents'] for i in selected), sum(i['available_cents'] for i in items))
    parts = split(amount,s.ACTIVITY_TRANSFER_MIN_CENTS,s.ACTIVITY_TRANSFER_MAX_CENTS)
    if not parts: raise HTTPException(409, '今日额度已用完或金额不足最低提现额')
    if len(parts) > 100: raise HTTPException(409, '单次最多申请100笔，请分批提现')
    allocations = []; left = amount
    for item in selected:
        take = min(left,item['available_cents'])
        if not take: break
        earning = await db.get(ActivityEarning,item['earning_id'])
        earning.fee_rate = item['rate']
        allocations.append(dict(earning_id=earning.id,order_id=item['order_id'],amount_cents=take,fee_rate=item['rate'],order_fee_cents=item['fee_cents']))
        left -= take
    withdrawal = ActivityWithdrawal(owner_id=user.id,request_key=request_key,allocations=allocations)
    db.add(withdrawal); await db.flush()
    for part in parts:
        no = 'AW'+secrets.token_hex(15)
        payload = dict(appid=s.WX_APP_ID,out_bill_no=no,transfer_scene_id=s.ACTIVITY_TRANSFER_SCENE_ID,openid=user.openid,
            transfer_amount=part,transfer_remark='活动奖励',transfer_scene_report_infos=s.ACTIVITY_TRANSFER_REPORT_INFOS)
        if s.ACTIVITY_TRANSFER_NOTIFY_URL: payload['notify_url'] = s.ACTIVITY_TRANSFER_NOTIFY_URL
        payload['_mchid'] = s.WX_MCH_ID
        db.add(ActivityTransfer(withdrawal_id=withdrawal.id,out_bill_no=no,amount_cents=part,request_payload=payload,state='NEW'))
    await db.flush()
    logger.info('Activity withdrawal %s reserved for owner, amount cents=%s',withdrawal.id,amount)
    return withdrawal


async def wx_call(method, path, payload=None):
    def call():
        client = get_wxpay()
        status, body = client._core.request(path=path,method=RequestType.POST if method == 'POST' else RequestType.GET,data=payload)
        parsed = json.loads(body) if body else {}
        if status >= 300: raise WeChatPayError(status,parsed)
        return parsed
    return await run_in_threadpool(call)


def apply_result(bill, data):
    if data.get('out_bill_no') != bill.out_bill_no or data.get('state') not in STATES:
        raise HTTPException(502, '微信转账单响应不匹配')
    for key, expected in (('transfer_amount',bill.amount_cents),('openid',bill.request_payload['openid']),('mchid',bill.request_payload['_mchid'])):
        if key in data and data[key] != expected: raise HTTPException(502,'微信转账身份或金额不匹配')
    if bill.state in TERMINAL: return
    bill.state = data['state']; bill.transfer_bill_no = data.get('transfer_bill_no') or bill.transfer_bill_no
    bill.package_info = data.get('package_info') or bill.package_info
    bill.error_code = data.get('fail_reason','')[:64] or None
    bill.updated_at = now()
    if bill.state in TERMINAL: bill.completed_at = now()


async def sync_bill(db, owner_id, bill_id):
    await db.scalar(select(User).where(User.id == owner_id).with_for_update())
    bill = await db.scalar(select(ActivityTransfer).join(ActivityWithdrawal).where(ActivityTransfer.id == bill_id,ActivityWithdrawal.owner_id == owner_id).with_for_update().execution_options(populate_existing=True))
    if not bill: raise HTTPException(404,'提现记录不存在')
    if bill.state in TERMINAL: return bill
    s = get_settings()
    if bill.request_payload['_mchid'] != s.WX_MCH_ID or bill.request_payload['appid'] != s.WX_APP_ID:
        raise HTTPException(409,'商户配置已变化，请联系平台核对原单')
    if bill.state == 'NEW':
        if not config_ready(): return bill
        items, _, _, _ = await snapshot(db,owner_id,lock=True)
        # Do not initiate transfers after a refund or changed unlock time invalidated their backing.
        if sum(i['available_cents'] for i in items) < 0:
            bill.state='CANCELLED'; bill.completed_at=now(); bill.error_code='SOURCE_UNAVAILABLE'
            await db.commit(); return bill
        bill.state='SUBMITTING'
        await db.commit()  # Persist the bill number before any request can reach WeChat.
        return await sync_bill(db,owner_id,bill_id)
    try:
        try:
            result = await wx_call('GET','/v3/fund-app/mch-transfer/transfer-bills/out-bill-no/'+bill.out_bill_no)
        except WeChatPayError as exc:
            if exc.status != 404 or exc.payload.get('code') not in ('NOT_FOUND','RESOURCE_NOT_EXISTS') or bill.state != 'SUBMITTING' or not config_ready(): raise
            items, _, _, _ = await snapshot(db,owner_id,lock=True)
            if sum(i['available_cents'] for i in items) < 0:
                bill.state='CANCELLED'; bill.completed_at=now(); bill.error_code='SOURCE_UNAVAILABLE'
                await db.commit(); return bill
            payload = {k:v for k,v in bill.request_payload.items() if not k.startswith('_')}
            result = await wx_call('POST','/v3/fund-app/mch-transfer/transfer-bills',payload)
        apply_result(bill,result)
    except Exception:
        bill.error_code='QUERY_REQUIRED'; bill.updated_at=now()
        logger.error('Activity transfer %s requires reconciliation',bill.id,exc_info=True)
    await db.commit()
    return bill


async def maintain(db):
    rows = (await db.execute(select(ActivityTransfer.id,ActivityWithdrawal.owner_id).join(ActivityWithdrawal).where(ActivityTransfer.state.not_in(TERMINAL)).order_by(ActivityTransfer.updated_at,ActivityTransfer.id).limit(100))).all()
    await db.rollback()
    for ident,owner in rows:
        try: await sync_bill(db,owner,ident)
        except Exception:
            await db.rollback(); logger.error('Activity transfer recovery %s failed',ident,exc_info=True)
    return {'processed':len(rows)}
