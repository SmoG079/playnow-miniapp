"""MySQL snapshot and concurrent retry regression for private messages."""
import asyncio
import os
import secrets
from datetime import date, time
from unittest.mock import AsyncMock
import pytest
from sqlalchemy import select, delete, func
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from app.api.v1 import messages
from app.models.models import User, Activity, MatchPost, DirectConversation, DirectMessage

URL = os.environ.get('ACTIVITY_MYSQL_TEST_DATABASE_URL')
pytestmark = pytest.mark.skipif(not URL, reason='Explicit disposable MySQL required')


@pytest.mark.asyncio
async def test_concurrent_contact_send_and_read(monkeypatch):
    url = make_url(URL)
    if url.host not in ('127.0.0.1', 'localhost') or not (
        url.database == 'test_db' or url.database.startswith('playnow_test_')
    ):
        raise RuntimeError('Refusing non-disposable direct-message integration database')
    engine = create_async_engine(url, poolclass=NullPool, hide_parameters=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(messages, 'check_rate_limit', AsyncMock())
    token = secrets.token_hex(8)
    user_ids, post_id = [], None
    try:
        async with factory() as db:
            users = [User(openid=f'direct-test-{token}-{i}') for i in range(2)]
            db.add_all(users)
            await db.flush()
            user_ids = [u.id for u in users]
            activity = Activity(kind='post')
            db.add(activity)
            await db.flush()
            post_id = activity.id
            db.add(MatchPost(id=post_id, user_id=user_ids[0], title='隔离私信测试',
                             preferred_date=date(2030, 1, 1),
                             preferred_start=time(10), preferred_end=time(12)))
            await db.commit()

        async def contact():
            async with factory() as db:
                # Authentication reads before the competing write establish a snapshot.
                user = await db.get(User, user_ids[1])
                result = await messages.contact(messages.ContactPost(post_id=post_id), user, db)
                await db.commit()
                return result['id']

        ids = await asyncio.gather(contact(), contact())
        assert ids[0] == ids[1]
        conversation_id = ids[0]

        async def send():
            async with factory() as db:
                user = await db.get(User, user_ids[1])
                result = await messages.send(conversation_id, messages.SendMessage(
                    client_id='mysql-concurrent-retry', content='一起打球'), user, db)
                await db.commit()
                return result['id']

        ids = await asyncio.gather(send(), send())
        assert ids[0] == ids[1]
        async with factory() as db:
            assert await db.scalar(select(func.count()).select_from(DirectMessage).where(
                DirectMessage.conversation_id == conversation_id)) == 1
            owner = await db.get(User, user_ids[0])
            assert (await messages.unread_count(owner, db))['count'] == 1
            inbox = await messages.conversations(1, 20, owner, db)
            assert inbox['items'][0]['unread_count'] == 1
            await messages.mark_read(conversation_id, messages.ReadMessages(through_id=ids[0]), owner, db)
            assert (await messages.unread_count(owner, db))['count'] == 0
            await db.commit()
    finally:
        async with factory() as db:
            if post_id is not None:
                convs = select(DirectConversation.id).where(DirectConversation.post_id == post_id)
                await db.execute(delete(DirectMessage).where(DirectMessage.conversation_id.in_(convs)))
                await db.execute(delete(DirectConversation).where(DirectConversation.post_id == post_id))
                await db.execute(delete(MatchPost).where(MatchPost.id == post_id))
                await db.execute(delete(Activity).where(Activity.id == post_id))
            if user_ids:
                await db.execute(delete(User).where(User.id.in_(user_ids)))
            await db.commit()
        await engine.dispose()
