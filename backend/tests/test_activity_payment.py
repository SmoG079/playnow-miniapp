"""Channel selection and real receipt/compensation boundaries on isolated SQL."""
from datetime import datetime, timedelta
from decimal import Decimal
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from app.api.v1 import posts, tournaments
from app.core.config import get_settings
from app.models.models import User, MatchPost, MatchRegistration, BookingOrder, RefundRecord, TournamentRegistration, Tournament
from app.schemas.schemas import PostCreate, PostUpdate, RegisterPostRequest, ReviewRegistrationRequest
from app.schemas.tournament import TournamentCreate, TournamentConfig, RegistrationCommand, ReviewCommand, ReasonCommand, DrawCommand
from app.services import post_payments, tournament_lifecycle as life, payment_callback
from tests.test_tournaments import db


async def post(db, method='offline', fee=36, approval=False, capacity=3):
    owner = await db.get(User, '1')
    row = await posts.create_post(PostCreate(title='收费约球',city='上海市',preferred_date=(datetime.now()+timedelta(days=2)).date(),preferred_start='09:00',preferred_end='11:00',price=fee,payment_method=method,max_players=capacity,approval_required=approval),owner,db)
    return await db.get(MatchPost,row.id), owner


def receipt(order, **extra):
    s=get_settings()
    return dict(out_trade_no=order.order_no,mchid=s.WX_MCH_ID,appid=s.WX_APP_ID,
                transaction_id='real-post-'+str(order.id),amount={'total':int(order.amount*100)},**extra)


@pytest.mark.asyncio
@pytest.mark.parametrize('approval',[False,True])
async def test_offline_post_without_payment_switch_never_creates_order(db,monkeypatch,approval):
    monkeypatch.setattr(get_settings(),'WX_PAY_ENABLED',False)
    p,owner=await post(db,approval=approval)
    guest=await db.get(User,'2')
    r=await posts.register_post(p.id,RegisterPostRequest(),guest,db)
    assert r['payment']=='offline'
    reg=await db.scalar(select(MatchRegistration))
    assert reg.status.value==('pending' if approval else 'approved')
    if approval:
        await posts.review_registration(p.id,guest.public_id,ReviewRegistrationRequest(status='approved'),owner,db)
    assert not (await db.scalars(select(BookingOrder))).all()
    assert (await posts.get_post(p.id,db,guest)).payment_method=='offline'
    with pytest.raises(HTTPException):await posts.update_post(p.id,PostUpdate(payment_method='online'),owner,db)
    await posts.cancel_register(p.id,guest,db)
    assert not (await db.scalars(select(RefundRecord))).all()


@pytest.mark.asyncio
async def test_online_post_requires_receipt_before_success_and_refunds_once(db,monkeypatch):
    monkeypatch.setattr(get_settings(),'WX_PAY_ENABLED',True)
    p,owner=await post(db,'online')
    guest=await db.get(User,'2')
    assert (await posts.register_post(p.id,RegisterPostRequest(),guest,db))['payment']=='pending'
    reg=await db.scalar(select(MatchRegistration))
    assert reg.status.value=='pending'
    order=await db.get(BookingOrder,reg.order_id)
    assert order.amount==Decimal('36') and order.business_type=='post'
    bad=receipt(order);bad['amount']={'total':1}
    with pytest.raises(HTTPException):await payment_callback._handle_payment_success(bad,db)
    assert order.status.value=='pending'
    await payment_callback._handle_payment_success(receipt(order),db)
    await payment_callback._handle_payment_success(receipt(order),db)
    assert reg.status.value=='approved' and reg.payment=='paid'
    await posts.cancel_register(p.id,guest,db)
    await posts.cancel_register(p.id,guest,db)
    refs=(await db.scalars(select(RefundRecord))).all()
    assert len(refs)==1 and refs[0].amount==36
    await payment_callback._handle_refund_callback(dict(out_trade_no=order.order_no,out_refund_no=refs[0].out_refund_no,refund_status='SUCCESS',amount={'refund':3600}),db)
    assert order.status.value=='refunded'
    assert reg.status.value=='cancelled'


@pytest.mark.asyncio
async def test_online_post_pending_seat_expires_and_late_payment_refunds(db,monkeypatch):
    monkeypatch.setattr(get_settings(),'WX_PAY_ENABLED',True)
    p,_=await post(db,'online',capacity=2)
    guest=await db.get(User,'2')
    await posts.register_post(p.id,RegisterPostRequest(),guest,db)
    reg=await db.scalar(select(MatchRegistration));old=await db.get(BookingOrder,reg.order_id)
    with pytest.raises(HTTPException):await posts.register_post(p.id,RegisterPostRequest(),await db.get(User,'3'),db)
    reg.seat_expires_at=life.now()-timedelta(seconds=1)
    await post_payments.refresh(db,p)
    assert reg.status.value=='cancelled' and p.status.value=='open'
    await posts.register_post(p.id,RegisterPostRequest(),guest,db)
    new=reg.order_id
    await payment_callback._handle_payment_success(receipt(old),db)
    assert old.status.value=='refunding' and reg.order_id==new and reg.payment=='pending'


@pytest.mark.asyncio
async def test_online_post_review_and_host_close_refund(db,monkeypatch):
    monkeypatch.setattr(get_settings(),'WX_PAY_ENABLED',True)
    p,owner=await post(db,'online',approval=True)
    guest=await db.get(User,'2')
    await posts.register_post(p.id,RegisterPostRequest(),guest,db)
    reg=await db.scalar(select(MatchRegistration));order=await db.get(BookingOrder,reg.order_id)
    with pytest.raises(HTTPException):await posts.review_registration(p.id,guest.public_id,ReviewRegistrationRequest(status='approved'),owner,db)
    await payment_callback._handle_payment_success(receipt(order),db)
    assert reg.status.value=='pending' and reg.payment=='paid'
    await posts.review_registration(p.id,guest.public_id,ReviewRegistrationRequest(status='approved'),owner,db)
    await posts.close_post(p.id,owner,db)
    assert reg.status.value=='cancelled' and order.status.value=='refunding'


@pytest.mark.asyncio
@pytest.mark.parametrize('approval',[False,True])
async def test_offline_tournament_admission_draw_and_cancel_without_orders(db,monkeypatch,approval):
    monkeypatch.setattr(get_settings(),'WX_PAY_ENABLED',False)
    owner=await db.get(User,'1')
    req=TournamentCreate(title='线下比赛',address='网球场',start_time=life.now()+timedelta(days=2),end_time=life.now()+timedelta(days=3),max_participants=4,entry_fee=20,payment_method='offline',config=TournamentConfig(approval_required=approval))
    tid=(await tournaments.create_tournament(req,owner,db))['id']
    for uid in ('2','3','4','5'):
        await tournaments.register_tournament(tid,RegistrationCommand(),await db.get(User,uid),db)
        reg=await db.scalar(select(TournamentRegistration).where(TournamentRegistration.user_id==uid))
        if approval:await tournaments.review(tid,reg.id,ReviewCommand(approved=True,reason='通过'),owner,db)
        assert life.eligible(reg) and reg.payment=='offline' and reg.order_id is None and reg.seat_expires_at is None
    assert (await db.get(Tournament,tid)).current_participants==4
    assert not (await db.scalars(select(BookingOrder))).all()
    reg=await db.scalar(select(TournamentRegistration).where(TournamentRegistration.user_id=='5'))
    await tournaments.cancel_registration(tid,reg.id,ReasonCommand(reason='线下取消'),await db.get(User,'5'),db)
    assert not (await db.scalars(select(RefundRecord))).all()
    await tournaments.register_tournament(tid,RegistrationCommand(),await db.get(User,'5'),db)
    if approval:await tournaments.review(tid,reg.id,ReviewCommand(approved=True,reason='通过'),owner,db)
    await tournaments.close_registration(tid,owner,db)
    await tournaments.create_draw(tid,DrawCommand(expected_version=0,idempotency_key='offline-draw'),owner,db)


@pytest.mark.asyncio
async def test_online_paid_post_is_blocked_by_switch(db,monkeypatch):
    monkeypatch.setattr(get_settings(),'WX_PAY_ENABLED',False)
    p,_=await post(db,'online')
    with pytest.raises(HTTPException) as e:await posts.register_post(p.id,RegisterPostRequest(),await db.get(User,'2'),db)
    assert e.value.status_code==503


@pytest.mark.asyncio
async def test_post_prepay_amount_and_identity_and_payment_recovery(db,monkeypatch):
    from unittest.mock import AsyncMock
    monkeypatch.setattr(get_settings(),'WX_PAY_ENABLED',True)
    p,_=await post(db,'online',fee=Decimal('1.25'))
    guest=await db.get(User,'2')
    await posts.register_post(p.id,RegisterPostRequest(),guest,db)
    reg=await db.scalar(select(MatchRegistration));order=await db.get(BookingOrder,reg.order_id)
    call=AsyncMock(return_value={'prepay_id':'test-prepay'})
    monkeypatch.setattr(life,'wx_call',call)
    monkeypatch.setattr(post_payments,'get_wxpay',lambda:object())
    monkeypatch.setattr(post_payments,'build_jsapi_params',lambda _,prepay:{'package':'prepay_id='+prepay})
    assert (await post_payments.pay(db,p,reg,guest))['package']=='prepay_id=test-prepay'
    assert call.call_args.kwargs['amount']=={'total':125,'currency':'CNY'}
    assert call.call_args.kwargs['payer']=={'openid':'wx2'}
    data=receipt(order);reg_id=reg.id
    await db.commit()
    call.return_value=dict(data,trade_state='SUCCESS')
    await post_payments.maintain(db)
    stored=await db.get(MatchRegistration,reg_id)
    assert stored.payment=='paid' and stored.status.value=='approved'


@pytest.mark.asyncio
async def test_offline_tournament_waitlist_promotes_without_payment_or_expiry(db,monkeypatch):
    monkeypatch.setattr(get_settings(),'WX_PAY_ENABLED',False)
    owner=await db.get(User,'1')
    req=TournamentCreate(title='线下候补',address='网球场',start_time=life.now()+timedelta(days=2),end_time=life.now()+timedelta(days=3),max_participants=2,entry_fee=20,payment_method='offline',config=TournamentConfig(waitlist_enabled=True))
    tid=(await tournaments.create_tournament(req,owner,db))['id']
    for uid in ('2','3','4'):await tournaments.register_tournament(tid,RegistrationCommand(),await db.get(User,uid),db)
    wait=await db.scalar(select(TournamentRegistration).where(TournamentRegistration.user_id=='4'))
    first=await db.scalar(select(TournamentRegistration).where(TournamentRegistration.user_id=='2'))
    assert wait.admission=='waitlisted'
    await tournaments.cancel_registration(tid,first.id,ReasonCommand(reason='取消'),await db.get(User,'2'),db)
    assert life.eligible(wait) and wait.payment=='offline' and wait.seat_expires_at is None
    assert not (await db.scalars(select(BookingOrder))).all()
