"""Withdrawals serialize on an owner row; real MySQL locks, mocked transfer I/O."""
import asyncio
import os
import uuid
from datetime import datetime, timedelta, time
from pathlib import Path
import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy.engine import make_url
from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from app.models.models import User, Activity, MatchPost, BookingOrder, ActivityTransfer
from app.services import activity_wallet as wallet
from tests.test_activity_wallet import enabled

@pytest.mark.asyncio
@pytest.mark.skipif(not os.environ.get('TOURNAMENT_MYSQL_TEST_DATABASE_URL'),reason='Explicit isolated MySQL required')
async def test_concurrent_withdrawals_cannot_spend_the_same_receipt_twice(enabled):
    source=make_url(os.environ['TOURNAMENT_MYSQL_TEST_DATABASE_URL'])
    if source.host not in ('localhost','127.0.0.1') or not (source.database=='test_db' or source.database.startswith('playnow_test_')):
        raise RuntimeError('Only isolated local MySQL allowed')
    name='playnow_migration_wallet_race_'+uuid.uuid4().hex[:10]
    admin=sa.create_engine(source.set(drivername='mysql+pymysql',database=None),hide_parameters=True)
    with admin.begin() as c:c.execute(sa.text('CREATE DATABASE '+name+' CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci'))
    sync=sa.create_engine(source.set(drivername='mysql+pymysql',database=name),hide_parameters=True)
    engine=create_async_engine(source.set(drivername='mysql+asyncmy',database=name),poolclass=NullPool,hide_parameters=True)
    factory=async_sessionmaker(engine,expire_on_commit=False)
    try:
        with sync.connect() as c:
            root=Path(__file__).resolve().parents[1]
            cfg=Config(str(root/'alembic.ini'));cfg.set_main_option('script_location',str(root/'alembic'));cfg.attributes['connection']=c
            command.upgrade(cfg,'head');c.commit()
        async with factory() as db:
            db.add_all([User(id=str(i),openid='race-wx-'+str(i),public_id='race-pub-'+str(i),role='user') for i in (1,2)])
            db.add(Activity(id=701,kind='post'));await db.flush()
            db.add(MatchPost(id=701,user_id='1',title='提现并发',preferred_date=(datetime.now()-timedelta(days=2)).date(),preferred_start=time(9),preferred_end=time(11),max_players=4,min_players=2,price=100,payment_method='online'))
            await db.flush()
            order=BookingOrder(order_no='race-order',business_type='post',post_id=701,user_id='2',amount=100,status='paid',wx_transaction_id='real-race-tx')
            db.add(order);await db.flush();await wallet.capture(db,order);await db.commit()
        gate=asyncio.Event()
        async def submit(key):
            async with factory() as db:
                user=await db.get(User,'1');await gate.wait()
                try:
                    record=await wallet.reserve(db,user,key);await db.commit();return record.id
                except HTTPException as e:
                    await db.rollback();assert e.status_code==409;return None
        a=asyncio.create_task(submit('race-request-a'));b=asyncio.create_task(submit('race-request-b'));gate.set()
        results=await asyncio.gather(a,b)
        assert sum(r is not None for r in results)==1
        async with factory() as db:
            bills=(await db.scalars(sa.select(ActivityTransfer))).all()
            assert sum(b.amount_cents for b in bills)==9940
            assert (await wallet.overview(db,'1'))['available_cents']==0
    finally:
        await engine.dispose();sync.dispose()
        with admin.begin() as c:c.execute(sa.text('DROP DATABASE '+name))
        admin.dispose()
