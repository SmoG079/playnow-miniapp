from datetime import date, datetime, timedelta
import pytest
from app.models.models import User, MatchPost, Club
from app.api.v1 import posts,tournaments
from app.api.v1.discovery import parse_city
from app.schemas.schemas import PostCreate
from app.schemas.tournament import TournamentCreate
from tests.test_tournaments import db

async def listing(db,city='扬州市',**options):
    args=dict(club_id=None,sport=None,status=None,ntrp_levels=None,lat=None,lng=None,
              sort_by='date_asc',page=1,page_size=20,city=city,activity_type='all',on_date=None,db=db)
    args.update(options)
    return await posts.list_posts(**args)

async def post(db,city,day,**fields):
    payload=dict(title=city or '历史无城市',city=city,preferred_date=day,
        preferred_start='10:00',preferred_end='12:00',players_needed=2,price=0)
    payload.update(fields)
    return await posts.create_post(PostCreate(**payload),await db.get(User,2),db)

@pytest.mark.asyncio
async def test_city_isolation_empty_city_and_dates_before_pagination(db):
    old=await post(db,'扬州市','2026-11-01')
    far=await post(db,'扬州市','2026-12-01')
    other=await post(db,'南京市','2026-10-01')
    legacy=await post(db,None,'2026-10-01')
    assert [x.id for x in (await listing(db,page_size=1)).items]==[old.id]
    assert [x.id for x in (await listing(db,page_size=1,sort_by='date_desc')).items]==[far.id]
    assert (await listing(db)).total==2
    assert [x.id for x in (await listing(db,city='南京市')).items]==[other.id]
    assert (await listing(db,city=None)).total==0
    assert [x.id for x in (await listing(db,on_date=date(2026,12,1))).items]==[far.id]
    assert (await listing(db,on_date=date(2026,12,1))).total==1
    assert (await db.get(MatchPost,legacy.id)) is not None

@pytest.mark.asyncio
async def test_type_and_distance_order_applied_before_pagination(db):
    near=await post(db,'扬州市','2026-11-01',latitude=32.4,longitude=119.4)
    far=await post(db,'扬州市','2026-11-01',latitude=32.9,longitude=119.9)
    unknown=await post(db,'扬州市','2026-11-01')
    result=await listing(db,sort_by='distance',lat=32.4,lng=119.4,page_size=1)
    assert [x.id for x in result.items]==[near.id] and result.total==3
    assert result.items[0].distance==0
    assert [x.id for x in (await listing(db,sort_by='distance',lat=32.4,lng=119.4,page=3,page_size=1)).items]==[unknown.id]
    assert (await listing(db,activity_type='venue')).total==0
    assert (await listing(db,activity_type='free')).total==3

@pytest.mark.asyncio
async def test_tournaments_city_and_shanghai_day_filter(db):
    owner=await db.get(User,2)
    for city,start in [('扬州市',datetime(2026,11,1,16,30)),('南京市',datetime(2026,11,1,16,30)),('扬州市',datetime(2026,11,2,18))]:
        await tournaments.create_tournament(TournamentCreate(city=city,club_id=1,title=city,address='网球场',
            start_time=start,end_time=start+timedelta(hours=2),max_participants=2),owner,db)
    result=await tournaments.list_tournaments(db=db,city='扬州市',sort_by='date_desc',lat=None,lng=None,
        page=1,page_size=1,on_date=date(2026,11,2))
    assert result['total']==1 and result['items'][0]['city']=='扬州市'

@pytest.mark.parametrize('province,city,district,expected',[
    ('江苏省','扬州市','广陵区','扬州市'),('北京市','市辖区','朝阳区','北京市'),
    ('河南省','省直辖县级行政区划','济源市','济源市')])
def test_provider_city_normalization(province,city,district,expected):
    assert parse_city({'status':0,'result':{'address_component':dict(province=province,city=city,district=district)}})['city']==expected

@pytest.mark.asyncio
async def test_manual_city_selection_does_not_require_map_provider(db):
    from fastapi import HTTPException
    await post(db,'扬州市','2026-11-01')
    assert (await listing(db)).total==1
    with pytest.raises(HTTPException) as err: await listing(db,sort_by='distance')
    assert err.value.status_code==422

@pytest.mark.asyncio
async def test_location_proxy_handles_credentials_provider_failure_and_success(monkeypatch):
    from types import SimpleNamespace
    from fastapi import HTTPException, Request
    from app.api.v1 import discovery
    request=Request({'type':'http','client':('127.0.0.1',1)})
    monkeypatch.setattr(discovery,'get_settings',lambda:SimpleNamespace(TENCENT_MAP_KEY=''))
    with pytest.raises(HTTPException) as err: await discovery.location_city(request,32.4,119.4)
    assert err.value.status_code==503
    monkeypatch.setattr(discovery,'get_settings',lambda:SimpleNamespace(TENCENT_MAP_KEY='isolated-test-key'))
    async def no_limit(*args): pass
    monkeypatch.setattr(discovery,'check_rate_limit',no_limit)
    class Client:
        def __init__(self,*args,**kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
        async def get(self,url,params,headers):
            assert params['location']=='32.4,119.4' and params['key']=='isolated-test-key'
            return SimpleNamespace(raise_for_status=lambda:None,json=lambda:{'status':0,'result':{'address_component':{'province':'江苏省','city':'扬州市','district':'广陵区'}}})
    monkeypatch.setattr(discovery.httpx,'AsyncClient',Client)
    result=await discovery.location_city(request,32.4,119.4)
    assert result['city']=='扬州市' and 'key' not in result

@pytest.mark.parametrize('schema,payload',[
    (PostCreate,dict(title='测试',preferred_date='2030-11-01',preferred_start='09:00',preferred_end='11:00',players_needed=2,price=0)),
    (TournamentCreate,dict(title='测试',club_id=1,address='网球场',start_time='2030-11-01T09:00:00',end_time='2030-11-01T11:00:00',max_participants=2)),
])
def test_city_and_location_input_validation(schema,payload):
    from pydantic import ValidationError
    with pytest.raises(ValidationError): schema(**dict(payload,city='  '))
    with pytest.raises(ValidationError): schema(**dict(payload,city='扬州市',latitude=32.4))
    assert schema(**dict(payload,city=' 扬州市 ',latitude=32.4,longitude=119.4)).city=='扬州市'

@pytest.mark.asyncio
async def test_courts_in_same_club_are_independent_and_override_client_location(db):
    from app.api.v1 import venues, clubs
    from app.models.models import Venue, BookingOrder, OrderStatus
    from app.schemas.schemas import VenueCreate, VenueUpdate
    owner=await db.get(User,2)
    club=await db.get(Club,1)
    club.city='错误俱乐部城市'; club.latitude=0; club.longitude=0; club.address='办公室'
    club.status='active'
    first=await venues.create_venue_for_club(1,VenueCreate(name='扬州球场',price_per_hour=10,city='扬州市',address='扬州实际地址',latitude=32.4,longitude=119.4),owner,db)
    second=await venues.create_venue_for_club(1,VenueCreate(name='南京球场',price_per_hour=10,city='南京市',address='南京实际地址',latitude=32,longitude=118.8),owner,db)
    records=[]
    for v in (first,second):
        order=BookingOrder(user_id=owner.id,club_id=1,venue_id=v.id,order_no="location-test-"+str(v.id),amount=10,status=OrderStatus.paid,business_type='booking')
        db.add(order); await db.flush()
        p=await post(db,'伪造城市','2026-11-01',venue_id=v.id,booking_id=order.id,latitude=1,longitude=1)
        assert p.city==v.city and p.latitude==v.latitude
        records.append(p)
        t=await tournaments.create_tournament(TournamentCreate(city='伪造城市',latitude=1,longitude=1,club_id=1,venue_id=v.id,title='比赛',address='假地址',start_time=datetime(2026,11,1),end_time=datetime(2026,11,2),max_participants=2),owner,db)
        detail=await tournaments.get_tournament(t['id'],owner,db)
        assert detail['address']==v.address and detail['city']==v.city
    assert [p.id for p in (await listing(db,city='扬州市')).items]==[records[0].id]
    assert [p.id for p in (await listing(db,city='南京市')).items]==[records[1].id]
    detail=await posts.get_post(records[1].id,db)
    assert detail.venue_address=='南京实际地址' and detail.venue_latitude==32
    # Court edits update linked activities and their personal-record snapshots.
    await venues.update_venue(second.id,1,VenueUpdate(city='镇江市',address='镇江实际地址',latitude=32.2,longitude=119.4),owner,db)
    assert (await listing(db,city='南京市')).total==0
    assert (await listing(db,city='镇江市')).total==1
    detail=await posts.get_post(records[1].id,db)
    assert detail.venue_address=='镇江实际地址'
    assert (await db.get(Club,1)).address=='办公室'
    found=await clubs.list_clubs(lat=32.4,lng=119.4,sport=None,keyword=None,page=1,page_size=1,db=db)
    assert found.items[0].nearest_venue_id==first.id and found.items[0].distance==0
    assert found.items[0].venue_address=='扬州实际地址'
    changed=await venues.update_venue(first.id,1,VenueUpdate(address='地址变更待重新定位'),owner,db)
    assert changed.latitude is None and changed.longitude is None

@pytest.mark.parametrize('schema', ['create','update'])
def test_court_coordinates_and_blank_location_are_validated(schema):
    from app.schemas.schemas import VenueCreate,VenueUpdate
    from pydantic import ValidationError
    kind=VenueCreate if schema=='create' else VenueUpdate
    args=dict(name='球场',price_per_hour=10) if schema=='create' else {}
    for location in (dict(city=' '),dict(address=' '),dict(latitude=32),dict(latitude=100,longitude=119)):
        with pytest.raises(ValidationError): kind(**args,**location)
