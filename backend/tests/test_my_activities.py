from datetime import datetime,timedelta,time
from zoneinfo import ZoneInfo
import pytest
from fastapi import FastAPI
from httpx import ASGITransport,AsyncClient
from app.api.v1 import users,tournaments
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.models import User,ClubMember,ClubMemberRole,Activity,MatchPost,MatchRegistration,RegistrationStatus
from app.schemas.tournament import TournamentCreate,TournamentConfig,RegistrationCommand
from tests.test_tournaments import db

async def activity(db,creator='2',title='海风杯'):
    result=await tournaments.create_tournament(TournamentCreate(club_id=1,title=title,address='球场',start_time=datetime.utcnow()+timedelta(days=2),end_time=datetime.utcnow()+timedelta(days=3),max_participants=4,config=TournamentConfig(approval_required=True)),await db.get(User,creator),db)
    return result['id']
async def records(db,uid='2',kind='tournament',relation='joined',phase='all',keyword='',page=1,size=20):
    return await users.my_activities(kind,relation,phase,keyword,page,size,await db.get(User,uid),db)

@pytest.mark.asyncio
async def test_participation_and_publication_are_separate_and_scoped(db):
    own=await activity(db);other=await activity(db,'1','另一比赛')
    await tournaments.register_tournament(other,RegistrationCommand(),await db.get(User,'2'),db)
    await tournaments.register_tournament(other,RegistrationCommand(),await db.get(User,'3'),db)
    joined=await records(db);published=await records(db,relation='published')
    assert [x['id'] for x in joined.items]==[other] and joined.items[0]['registration']['approval']=='pending'
    assert not joined.items[0]['can_manage']
    assert [x['id'] for x in published.items]==[own] and published.items[0]['can_manage']
    assert published.items[0]['registration'] is None
    assert (await records(db,'4')).total==0
    assert (await records(db,'1',relation='published')).items[0]['id']==other
    assert (await records(db,phase='review')).total==1
    assert (await records(db,relation='published',phase='review')).total==0

@pytest.mark.asyncio
async def test_search_name_number_pagination_and_literal_wildcards(db):
    first=await activity(db,title='海风杯');second=await activity(db,title='海风杯 2');third=await activity(db,title='100% 网球杯')
    result=await records(db,relation='published',keyword='海风',size=1)
    page2=await records(db,relation='published',keyword='海风',page=2,size=1)
    assert result.total==page2.total==2 and {result.items[0]['id'],page2.items[0]['id']}=={first,second}
    assert (await records(db,relation='published',keyword=f'#{third}')).items[0]['id']==third
    assert (await records(db,relation='published',keyword='%')).total==1
    assert (await records(db,relation='published',keyword='9999999999999999999999999999999999999')).total==0

@pytest.mark.asyncio
async def test_post_lifecycle_filters_use_shanghai_clock_and_keep_review_result(db):
    local=datetime.utcnow().replace(tzinfo=ZoneInfo('UTC')).astimezone(ZoneInfo('Asia/Shanghai'))
    db.add_all([Activity(id=i,kind='post') for i in [100,101,102]]);await db.flush()
    db.add_all([MatchPost(id=100,user_id='2',title='未来约球',preferred_date=local.date()+timedelta(days=1),preferred_start=time(9),preferred_end=time(11)),
        MatchPost(id=101,user_id='2',title='进行中的约球',preferred_date=local.date(),preferred_start=time(0),preferred_end=time(23,59,59)),
        MatchPost(id=102,user_id='2',title='已关闭约球',status='closed',preferred_date=local.date()+timedelta(days=1),preferred_start=time(9),preferred_end=time(11))]);await db.flush()
    db.add(MatchRegistration(post_id=100,user_id='3',status=RegistrationStatus.rejected,review_reason='名额不匹配'));await db.flush()
    assert [x['id'] for x in (await records(db,kind='post',relation='published',phase='open')).items]==[100]
    assert [x['id'] for x in (await records(db,kind='post',relation='published',phase='ongoing')).items]==[101]
    assert [x['id'] for x in (await records(db,kind='post',relation='published',phase='ended')).items]==[102]
    own=await records(db,'3',kind='post')
    assert own.items[0]['registration']=={'status':'rejected','review_reason':'名额不匹配'}

@pytest.mark.asyncio
async def test_concurrent_identities_are_derived_from_role_and_membership(db):
    admin=await db.get(User,'1')
    assert (await users.get_me(admin,db)).roles==['platform_admin']
    db.add(ClubMember(club_id=1,user_id='1',role=ClubMemberRole.owner));await db.flush()
    assert (await users.get_me(admin,db)).roles==['platform_admin','club_admin']
    assert (await users.get_me(await db.get(User,'2'),db)).roles==['user']

@pytest.mark.asyncio
async def test_http_defaults_to_tournaments_and_rejects_spoofed_scope(db):
    tid=await activity(db)
    await tournaments.register_tournament(tid,RegistrationCommand(),await db.get(User,'3'),db)
    app=FastAPI();app.include_router(users.router)
    async def database():yield db
    async def user():return await db.get(User,'3')
    app.dependency_overrides[get_db]=database;app.dependency_overrides[get_current_user]=user
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://isolated') as client:
        result=await client.get('/users/me/activity-records?user_id=2')
        assert result.status_code==200 and result.json()['items'][0]['kind']=='tournament'
        assert (await client.get('/users/me/activity-records?relation=published')).json()['total']==0
        assert (await client.get('/users/me/activity-records?kind=invalid')).status_code==422

@pytest.mark.asyncio
async def test_published_post_is_visible_without_own_registration(db):
    db.add(Activity(id=300,kind='post'));await db.flush()
    db.add(MatchPost(id=300,user_id='2',title='我发布的约球',preferred_date=datetime.utcnow().date()+timedelta(days=1),preferred_start=time(9),preferred_end=time(11)));await db.flush()
    app=FastAPI();app.include_router(users.router)
    async def database():yield db
    async def user():return await db.get(User,'2')
    app.dependency_overrides[get_db]=database;app.dependency_overrides[get_current_user]=user
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://isolated') as client:
        for route in ('/users/me/activity-records','/users/me/activities'):
            default=await client.get(route+'?relation=published')
            assert default.status_code==200 and default.json()['total']==0
            posts=await client.get(route+'?relation=published&kind=post')
            assert posts.status_code==200 and posts.json()['total']==1
            row=posts.json()['items'][0]
            assert row['id']==300 and row['can_manage'] and row['registration'] is None
        joined=await client.get('/users/me/activity-records?kind=post')
        assert joined.json()['total']==0
