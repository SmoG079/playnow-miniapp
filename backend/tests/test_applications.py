"""Review ownership and pending club access using a disposable database."""
from datetime import datetime, timedelta
import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, func
from app.models.models import User, UserRole, Club, ClubMember, Activity, MatchPost, MatchRegistration, TournamentRegistration, Notification
from app.api.v1 import applications as api, clubs, tournaments, posts
from app.api.deps import get_current_user
from app.core.database import get_db
from app.schemas.schemas import ClubCreate, ReviewRegistrationRequest
from app.schemas.tournament import TournamentCreate, TournamentConfig, RegistrationCommand, ReviewCommand
from tests.test_tournaments import db

async def club_request(db):
    return await clubs.create_club(ClubCreate(name='待审核俱乐部',city='南京市',address='地图地址',latitude=32,longitude=118,contact_phone='13800138000'),await db.get(User,'2'),db)
async def inbox(db,uid='1',scope='todo',kind='all',page=1,size=20):
    return await api.list_applications(scope,kind,page,size,await db.get(User,uid),db)
async def pending_post(db):
    db.add(Activity(id=100,kind='post'));await db.flush()
    db.add(MatchPost(id=100,user_id='2',title='约球申请',players_needed=1,approval_required=True));await db.flush()
    r=MatchRegistration(post_id=100,user_id='3',message='请审核');db.add(r);await db.flush();return r

@pytest.mark.asyncio
async def test_club_approval_gates_visibility_and_permissions_and_is_not_repeatable(db):
    c=await club_request(db);user=await db.get(User,'2')
    assert c.status=='inactive' and c.approval_status=='pending' and user.role==UserRole.user
    assert await db.scalar(select(func.count(ClubMember.id)).where(ClubMember.club_id==c.id))==0
    with pytest.raises(HTTPException) as error: await clubs.get_club(c.id,db,None)
    assert error.value.status_code==404
    assert (await clubs.get_club(c.id,db,user)).id==c.id
    with pytest.raises(HTTPException): await clubs.club_venues(c.id,db)
    public=await clubs.list_clubs(None,None,None,None,None,1,20,db)
    assert c.id not in [x.id for x in public.items]
    assert (await inbox(db,'2','mine')).items[0]['status']=='pending'
    assert (await inbox(db,'2')).total==0 and (await inbox(db)).total==1
    with pytest.raises(HTTPException) as error: await api.review_club(c.id,api.ClubReview(approved=True),user,db)
    assert error.value.status_code==403
    await api.review_club(c.id,api.ClubReview(approved=True,reason='资料完整'),await db.get(User,'1'),db)
    assert user.role=='club_admin' and (await clubs.get_club(c.id,db,None)).status=='active'
    assert await db.scalar(select(func.count(ClubMember.id)).where(ClubMember.club_id==c.id))==1
    assert (await inbox(db)).total==0 and (await inbox(db,scope='done')).total==1
    with pytest.raises(HTTPException) as error: await api.review_club(c.id,api.ClubReview(approved=False,reason='重复'),await db.get(User,'1'),db)
    assert error.value.status_code==409 and user.role=='club_admin'

@pytest.mark.asyncio
async def test_rejection_records_reason_and_does_not_grant_access(db):
    c=await club_request(db)
    with pytest.raises(HTTPException) as error: await api.review_club(c.id,api.ClubReview(approved=False,reason='  '),await db.get(User,'1'),db)
    assert error.value.status_code==422
    await api.review_club(c.id,api.ClubReview(approved=False,reason='资料不全'),await db.get(User,'1'),db)
    club=await db.get(Club,c.id)
    assert club.approval_status=='rejected' and club.review_reason=='资料不全' and club.reviewed_by=='1' and club.reviewed_at
    assert (await db.get(User,'2')).role==UserRole.user
    assert (await inbox(db,'2','mine')).items[0]['reason']=='资料不全' and (await inbox(db,'3','mine')).total==0
    assert await db.scalar(select(func.count(Notification.id)).where(Notification.user_id=='2'))==1

@pytest.mark.asyncio
async def test_post_reviews_are_creator_only_and_repeated_actions_are_rejected(db):
    r=await pending_post(db)
    assert (await inbox(db)).total==0 and (await inbox(db,'2')).items[0]['kind']=='post'
    for uid in ['1','3']:
        with pytest.raises(HTTPException) as error: await api.review_application('post',r.id,api.ClubReview(approved=True),await db.get(User,uid),db)
        assert error.value.status_code==403
    await api.review_application('post',r.id,api.ClubReview(approved=True,reason='欢迎'),await db.get(User,'2'),db)
    assert r.status.value=='approved' and r.review_reason=='欢迎'
    assert (await inbox(db,'2')).total==0 and (await inbox(db,'2','done')).items[0]['reason']=='欢迎'
    with pytest.raises(HTTPException) as error: await posts.review_registration(100,(await db.get(User,'3')).public_id,ReviewRegistrationRequest(status='rejected'),await db.get(User,'2'),db)
    assert error.value.status_code==409

@pytest.mark.asyncio
async def test_tournament_review_keeps_admission_logic_and_creator_scope(db):
    creator=await db.get(User,'2')
    t=await tournaments.create_tournament(TournamentCreate(club_id=1,title='正式比赛',address='球场',start_time=datetime.utcnow()+timedelta(days=2),end_time=datetime.utcnow()+timedelta(days=3),max_participants=2,config=TournamentConfig(approval_required=True)),creator,db)
    await tournaments.register_tournament(t['id'],RegistrationCommand(),await db.get(User,'3'),db)
    r=await db.scalar(select(TournamentRegistration).where(TournamentRegistration.tournament_id==t['id']))
    assert (await inbox(db)).total==0 and (await inbox(db,'2')).items[0]['kind']=='tournament'
    with pytest.raises(HTTPException) as error: await tournaments.review(t['id'],r.id,ReviewCommand(approved=True,reason='越权'),await db.get(User,'1'),db)
    assert error.value.status_code==403
    await api.review_application('tournament',r.id,api.ClubReview(approved=True),creator,db)
    assert r.approval=='approved' and r.admission=='active'
    assert (await inbox(db,'2','done')).items[0]['status']=='approved'

@pytest.mark.asyncio
async def test_queue_pagination_and_closed_items(db):
    await pending_post(db)
    for i in range(3): await club_request(db)
    first=await inbox(db,kind='club',size=2);second=await inbox(db,kind='club',page=2,size=2)
    assert first.total==second.total==3 and len(first.items)==2 and len(second.items)==1
    assert len({x['application_id'] for x in first.items+second.items})==3
    assert 'phone' not in first.items[0] and 'user_id' not in first.items[0]
    (await db.get(MatchPost,100)).status='closed'
    assert (await inbox(db,'2')).total==0

@pytest.mark.asyncio
async def test_http_role_and_scope_cannot_be_bypassed(db):
    c=await club_request(db);app=FastAPI();app.include_router(api.router);current=await db.get(User,'2')
    async def user(): return current
    async def database(): yield db
    app.dependency_overrides[get_current_user]=user;app.dependency_overrides[get_db]=database
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://isolated') as client:
        assert (await client.post(f'/applications/clubs/{c.id}/review',json={'approved':True})).status_code==403
        assert (await client.get('/applications?scope=mine')).json()['total']==1
        assert (await client.get('/applications?scope=todo')).json()['total']==0
        current=await db.get(User,'1')
        assert (await client.post(f'/applications/clubs/{c.id}/review',json={'approved':True})).status_code==200
        assert (await client.post(f'/applications/clubs/{c.id}/review',json={'approved':True})).status_code==409
