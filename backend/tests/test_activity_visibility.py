from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
import pytest
from sqlalchemy import select
from fastapi import HTTPException
from app.models.models import Activity, MatchPost, MatchRegistration, RegistrationStatus, User, Tournament
from app.api.v1 import posts, tournaments, users
from app.schemas.schemas import RegisterPostRequest
from app.schemas.tournament import RegistrationCommand
from tests.test_tournaments import db, event
from tests.test_discovery import listing


@pytest.mark.asyncio
async def test_post_cutoff_filtered_before_pagination_and_retained_for_both_users(db):
    local=datetime.now(ZoneInfo('Asia/Shanghai'))
    for i in range(4):
        db.add(Activity(id=800+i,kind='post'))
    await db.flush()
    ended=MatchPost(id=800,user_id='2',title='已截止',city='南京市',preferred_date=local.date()-timedelta(days=1),preferred_start=time(8),preferred_end=time(10),players_needed=4,status='open')
    before=MatchPost(id=801,user_id='2',title='旧记录',city='南京市',preferred_date=local.date()-timedelta(days=2),preferred_start=time(8),preferred_end=time(10),players_needed=4,status='open')
    future=MatchPost(id=802,user_id='2',title='仍可报名',city='南京市',preferred_date=local.date()+timedelta(days=1),preferred_start=time(8),preferred_end=time(10),players_needed=4,status='open')
    full=MatchPost(id=803,user_id='2',title='满员未来活动',city='南京市',preferred_date=local.date()+timedelta(days=2),preferred_start=time(8),preferred_end=time(10),players_needed=4,status='full')
    db.add_all([ended,before,future,full]);await db.flush()
    db.add(MatchRegistration(post_id=800,user_id='3',status=RegistrationStatus.approved));await db.flush()
    result=await listing(db,city='南京市',page_size=1)
    assert result.total==2 and [p.id for p in result.items]==[802]
    assert [p.id for p in (await listing(db,city='南京市',page=2,page_size=1)).items]==[803]
    for uid,relation in [('2','published'),('3','joined')]:
        records=await users.my_activities(kind='post',relation=relation,phase='ended',keyword='',page=1,page_size=20,current_user=await db.get(User,uid),db=db)
        assert 800 in [p['id'] for p in records.items]
    assert (await db.get(MatchPost,800)).status=='open'
    with pytest.raises(HTTPException) as blocked:
        await posts.register_post(800,RegisterPostRequest(),await db.get(User,'4'),db)
    assert blocked.value.status_code==409


@pytest.mark.asyncio
async def test_tournament_waiting_ongoing_ended_and_manual_closure(db):
    tid,owner=await event(db,4)
    future=await db.get(Tournament,tid);future.city='南京市'
    await tournaments.register_tournament(tid,RegistrationCommand(),await db.get(User,'2'),db)
    future.registration_deadline=datetime.utcnow()-timedelta(seconds=1)
    await db.flush()
    args=dict(db=db,city='南京市',page=1,page_size=20,lat=None,lng=None,sort_by='date_asc')
    assert (await tournaments.list_tournaments(**args))['total']==1
    for uid,relation in [('1','published'),('2','joined')]:
        records=await users.my_activities(kind='tournament',relation=relation,phase='registration_closed',keyword='',page=1,page_size=20,current_user=await db.get(User,uid),db=db)
        item=next(p for p in records.items if p['id']==tid)
        assert item['phase']=='registration_closed' and 'archived' not in item
    assert future.status=='open'
    future.registration_deadline=datetime.utcnow()+timedelta(days=1)
    await db.flush()
    assert (await tournaments.list_tournaments(**args))['total']==1
    future.registration_closed=True;await db.flush()
    assert (await tournaments.list_tournaments(**args))['total']==1
    assert (await tournaments.list_tournaments(**args))['items'][0]['phase']=='registration_closed'
    future.start_time=datetime.utcnow()-timedelta(seconds=1);await db.flush()
    assert (await tournaments.list_tournaments(**args))['items'][0]['phase']=='ongoing'
    future.end_time=datetime.utcnow()-timedelta(seconds=1);await db.flush()
    assert (await tournaments.list_tournaments(**args))['total']==0
    ended=await users.my_activities(kind='tournament',relation='published',phase='ended',keyword='',page=1,page_size=20,current_user=owner,db=db)
    assert ended.items[0]['id']==tid


def test_exact_start_boundary_shanghai():
    from types import SimpleNamespace
    from app.services.activity_visibility import post_registration_closed
    post=SimpleNamespace(preferred_date=datetime(2026,10,13).date(),preferred_start=time(0))
    assert not post_registration_closed(post,datetime(2026,10,12,15,59,59))
    assert post_registration_closed(post,datetime(2026,10,12,16))

@pytest.mark.asyncio
async def test_public_results_refresh_only_from_published_draw(db):
    from tests.test_tournaments import register
    from app.models.models import TournamentMatch, TournamentDraw
    from app.schemas.tournament import DrawCommand, VersionCommand, ResultCommand
    tid,owner=await event(db,2)
    for uid in (2,3): await register(db,tid,uid)
    await tournaments.close_registration(tid,owner,db)
    await tournaments.create_draw(tid,DrawCommand(idempotency_key='visibility-draw',expected_version=0),owner,db)
    t=await db.get(Tournament,tid);t.city='南京市'
    args=dict(db=db,city='南京市',page=1,page_size=20,lat=None,lng=None,sort_by='date_asc')
    assert (await tournaments.list_tournaments(**args))['items'][0]['result_summary'] is None
    await tournaments.publish_draw(tid,VersionCommand(expected_version=t.draw_version),owner,db)
    d=await db.scalar(select(TournamentDraw).where(TournamentDraw.tournament_id==tid,TournamentDraw.version==t.published_version))
    m=await db.scalar(select(TournamentMatch).where(TournamentMatch.draw_id==d.id))
    # Same storage written by the administrator's result endpoint.
    m.score='6:3';m.winner_id=m.team_a_id;m.status='completed';await db.flush()
    t.start_time=datetime.utcnow()-timedelta(minutes=1);await db.flush()
    item=(await tournaments.list_tournaments(**args))['items'][0]
    assert item['phase']=='ongoing' and item['result_summary']['score']=='6:3'
    assert item['result_summary']['winner']
    m.score='6:4';await db.flush()
    assert (await tournaments.list_tournaments(**args))['items'][0]['result_summary']['score']=='6:4'
