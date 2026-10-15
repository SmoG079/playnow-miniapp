from datetime import date,datetime,timedelta
import pytest
from app.api.v1 import posts,tournaments
from app.models.models import User,MatchPost
from app.schemas.schemas import PostCreate
from app.schemas.tournament import TournamentCreate
from tests.test_tournaments import db

@pytest.mark.asyncio
async def test_free_post_keeps_place_name_separate_from_street_address(db):
    user=await db.get(User,'2')
    result=await posts.create_post(PostCreate(title='一起打球',city='扬州市',location_name='测试网球中心',address='广陵区长江路8号',latitude=32,longitude=119,preferred_date=date.today()+timedelta(days=2),preferred_start='19:00',preferred_end='21:00',min_players=4,max_players=6,price=0),user,db)
    stored=await db.get(MatchPost,result.id)
    assert stored.location_name=='测试网球中心' and stored.address=='广陵区长江路8号'
    detail=await posts.get_post(result.id,db,user)
    assert detail.location_name=='测试网球中心' and detail.address=='广陵区长江路8号'

@pytest.mark.asyncio
async def test_tournament_keeps_place_name_in_creation_and_details(db):
    start=datetime.utcnow()+timedelta(days=2)
    user=await db.get(User,'1')
    result=await tournaments.create_tournament(TournamentCreate(title='测试比赛',city='扬州市',location_name='测试网球中心（东区）',address='邗江区长春路48号',start_time=start,end_time=start+timedelta(hours=2),max_participants=4),user,db)
    detail=await tournaments.get_tournament(result['id'],user,db)
    assert detail['location_name']=='测试网球中心（东区）' and detail['address']=='邗江区长春路48号'
