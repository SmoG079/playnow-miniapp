"""Real SQL assertions for provenance, durable bill identity, refunds and quotas."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from app.core.config import get_settings
from app.models.models import User, MatchPost, Activity, BookingOrder, OrderStatus, ActivityEarning, ActivityWithdrawal, ActivityTransfer
from app.services import activity_wallet as wallet
from app.core.wechat_pay import WeChatPayError
from tests.test_tournaments import db

@pytest.fixture
def enabled(monkeypatch):
    s=get_settings()
    for key,value in dict(ACTIVITY_TRANSFER_ENABLED=True,ACTIVITY_TRANSFER_SCENE_VERIFIED=True,ACTIVITY_FEE_RATE_VERIFIED=True,ACTIVITY_TRANSFER_LIMITS_VERIFIED=True,ACTIVITY_TRANSFER_SCENE_ID='approved',ACTIVITY_TRANSFER_REPORT_INFOS=[{'info_type':'test','info_content':'isolated'}],WX_PAY_ENABLED=True,WX_MCH_ID='test-merchant',WX_APP_ID='test-app',ACTIVITY_TRANSFER_DAILY_CENTS=100000).items():monkeypatch.setattr(s,key,value)
    return s

async def receipt(db,amount='100.00',hours=25,suffix='1',transaction='real-tx'):
    local=datetime.now(ZoneInfo('Asia/Shanghai'))-timedelta(hours=hours)
    activity=Activity(kind='post');db.add(activity);await db.flush()
    post=MatchPost(id=activity.id,user_id='1',title='活动收入',price=Decimal(amount),payment_method='online',preferred_date=local.date(),preferred_start=(local-timedelta(hours=1)).time(),preferred_end=local.time())
    db.add(post);await db.flush()
    order=BookingOrder(order_no='wallet-'+suffix,user_id='2',business_type='post',post_id=post.id,amount=Decimal(amount),status=OrderStatus.paid,wx_transaction_id=transaction)
    db.add(order);await db.flush();await wallet.capture(db,order)
    return order,post

@pytest.mark.asyncio
async def test_manual_unlock_only_selected_receipt_preserves_refunds_and_ownership(db,enabled,monkeypatch):
    order,_=await receipt(db,hours=0,suffix='manual')
    await receipt(db,hours=0,suffix='still-locked')
    earning=await db.scalar(select(ActivityEarning).where(ActivityEarning.order_id==order.id))
    monkeypatch.setattr(enabled,'ACTIVITY_TRANSFER_EARLY_UNLOCK_EARNING_IDS',[earning.id])
    data=await wallet.overview(db,'1')
    assert data['available_cents']==9940 and data['locked_cents']==9940
    assert (await wallet.overview(db,'2'))['available_cents']==0
    monkeypatch.setattr(enabled,'ACTIVITY_TRANSFER_EARLY_UNLOCK_EARNING_IDS',[])
    assert (await wallet.overview(db,'1'))['available_cents']==0
    monkeypatch.setattr(enabled,'ACTIVITY_TRANSFER_EARLY_UNLOCK_EARNING_IDS',[earning.id])
    order.status=OrderStatus.refunding
    await db.flush()
    assert (await wallet.overview(db,'1'))['available_cents']==0

@pytest.mark.asyncio
async def test_real_receipts_only_unlock_after_24_hours_and_fee_once(db,enabled,monkeypatch):
    order,post=await receipt(db,hours=23)
    await wallet.capture(db,order)
    data=await wallet.overview(db,'1')
    assert data['available_cents']==0 and data['locked_cents']==9940
    await receipt(db,transaction='dev_placeholder',suffix='dev')
    assert len((await db.scalars(select(ActivityEarning))).all())==1
    with pytest.raises(HTTPException):await wallet.reserve(db,await db.get(User,'1'),'locked-request')
    end=datetime.combine(post.preferred_date,post.preferred_end).replace(tzinfo=ZoneInfo('Asia/Shanghai')).astimezone(timezone.utc).replace(tzinfo=None)
    monkeypatch.setattr(wallet,'now',lambda:end+timedelta(hours=24))
    assert (await wallet.overview(db,'1'))['available_cents']==9940

@pytest.mark.asyncio
async def test_idempotency_failure_release_and_ownership(db,enabled):
    await receipt(db,'214.00');owner=await db.get(User,'1')
    record=await wallet.reserve(db,owner,'unique-request')
    assert (await wallet.reserve(db,owner,'unique-request')).id==record.id
    bills=(await db.scalars(select(ActivityTransfer).order_by(ActivityTransfer.id))).all()
    assert [b.amount_cents for b in bills]==[20000,1272]
    assert (await wallet.overview(db,'1'))['available_cents']==0
    bills[0].state='SUCCESS';bills[0].completed_at=wallet.now();bills[1].state='FAIL';await db.flush()
    summary=await wallet.overview(db,'1')
    assert summary['available_cents']==1272 and summary['paid_cents']==20000
    assert (await wallet.overview(db,'2'))['gross_cents']==0
    with pytest.raises(HTTPException) as e:await wallet.sync_bill(db,'2',bills[0].id)
    assert e.value.status_code==404

@pytest.mark.asyncio
async def test_daily_quota_includes_previous_day_pending_bills(db,enabled,monkeypatch):
    monkeypatch.setattr(enabled,'ACTIVITY_TRANSFER_DAILY_CENTS',20000)
    await receipt(db,'500.00');owner=await db.get(User,'1')
    await wallet.reserve(db,owner,'first-request');bill=await db.scalar(select(ActivityTransfer))
    assert bill.amount_cents==20000
    bill.created_at=wallet.now()-timedelta(days=2);await db.flush()
    with pytest.raises(HTTPException):await wallet.reserve(db,owner,'second-request')

@pytest.mark.asyncio
async def test_refund_after_payout_is_debt_and_does_not_block_customer_refund(db,enabled):
    order,_=await receipt(db)
    await wallet.reserve(db,await db.get(User,'1'),'paid-request')
    bill=await db.scalar(select(ActivityTransfer));bill.state='SUCCESS';bill.completed_at=wallet.now()
    from app.services.tournament_lifecycle import request_refund
    await request_refund(db,order,'用户取消');await db.flush()
    summary=await wallet.overview(db,'1')
    assert summary['debt_cents']==9940 and summary['available_cents']==0
    with pytest.raises(HTTPException):await wallet.reserve(db,await db.get(User,'1'),'refund-request')

@pytest.mark.asyncio
async def test_uncertain_result_reuses_bill_and_signed_success_is_final(db,enabled,monkeypatch):
    await receipt(db);await wallet.reserve(db,await db.get(User,'1'),'network-request')
    bill=await db.scalar(select(ActivityTransfer));await db.commit()
    async def unknown(method,path,payload=None):
        if method=='GET':raise WeChatPayError(404,{'code':'NOT_FOUND'})
        raise TimeoutError('isolated timeout')
    monkeypatch.setattr(wallet,'wx_call',unknown)
    await wallet.sync_bill(db,'1',bill.id)
    assert bill.state=='SUBMITTING' and (await wallet.overview(db,'1'))['pending_cents']==9940
    number=bill.out_bill_no
    async def success(*args):return dict(out_bill_no=number,state='SUCCESS',transfer_amount=9940,openid='wx1',mchid='test-merchant')
    monkeypatch.setattr(wallet,'wx_call',success);await wallet.sync_bill(db,'1',bill.id)
    assert bill.state=='SUCCESS' and bill.out_bill_no==number
    wallet.apply_result(bill,dict(out_bill_no=number,state='PROCESSING'))
    assert bill.state=='SUCCESS' and len((await db.scalars(select(ActivityWithdrawal))).all())==1

@pytest.mark.asyncio
async def test_refund_before_submission_cancels_unsent_bill(db,enabled,monkeypatch):
    order,_=await receipt(db);await wallet.reserve(db,await db.get(User,'1'),'before-refund')
    order.status=OrderStatus.refunding;await db.commit();bill=await db.scalar(select(ActivityTransfer))
    async def forbidden(*args):raise AssertionError('Must not transfer refunded source')
    monkeypatch.setattr(wallet,'wx_call',forbidden);await wallet.sync_bill(db,'1',bill.id)
    assert bill.state=='CANCELLED'

def test_split_minimum_tail():
    assert wallet.split(20005,10,20000)==[19995,10]
    assert wallet.split(9,10,20000)==[]
    assert wallet.split(40000,10,20000)==[20000,20000]

@pytest.mark.asyncio
async def test_scene_configuration_gate(db,enabled,monkeypatch):
    await receipt(db);monkeypatch.setattr(enabled,'ACTIVITY_TRANSFER_SCENE_VERIFIED',False)
    with pytest.raises(HTTPException) as e:await wallet.reserve(db,await db.get(User,'1'),'blocked-request')
    assert e.value.status_code==503 and not (await db.scalars(select(ActivityTransfer))).all()

@pytest.mark.asyncio
async def test_paused_booking_blocks_new_orders_payments_and_direct_settlement(db,monkeypatch):
    from app.api.v1 import bookings, venues
    from app.schemas.schemas import BookingCreateRequest, VenueCreate
    from app.services.settlement import execute_settlement
    monkeypatch.setattr(get_settings(),'CLUB_BOOKING_ENABLED',False)
    owner=await db.get(User,'1')
    with pytest.raises(HTTPException) as error:
        await bookings.create_booking(BookingCreateRequest(slot_ids=[1,2]),owner,db)
    assert error.value.status_code==503
    order=BookingOrder(order_no='paused-booking',business_type='booking',user_id='1',amount=100,status=OrderStatus.pending)
    db.add(order);await db.flush()
    async def no_limit(*args,**kwargs):pass
    monkeypatch.setattr(bookings,'check_rate_limit',no_limit)
    with pytest.raises(HTTPException) as error:await bookings.pay_booking(order.id,owner,db)
    assert error.value.status_code==503 and order.status==OrderStatus.pending
    with pytest.raises(HTTPException) as error:await venues.create_venue_for_club(1,VenueCreate(name='暂停',price_per_hour=100),owner,db)
    assert error.value.status_code==503
    with pytest.raises(ValueError,match='暂未开放'):await execute_settlement(db,1)

@pytest.mark.asyncio
async def test_later_unlocked_income_offsets_refunded_payout_before_new_transfer(db,enabled):
    old,_=await receipt(db)
    await wallet.reserve(db,await db.get(User,'1'),'original-payout')
    bill=await db.scalar(select(ActivityTransfer));bill.state='SUCCESS';bill.completed_at=wallet.now()
    old.status=OrderStatus.refunding;await db.flush()
    await receipt(db,amount='200.00',suffix='new')
    assert (await wallet.overview(db,'1'))['available_cents']==9940
    second=await wallet.reserve(db,await db.get(User,'1'),'offset-request')
    new_bill=await db.scalar(select(ActivityTransfer).where(ActivityTransfer.withdrawal_id==second.id))
    assert new_bill.amount_cents==9940
    assert (await wallet.overview(db,'1'))['available_cents']==0

def test_default_limits_allow_a_5000_yuan_day_in_200_yuan_bills():
    """The organiser takes home the full ¥5000 a day, but WeChat still sees ¥200 bills."""
    from app.core.config import Settings
    fields = Settings.model_fields
    assert fields['ACTIVITY_PAYMENT_FEE_RATE'].default == '0.006'
    assert fields['ACTIVITY_TRANSFER_MAX_CENTS'].default == 20000
    assert fields['ACTIVITY_TRANSFER_DAILY_CENTS'].default == 500000
    parts = wallet.split(500000, 10, 20000)
    assert len(parts) == 25 and sum(parts) == 500000 and max(parts) == 20000
