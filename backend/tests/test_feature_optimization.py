"""Isolated regression coverage for ordered prices, prizes and draw adjustments."""
from datetime import date, time, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from app.services.price_rules import validate_rules, quote, expires_at
from app.services.pricing import slot_charge
from app.services import tournament_adjustment as adj
from app.schemas.tournament import DrawCommand, DrawAdjustCommand, VersionCommand, ResultCommand, TournamentPrize, TournamentCreate
from app.models.models import User, UserRole, ClubMember, Venue, Notification, Tournament
from app.api.v1 import tournaments as api
from app.api.v1.venues import PricePreviewRequest, price_preview_for_club
from tests.test_tournaments import db, event, register


def test_ordered_combined_recurring_prices_and_month_end():
    rules=validate_rules([
        dict(type='weekly',weekdays=[6,7],start_time='08:00',end_time='10:00',price='120'),
        dict(type='monthly',start_day=1,end_day=7,price='90'),
        dict(type='weekly',weekdays=[6,7],price='80')])
    assert quote(50,rules,date(2026,11,1),time(8))==(Decimal(120),0)
    assert quote(50,rules,date(2026,11,1),time(10))==(Decimal(90),1)
    assert quote(50,rules,date(2026,11,8),time(10))==(Decimal(80),2)
    assert quote(50,rules,date(2026,11,9),time(10))==(Decimal(50),None)
    assert quote(50,rules[::-1],date(2026,11,1),time(8))==(Decimal(80),0)
    dates=validate_rules([dict(type='date_range',start_date='2026-11-01',end_date='2026-11-07',weekdays=[6,7],price=0)])
    assert quote(50,dates,date(2026,11,7),time(8))[0]==0
    assert quote(50,dates,date(2026,11,8),time(8))[0]==50
    monthly=validate_rules([dict(type='monthly',start_day=29,end_day=31,price=100)])
    assert quote(50,monthly,date(2028,2,29),time(8))[0]==100
    assert quote(50,monthly,date(2026,2,28),time(8))[0]==50


@pytest.mark.parametrize('rule',[
    dict(type='weekly',weekdays=[],price=1),dict(type='weekly',weekdays=[8],price=1),
    dict(type='monthly',start_day=7,end_day=1,price=1),
    dict(type='daily_time',start_time='08:15',end_time='10:00',price=1),
    dict(type='daily_time',start_time='22:00',end_time='08:00',price=1),
    dict(type='weekly',weekdays=[6],price='NaN'),
    dict(type='date_range',start_date='2026-10-02',end_date='2026-10-01',price=1)])
def test_invalid_rules(rule):
    with pytest.raises(ValueError):validate_rules([rule])


def test_expiry_is_last_actual_occurrence_and_repeating_rules_remain():
    rules=validate_rules([dict(type='weekly',weekdays=[6,7],start_date='2026-10-01',end_date='2026-10-12',start_time='08:00',end_time='10:00',price=1)])
    assert expires_at(rules[0]).isoformat()=='2026-10-11T10:00:00+08:00'
    assert expires_at(dict(type='weekly',weekdays=[6,7],price=1)) is None
    assert expires_at(dict(type='date_range',start_date='2026-10-01',end_date='2026-10-12',price=1)).isoformat()=='2026-10-13T00:00:00+08:00'


def test_legacy_override_is_ignored_and_new_quote_changes():
    v=SimpleNamespace(price_per_hour=50,price_rules=[])
    s=SimpleNamespace(date=date(2026,10,12),start_time=time(8),end_time=time(8,30),price_override=999)
    assert slot_charge(v,s)==25
    v.price_rules=[dict(type='daily_time',start_time='08:00',end_time='10:00',price=80)]
    assert slot_charge(v,s)==40


@pytest.mark.asyncio
async def test_unsaved_preview_uses_same_quote_without_persisting(db):
    req=PricePreviewRequest(price_per_hour=50,date=date(2026,11,1),price_rules=[dict(type='weekly',weekdays=[7],price=80)])
    result=await price_preview_for_club(db,1,req)
    assert result['slots'][0]['price']==40
    assert result['slots'][0]['rule_index']==0
    assert not (await db.scalars(select(Venue))).all()


@pytest.mark.asyncio
async def test_expiry_removal_notifies_once(db):
    from app.tasks.runtime import task_session_factory
    from app.tasks.tasks import _expire_price_rules_impl
    from contextlib import asynccontextmanager
    db.add(ClubMember(club_id=1,user_id='2'))
    db.add(Venue(id=1,club_id=1,name='一号场',sport_type='tennis',price_per_hour=50,price_rules=[
        dict(type='date_range',start_date='2020-01-01',end_date='2020-01-02',price=100),
        dict(type='weekly',weekdays=[6,7],price=80)]))
    await db.commit()
    @asynccontextmanager
    async def session():yield db
    token=task_session_factory.set(session)
    try:
        assert await _expire_price_rules_impl()==1
        assert await _expire_price_rules_impl()==0
        assert len((await db.scalars(select(Notification))).all())==1
        assert len((await db.get(Venue,1)).price_rules)==1
    finally:task_session_factory.reset(token)


@pytest.mark.parametrize('discipline', ['singles','doubles','mixed'])
@pytest.mark.asyncio
async def test_adjust_draw_keeps_teams_public_version_and_idempotence(db,discipline):
    from app.schemas.tournament import TournamentConfig
    people=4 if discipline=='singles' else 8
    tid,admin=await event(db,people,TournamentConfig(discipline=discipline, pairing="random" if discipline != "singles" else None))
    for uid in range(2,people+2):await register(db,tid,uid,gender='male' if uid%2==0 else 'female')
    await api.close_registration(tid,admin,db)
    await api.create_draw(tid,DrawCommand(expected_version=0,idempotency_key='first-draw'),admin,db)
    await api.publish_draw(tid,VersionCommand(expected_version=1),admin,db)
    before=await api.get_tournament(tid,admin,db)
    assert before['can_adjust_draw']
    positions=[dict(s) for s in before['draw_positions']]
    positions[0]['team_id'],positions[1]['team_id']=positions[1]['team_id'],positions[0]['team_id']
    req=DrawAdjustCommand(expected_version=1,idempotency_key='manual-adjust',reason='调整对位',positions=positions)
    assert (await api.adjust_draw(tid,req,admin,db))['version']==2
    assert (await api.adjust_draw(tid,req,admin,db))==dict(version=2)
    after=await api.get_tournament(tid,admin,db)
    assert sorted(tuple(t['user_ids']) for t in before['teams'])==sorted(tuple(t['user_ids']) for t in after['teams'])
    assert not after['draw_published']
    assert (await api.get_tournament(tid,None,db))['draw_version']==1
    with pytest.raises(HTTPException) as stale:
        await api.adjust_draw(tid,req.model_copy(update={'idempotency_key':'another-adjust'}),admin,db)
    assert stale.value.status_code==409
    await api.publish_draw(tid,VersionCommand(expected_version=2),admin,db)
    m=next(m for m in after['matches'] if m['status']=='pending' and m['team_a_id'] and m['team_b_id'])
    await api.record_result(tid,m['id'],ResultCommand(expected_version=2,winner_id=m['team_a_id'],score='6:4'),admin,db)
    assert not (await api.get_tournament(tid,admin,db))['can_adjust_draw']
    with pytest.raises(HTTPException):
        await api.adjust_draw(tid,req.model_copy(update={'expected_version':2,'idempotency_key':'played-adjust'}),admin,db)


@pytest.mark.asyncio
async def test_creator_does_not_gain_adjust_permission(db):
    tid,admin=await event(db,4)
    for uid in range(2,6):await register(db,tid,uid)
    await api.close_registration(tid,admin,db)
    await api.create_draw(tid,DrawCommand(expected_version=0,idempotency_key='initial-draw'),admin,db)
    detail=await api.get_tournament(tid,admin,db)
    admin.role=UserRole.user
    assert (await api.get_tournament(tid,admin,db))['can_manage']
    assert not (await api.get_tournament(tid,admin,db))['can_adjust_draw']
    req=DrawAdjustCommand(expected_version=1,idempotency_key='denied-adjust',reason='测试',positions=detail['draw_positions'])
    with pytest.raises(HTTPException) as denied:await api.adjust_draw(tid,req,admin,db)
    assert denied.value.status_code==403


def test_cross_group_and_bye_validation():
    original=[dict(group_no=g,position=i,team_id=(g-1)*2+i+1) for g in (1,2) for i in range(2)]
    proposed=[dict(s) for s in original]
    proposed[0]['team_id'],proposed[2]['team_id']=proposed[2]['team_id'],proposed[0]['team_id']
    assert adj.validate_positions(original,proposed,True)==proposed
    proposed[0]['team_id']=proposed[1]['team_id']
    with pytest.raises(ValueError):adj.validate_positions(original,proposed,True)
    bye=[dict(group_no=1,position=i,team_id=v) for i,v in enumerate([1,None,2,None])]
    bad=[dict(s,team_id=v) for s,v in zip(bye,[1,2,None,None])]
    with pytest.raises(ValueError):adj.validate_positions(bye,bad,True)


def test_optional_structured_prizes_and_validation():
    with pytest.raises(ValueError):TournamentPrize(name=' ',description='奖励')
    with pytest.raises(ValueError):TournamentPrize(name='冠军',description='x'*2001)
    assert TournamentPrize(name=' 冠军 ',description='奖杯\n奖金').name=='冠军'


@pytest.mark.asyncio
async def test_structured_prize_persistence_and_clear(db):
    tid,admin=await event(db)
    t=await db.get(Tournament,tid)
    t.prizes=[dict(name='冠军',description='奖杯\n奖金')]
    await db.flush()
    assert (await api.get_tournament(tid,None,db))['prizes'][0]['description']=='奖杯\n奖金'
    t.prizes=[]
    await db.flush()
    assert (await api.get_tournament(tid,None,db))['prizes']==[]


@pytest.mark.parametrize('count',[3,4,5,6])
def test_new_round_robin_persists_actual_draw_order(count):
    from app.services import tournament_engine as engine
    ids=list(range(count,0,-1))
    matches=engine.round_robin(ids,1)
    positions=adj.initial_positions([ids],matches)
    assert [s['team_id'] for s in positions]==ids
    rebuilt=adj.rebuild(matches,positions,{i:i for i in ids},False)
    assert [(m['team_a_id'],m['team_b_id']) for m in rebuilt]==[(m['team_a_id'],m['team_b_id']) for m in matches]


@pytest.mark.asyncio
async def test_insufficient_roster_reports_draw_reason_before_request(db):
    tid,admin=await event(db,4)
    await register(db,tid,2)
    await api.close_registration(tid,admin,db)
    detail=await api.get_tournament(tid,admin,db)
    assert '每组至少需要两支已完成报名的队伍' in detail['draw_block_reason']
    assert not detail['can_adjust_draw']
    assert detail['draw_version']==0
    assert (await api.get_tournament(tid,None,db))['draw_block_reason']==''


@pytest.mark.asyncio
async def test_reopen_before_draw_recovers_insufficient_frozen_roster(db):
    tid,admin=await event(db,4)
    await register(db,tid,2)
    await api.close_registration(tid,admin,db)
    await api.reopen_registration(tid,admin,db)
    assert not (await db.get(Tournament,tid)).roster_frozen
    await register(db,tid,3)
    await api.close_registration(tid,admin,db)
    assert (await api.get_tournament(tid,admin,db))['draw_block_reason']==''
    await api.create_draw(tid,DrawCommand(expected_version=0,idempotency_key='recovered-roster'),admin,db)
    with pytest.raises(HTTPException) as denied:await api.reopen_registration(tid,admin,db)
    assert denied.value.status_code==409


@pytest.mark.asyncio
async def test_reopen_refuses_deadline_and_other_users(db):
    tid,admin=await event(db,4)
    await api.close_registration(tid,admin,db)
    with pytest.raises(HTTPException) as denied:await api.reopen_registration(tid,await db.get(User,2),db)
    assert denied.value.status_code==403
    t=await db.get(Tournament,tid)
    t.registration_deadline=datetime.utcnow()-timedelta(minutes=1)
    with pytest.raises(HTTPException) as closed:await api.reopen_registration(tid,admin,db)
    assert closed.value.status_code==409


@pytest.mark.asyncio
async def test_full_update_without_prizes_clears_awards(db):
    tid,admin=await event(db,4)
    t=await db.get(Tournament,tid)
    t.prizes=[dict(name='冠军',description='奖杯\n奖金')]
    req=TournamentCreate(club_id=t.club_id,title=t.title,address=t.address,start_time=t.start_time,end_time=t.end_time,
        max_participants=4)
    await api.apply_request(db,t,req)
    assert t.prizes==[]
    await api.apply_request(db,t,req.model_copy(update={'prizes':[]}))
    assert t.prizes==[]
