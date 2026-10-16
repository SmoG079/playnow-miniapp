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


@pytest.mark.asyncio
async def test_card_thumbnails_include_owner_and_only_public_approved_people(db):
    from sqlalchemy import event as sql_event
    from app.models.models import MatchPost, MatchRegistration, RegistrationStatus
    a, _, c, _, _ = await fixtures(db)
    for uid, state in [('2', 'approved'), ('3', 'approved'), ('4', 'approved'),
                       ('5', 'approved'), ('6', 'pending'), ('7', 'rejected'), ('8', 'cancelled')]:
        db.add(MatchRegistration(post_id=a, user_id=uid, status=RegistrationStatus(state)))
    # An owner must never appear a second time in the public thumbnails.
    owner_post = await db.get(MatchPost, a)
    user = await db.get(User, '3'); user.nickname = '卡片球友'; user.avatar_url = 'https://example.com/3.jpg'
    await db.flush()
    selects = []
    def capture(_conn, _cursor, statement, _params, _context, _many):
        if 'row_number()' in statement.lower(): selects.append(statement)
    sql_event.listen(db.bind.sync_engine, 'before_cursor_execute', capture)
    try:
        result = await list_activities(db, '南京市', activity_type='post')
    finally:
        sql_event.remove(db.bind.sync_engine, 'before_cursor_execute', capture)
    cards = {card['id']: card for card in result['items']}
    people = cards[a]['card_participants']
    assert people[0]['user_id'] == owner_post.user_id
    assert len(people) == 4 and len({p['user_id'] for p in people}) == 4
    assert {p['user_id'] for p in people}.isdisjoint({'6', '7', '8'})
    assert next(p for p in people if p['user_id'] == '3')['user_avatar'] == 'https://example.com/3.jpg'
    assert cards[c]['card_participants'] == [dict(user_id=cards[c]['user_id'], user_nickname=cards[c]['user_nickname'], user_avatar=cards[c]['user_avatar'])]
    assert len(selects) == 1  # One bounded query covers every post on the page.
    assert set(people[0]) == {'user_id', 'user_nickname', 'user_avatar'}
    from tests.test_my_activities import records
    personal = await records(db, uid='2', kind='post', relation='published')
    own_card = next(card for card in personal.items if card['id'] == a)
    assert own_card['card_participants'] == people and own_card['can_manage'] is True
    assert own_card['registration_count'] == cards[a]['registration_count']


@pytest.mark.asyncio
async def test_tournament_card_uses_confirmed_roster_and_display_config(db):
    from app.models.models import TournamentRegistration, TournamentRegStatus
    _, tid, _, _, _ = await fixtures(db)
    t = await db.get(Tournament, tid)
    t.location_name = '测试网球中心'; t.address = '测试区体育路8号'
    t.config = {**t.config, 'discipline': 'doubles', 'pairing': 'fixed'}
    states = [dict(), dict(approval='pending'), dict(payment='unpaid'), dict(admission='waitlist'),
              dict(status=TournamentRegStatus.cancelled), dict(status=TournamentRegStatus.registered), dict(payment='verified')]
    for uid, extra in enumerate(states, 2):
        fields = dict(status=TournamentRegStatus.confirmed, approval='approved', admission='active', payment='none')
        db.add(TournamentRegistration(tournament_id=tid, user_id=str(uid), **{**fields, **extra}))
    await db.flush()
    card = (await list_activities(db, '南京市', activity_type='tournament'))['items'][0]
    assert [p['user_id'] for p in card['card_participants']] == ['2', '8']
    assert card['location_name'] == '测试网球中心' and card['address'] == '测试区体育路8号'
    assert card['config'] == dict(format='knockout', discipline='doubles', pairing='fixed')
    from tests.test_my_activities import records
    personal = await records(db, uid='1', relation='published')
    own_card = next(item for item in personal.items if item['id'] == tid)
    assert own_card['card_participants'] == card['card_participants']
    assert own_card['config'] == card['config'] and own_card['can_manage'] is True
