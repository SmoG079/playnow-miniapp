from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
import pytest
from pydantic import ValidationError
from app.api.v1 import tournaments
from app.models.models import User,Tournament
from app.schemas.tournament import TournamentCreate,RegistrationCommand,ReasonCommand
from app.services.activity_discovery import list_activities
from tests.test_tournaments import db,event
from tests.test_discovery import post

async def fixtures(db):
    day=(datetime.now(ZoneInfo('Asia/Shanghai'))+timedelta(days=3)).date()
    p1=await post(db,'南京市',day.isoformat(),preferred_start='09:00',level_required='3.0-4.0')
    tid,owner=await event(db,4)
    t=await db.get(Tournament,tid);t.city='南京市';t.level_required='3.5';t.start_time=datetime.combine(day,datetime.min.time())+timedelta(hours=2);t.end_time=t.start_time+timedelta(hours=3)
    p2=await post(db,'南京市',day.isoformat(),preferred_start='11:00',level_required='4.5')
    await db.flush()
    return p1.id,tid,p2.id,day,owner

@pytest.mark.asyncio
async def test_mixed_chronology_and_pagination(db):
    a,b,c,day,_=await fixtures(db)
    items=[]
    for page in (1,2,3):
        result=await list_activities(db,'南京市',page=page,page_size=1)
        assert result['total']==3;items.extend(result['items'])
    assert [x['id'] for x in items]==[a,b,c]
    assert [x['kind'] for x in items]==['post','tournament','post']
    assert [x['id'] for x in (await list_activities(db,'南京市',sort_by='date_desc'))['items']]==[c,b,a]
    assert (await list_activities(db,'扬州市'))['total']==0
    assert (await list_activities(db,''))['total']==0
    assert (await list_activities(db,'南京市',on_date=day+timedelta(days=1)))['total']==0

@pytest.mark.asyncio
async def test_type_and_level_filters_before_pagination(db):
    a,b,c,_,_=await fixtures(db)
    result=await list_activities(db,'南京市',ntrp_levels='3.5',page_size=1)
    assert result['total']==2 and result['items'][0]['id']==a
    assert (await list_activities(db,'南京市',ntrp_levels='3.5',page=2,page_size=1))['items'][0]['id']==b
    assert [x['id'] for x in (await list_activities(db,'南京市',activity_type='tournament'))['items']]==[b]
    assert (await list_activities(db,'南京市',activity_type='post'))['total']==2
    assert (await list_activities(db,'南京市',activity_type='venue'))['total']==0
    result=await list_activities(db=db,activity_type='tournament',city='南京市',ntrp_levels='3.5',sort_by='date_asc',lat=None,lng=None,page=1,page_size=20)
    assert result['total']==1 and result['items'][0]['level_required']=='3.5'

@pytest.mark.asyncio
async def test_cancelled_registration_hidden_in_participants_but_history_and_mine_retained(db):
    tid,owner=await event(db,4)
    participant=await db.get(User,'2')
    reg=await tournaments.register_tournament(tid,RegistrationCommand(),participant,db)
    await tournaments.cancel_registration(tid,reg['registration_id'],ReasonCommand(reason='取消报名'),owner,db)
    admin=await tournaments.get_tournament(tid,owner,db)
    assert admin['participants']==[] and admin['registrations'][0]['status']=='cancelled'
    assert admin['current_participants']==0
    personal=await tournaments.get_tournament(tid,participant,db)
    assert personal['participants']==[] and personal['my_registration']['status']=='cancelled'

@pytest.mark.parametrize('level',['0.5','7.5','3.3','4.0-3.0','a','NaN','3.0-','3.0-4.0-5.0'])
def test_invalid_ntrp_rejected(level):
    with pytest.raises(ValidationError):
        TournamentCreate(title='测试',address='球场',start_time=datetime(2030,1,1),end_time=datetime(2030,1,2),max_participants=4,level_required=level)

@pytest.mark.parametrize('value,expected',[('3','3.0'),('3.0–4.0','3.0-4.0'),('不限',None),('',None)])
def test_ntrp_normalization(value,expected):
    assert TournamentCreate(title='测试',address='球场',start_time=datetime(2030,1,1),end_time=datetime(2030,1,2),max_participants=4,level_required=value).level_required==expected

@pytest.mark.asyncio
async def test_distance_sort_places_missing_coordinates_last(db):
    from app.models.models import MatchPost
    a,b,c,_,_=await fixtures(db)
    p=await db.get(MatchPost,a);p.latitude=33;p.longitude=119
    t=await db.get(Tournament,b);t.latitude=32;t.longitude=118
    await db.flush()
    result=await list_activities(db,'南京市',sort_by='distance',lat=32,lng=118)
    assert [x['id'] for x in result['items']]==[b,a,c]

@pytest.mark.asyncio
async def test_public_square_http_filters_and_serialization(db):
    from fastapi import FastAPI
    from httpx import AsyncClient,ASGITransport
    from app.api.v1.discovery import router
    from app.core.database import get_db
    a,b,c,day,_=await fixtures(db)
    app=FastAPI();app.include_router(router)
    async def database():yield db
    app.dependency_overrides[get_db]=database
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://isolated') as client:
        result=await client.get('/discovery/activities',params={'city':'南京市','ntrp_levels':'3.5','page_size':1})
        assert result.status_code==200 and result.json()['total']==2
        assert result.json()['items'][0]['preferred_date']==day.isoformat()
        result=await client.get('/discovery/activities',params={'city':'南京市','activity_type':'tournament'})
        assert result.json()['items'][0]['id']==b and result.json()['items'][0]['level_required']=='3.5'
        assert (await client.get('/discovery/activities?activity_type=unknown')).status_code==422
        assert (await client.get('/discovery/activities?city=南京市&sort_by=distance')).status_code==422

@pytest.mark.asyncio
async def test_old_collection_routes_removed(db):
    from fastapi import FastAPI
    from httpx import AsyncClient,ASGITransport
    from app.api.v1 import posts,discovery
    app=FastAPI();app.include_router(posts.router);app.include_router(tournaments.router);app.include_router(discovery.router)
    schema=app.openapi()
    assert 'get' not in schema['paths']['/posts'] and 'get' not in schema['paths']['/tournaments']
    assert 'post' in schema['paths']['/posts'] and 'post' in schema['paths']['/tournaments']
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://isolated') as client:
        assert (await client.get('/posts')).status_code==405
        assert (await client.get('/tournaments')).status_code==405
