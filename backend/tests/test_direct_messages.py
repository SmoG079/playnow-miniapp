from datetime import date,time,timedelta
from unittest.mock import AsyncMock
import pytest
from pydantic import ValidationError
from fastapi import HTTPException,FastAPI
from httpx import AsyncClient,ASGITransport
from sqlalchemy import select,func
from app.api.v1 import messages
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.models import User,MatchPost,Activity,DirectMessage,DirectConversation
from tests.test_tournaments import db

async def setup(db,monkeypatch):
    monkeypatch.setattr(messages,'check_rate_limit',AsyncMock())
    db.add_all([Activity(id=800,kind='post'),Activity(id=801,kind='post')]);await db.flush()
    db.add_all([MatchPost(id=800,user_id='1',title='约球',preferred_date=date.today()+timedelta(days=1),preferred_start=time(10),preferred_end=time(12)),MatchPost(id=801,user_id='1',title='另一场约球')]);await db.flush()
    sender=await db.get(User,'2');receiver=await db.get(User,'1');outsider=await db.get(User,'3')
    c=await messages.contact(messages.ContactPost(post_id=800),sender,db)
    return c,sender,receiver,outsider

@pytest.mark.asyncio
async def test_contact_reuses_pair_and_does_not_reveal_private_identity(db,monkeypatch):
    c,s,r,_=await setup(db,monkeypatch)
    assert (await messages.contact(messages.ContactPost(post_id=801),s,db))['id']==c['id']
    assert await db.scalar(select(func.count()).select_from(DirectConversation))==1
    assert 'phone' not in c['peer'] and 'openid' not in c['peer'] and 'id' not in c['peer']
    assert (await messages.conversations(1,20,r,db))['items']==[]
    with pytest.raises(HTTPException) as e:await messages.contact(messages.ContactPost(post_id=800),r,db)
    assert e.value.status_code==409

@pytest.mark.asyncio
async def test_text_unread_and_retry_are_idempotent(db,monkeypatch):
    c,s,r,_=await setup(db,monkeypatch)
    req=messages.SendMessage(client_id='same-key-123',content='一起打球\n几点到？')
    first=await messages.send(c['id'],req,s,db)
    assert (await messages.send(c['id'],req,s,db))['id']==first['id']
    assert await db.scalar(select(func.count()).select_from(DirectMessage))==1
    assert (await messages.unread_count(r,db))['count']==1
    assert (await messages.unread_count(s,db))['count']==0
    assert (await messages.conversations(1,20,r,db))['items'][0]['unread_count']==1
    assert not (await messages.history(c['id'],None,None,30,r,db))['items'][0]['is_mine']
    await messages.mark_read(c['id'],messages.ReadMessages(through_id=first['id']),r,db)
    await messages.mark_read(c['id'],messages.ReadMessages(through_id=0),r,db)
    assert (await messages.unread_count(r,db))['count']==0
    second=await messages.send(c['id'],messages.SendMessage(client_id='second-key',content='明天见'),s,db)
    await messages.mark_read(c['id'],messages.ReadMessages(through_id=first['id']),r,db)
    assert (await messages.unread_count(r,db))['count']==1
    assert [m['id'] for m in (await messages.history(c['id'],None,first['id'],30,r,db))['items']]==[second['id']]
    with pytest.raises(HTTPException) as e:await messages.send(c['id'],messages.SendMessage(client_id=req.client_id,content='修改内容'),s,db)
    assert e.value.status_code==409

@pytest.mark.asyncio
@pytest.mark.parametrize('role',['user','platform_admin'])
async def test_every_conversation_operation_rejects_outsiders(db,monkeypatch,role):
    c,_,_,x=await setup(db,monkeypatch)
    x.role=role;await db.flush()
    calls=[lambda:messages.detail(c['id'],x,db),lambda:messages.history(c['id'],None,None,30,x,db),lambda:messages.send(c['id'],messages.SendMessage(client_id='outsider-key',content='私信'),x,db),lambda:messages.mark_read(c['id'],messages.ReadMessages(through_id=999),x,db)]
    for call in calls:
        with pytest.raises(HTTPException) as e:await call()
        assert e.value.status_code==404
    assert (await messages.conversations(1,20,x,db))['total']==0

@pytest.mark.asyncio
async def test_history_pagination_and_http_auth(db,monkeypatch):
    c,s,r,_=await setup(db,monkeypatch)
    sent=[await messages.send(c['id'],messages.SendMessage(client_id=f'pagination-{i}',content=f'消息{i}'),s,db) for i in range(5)]
    latest=await messages.history(c['id'],None,None,2,r,db)
    assert latest['has_more'] and [m['id'] for m in latest['items']]==[m['id'] for m in sent[-2:]]
    older=await messages.history(c['id'],latest['items'][0]['id'],None,2,r,db)
    assert [m['id'] for m in older['items']]==[m['id'] for m in sent[1:3]]
    new=await messages.history(c['id'],None,0,2,r,db)
    assert new['has_more'] and [m['id'] for m in new['items']]==[m['id'] for m in sent[:2]]
    app=FastAPI();app.include_router(messages.router)
    async def database():yield db
    app.dependency_overrides[get_db]=database
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://isolated') as client:
        assert (await client.get('/messages/conversations')).status_code==401
        async def user():return r
        app.dependency_overrides[get_current_user]=user
        response=await client.get('/messages/conversations')
        assert response.status_code==200 and response.json()['total']==1
        body=response.json()['items'][0]
        assert body['peer'].keys()=={'nickname','avatar_url'}

@pytest.mark.parametrize('content',['','   ','x'*2001])
def test_invalid_text(content):
    with pytest.raises(ValidationError):messages.SendMessage(client_id='valid-key',content=content)
