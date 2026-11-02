"""Upgrade the deployed schema on disposable MySQL, preserving historical money."""
import os
import uuid
from pathlib import Path
from datetime import datetime
import pytest
import sqlalchemy as sa
from sqlalchemy.engine import make_url
from alembic import command
from alembic.config import Config

@pytest.mark.skipif(not os.environ.get('TOURNAMENT_MYSQL_TEST_DATABASE_URL'),reason='Explicit isolated MySQL required')
def test_community_wallet_upgrade_preserves_receipts_and_members():
    source=make_url(os.environ['TOURNAMENT_MYSQL_TEST_DATABASE_URL'])
    if source.host not in ('localhost','127.0.0.1') or not (source.database=='test_db' or source.database.startswith('playnow_test_')):
        raise RuntimeError('Only isolated local MySQL allowed')
    name='playnow_migration_wallet_'+uuid.uuid4().hex[:10]
    admin=sa.create_engine(source.set(drivername='mysql+pymysql',database=None),hide_parameters=True)
    with admin.begin() as c:c.execute(sa.text('CREATE DATABASE '+name+' CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci'))
    engine=sa.create_engine(source.set(drivername='mysql+pymysql',database=name),hide_parameters=True)
    try:
        with engine.connect() as c:
            root=Path(__file__).resolve().parents[1]
            cfg=Config(str(root/'alembic.ini'));cfg.set_main_option('script_location',str(root/'alembic'));cfg.attributes['connection']=c
            command.upgrade(cfg,'20261020_activity_payment');c.commit()
            meta=sa.MetaData()
            def table(n):return sa.Table(n,meta,autoload_with=c)
            c.execute(table('users').insert(),[dict(id=str(i),openid='wallet-migrate-'+str(i),public_id='wallet-pub-'+str(i),role='user') for i in (1,2)])
            c.execute(table('clubs').insert().values(id=1,name='无场地社群',city='上海市',created_by='1',opening_time='08:00',closing_time='22:00',split_ratio='.100',view_count=0,exposure_count=0,status='active',approval_status='approved'))
            c.execute(table('club_members').insert().values(club_id=1,user_id='1',role='owner',created_at=datetime(2026,1,1)))
            c.execute(table('activities').insert().values(id=701,kind='post',created_at=datetime(2026,1,1)))
            c.execute(table('match_posts').insert().values(id=701,user_id='1',title='历史收费活动',price=214,payment_method='online',max_players=4,min_players=2,approval_required=False,status='open'))
            orders=table('booking_orders')
            for i,tx in enumerate(('real-wallet-tx','dev_placeholder',None),1):
                c.execute(orders.insert().values(id=i,order_no='migrate-'+str(i),business_type='post',post_id=701,user_id='2',amount=214,status='paid',slot_ids=[],wx_transaction_id=tx))
            c.commit()
            before=c.execute(sa.text('SELECT id,amount,status,wx_transaction_id FROM booking_orders ORDER BY id')).all()
            command.upgrade(cfg,'head');c.commit();command.upgrade(cfg,'head');c.commit()
            assert c.execute(sa.text('SELECT id,amount,status,wx_transaction_id FROM booking_orders ORDER BY id')).all()==before
            assert c.execute(sa.text('SELECT order_id,owner_id,fee_rate FROM activity_earnings')).one()==(1,'1',None)
            assert c.execute(sa.text('SELECT club_id,user_id FROM community_members')).one()==(1,'1')
            assert c.scalar(sa.text('SELECT COUNT(*) FROM activity_transfers'))==0
            assert c.scalar(sa.text('SELECT COUNT(*) FROM activity_withdrawals'))==0
            assert c.scalar(sa.text('SELECT version_num FROM alembic_version'))=='20261102_activity_wallet'
            inspector=sa.inspect(c)
            assert any(f['constrained_columns']==['order_id'] for f in inspector.get_foreign_keys('activity_earnings'))
            assert any(f['constrained_columns']==['user_id'] for f in inspector.get_foreign_keys('community_members'))
            with pytest.raises(sa.exc.IntegrityError):
                c.execute(sa.text("INSERT INTO community_members (club_id,user_id,created_at) VALUES (1,'1',UTC_TIMESTAMP())"))
            c.rollback()
    finally:
        engine.dispose()
        with admin.begin() as c:c.execute(sa.text('DROP DATABASE '+name))
        admin.dispose()
