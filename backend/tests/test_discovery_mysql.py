"""MySQL ordering and city boundaries; disposable DB and Redis 15 only."""
import os,secrets
from datetime import datetime,timedelta,date
import pytest
import redis.asyncio as redis
from sqlalchemy import delete
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from sqlalchemy.pool import NullPool
from app.models.models import Club,User,MatchPost,Tournament,TournamentAudit,Activity
from app.api.v1 import posts,tournaments
from app.schemas.schemas import PostCreate
from app.schemas.tournament import TournamentCreate
from app.services import activity_ids
URL=os.environ.get('ACTIVITY_MYSQL_TEST_DATABASE_URL')
REDIS=os.environ.get('ACTIVITY_REDIS_TEST_URL')
pytestmark=pytest.mark.skipif(not URL or not REDIS,reason='Disposable MySQL and Redis 15 required')

@pytest.mark.asyncio
async def test_real_city_distance_date_and_type_pagination(monkeypatch):
    url=make_url(URL)
    assert url.database=='test_db' or url.database.startswith(('playnow_test_','playnow_migration_'))
    assert REDIS.rstrip('/').endswith('/15')
    engine=create_async_engine(url,poolclass=NullPool)
    factory=async_sessionmaker(engine,expire_on_commit=False)
    client=redis.from_url(REDIS,decode_responses=True)
    monkeypatch.setattr(activity_ids,'redis_client',client)
    city='城市测试'+secrets.token_hex(6);other_city='其他'+secrets.token_hex(6)
    ids=[];uid=cid=None
    try:
        async with factory() as db:
            owner=User(openid='discovery-'+secrets.token_hex(12));host=Club(name='筛选测试',city=city)
            db.add_all([owner,host]);await db.flush();uid,cid=owner.id,host.id
            for place,day,lat,lng in [(city,'2030-11-01',32.4,119.4),(city,'2030-12-01',32.9,119.9),(other_city,'2030-10-01',32.4,119.4)]:
                p=await posts.create_post(PostCreate(city=place,latitude=lat,longitude=lng,title=place,preferred_date=day,
                    preferred_start='09:00',preferred_end='11:00',players_needed=2,price=0),owner,db)
                ids.append(p.id)
            start=datetime(2030,11,1,16,30)
            t=await tournaments.create_tournament(TournamentCreate(city=city,club_id=cid,title='跨日比赛',address='网球场',start_time=start,
                end_time=start+timedelta(hours=2),max_participants=2),owner,db);ids.append(t['id'])
            await db.commit()
            args=dict(city=city,club_id=None,sport=None,status=None,ntrp_levels=None,lat=32.4,lng=119.4,
                sort_by='distance',page=1,page_size=1,activity_type='all',on_date=None,db=db)
            result=await posts.list_posts(**args)
            assert result.total==2 and result.items[0].id==ids[0]
            result=await posts.list_posts(**dict(args,sort_by='date_desc'))
            assert result.items[0].id==ids[1]
            assert (await posts.list_posts(**dict(args,city=None))).total==0
            assert (await posts.list_posts(**dict(args,activity_type='venue'))).total==0
            result=await tournaments.list_tournaments(city=city,sort_by='date_asc',lat=None,lng=None,on_date=date(2030,11,2),page=1,page_size=1,db=db)
            assert result['total']==1 and result['items'][0]['id']==ids[3]
    finally:
        async with factory() as db:
            if ids:
                await db.execute(delete(TournamentAudit).where(TournamentAudit.tournament_id.in_(ids)))
                await db.execute(delete(Tournament).where(Tournament.id.in_(ids)))
                await db.execute(delete(MatchPost).where(MatchPost.id.in_(ids)))
                await db.execute(delete(Activity).where(Activity.id.in_(ids)))
            if uid: await db.execute(delete(User).where(User.id==uid))
            if cid: await db.execute(delete(Club).where(Club.id==cid))
            await db.commit()
        await client.aclose();await engine.dispose()
