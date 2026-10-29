"""Exercise payment-channel defaults and references on an isolated real MySQL."""
import os
import uuid
from pathlib import Path
from datetime import datetime, date, time
import pytest
import sqlalchemy as sa
from sqlalchemy.engine import make_url
from alembic import command
from alembic.config import Config


@pytest.mark.skipif(not os.environ.get('TOURNAMENT_MYSQL_TEST_DATABASE_URL'), reason='Explicit disposable local MySQL required')
def test_payment_channel_migration_preserves_legacy_and_repeats():
    source=make_url(os.environ['TOURNAMENT_MYSQL_TEST_DATABASE_URL'])
    if source.host not in ('localhost','127.0.0.1') or not source.database.startswith('playnow_test_'):
        raise RuntimeError('Only isolated local MySQL allowed')
    name='playnow_migration_payment_'+uuid.uuid4().hex[:10]
    admin=sa.create_engine(source.set(drivername='mysql+pymysql',database=None),hide_parameters=True)
    with admin.begin() as c:c.execute(sa.text('CREATE DATABASE '+name+' CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci'))
    engine=sa.create_engine(source.set(drivername='mysql+pymysql',database=name),hide_parameters=True)
    try:
        with engine.connect() as c:
            root=Path(__file__).resolve().parents[1]
            cfg=Config(str(root/'alembic.ini'));cfg.set_main_option('script_location',str(root/'alembic'));cfg.attributes['connection']=c
            command.upgrade(cfg,'20261019_tournament_owner');c.commit()
            meta=sa.MetaData()
            def table(name):return sa.Table(name,meta,autoload_with=c)
            c.execute(table('users').insert(),[dict(id=str(i),openid='channel-wx-'+str(i),public_id='channel-public-'+str(i),role='user') for i in (1,2)])
            c.execute(table('activities').insert(),[dict(id=701,kind='post',created_at=datetime(2026,1,1)),dict(id=702,kind='tournament',created_at=datetime(2026,1,1))])
            c.execute(table('match_posts').insert().values(id=701,user_id='1',title='历史线下约球',preferred_date=date(2030,1,1),preferred_start=time(9),preferred_end=time(11),price=36,max_players=4,min_players=2,approval_required=False,status='open'))
            c.execute(table('match_registrations').insert().values(post_id=701,user_id='2',status='approved'))
            c.execute(table('tournaments').insert().values(id=702,user_id='1',title='历史线上比赛',start_time=datetime(2030,1,1),end_time=datetime(2030,1,2),config={},lock_venue=False,max_participants=4,current_participants=0,entry_fee=20,prizes=[],auto_title=False,registration_closed=False,roster_frozen=False,draw_version=0,published_version=0,status='open'))
            c.commit();command.upgrade(cfg,'head');c.commit();command.upgrade(cfg,'head');c.commit()
            assert c.execute(sa.text('SELECT price,payment_method FROM match_posts WHERE id=701')).one()==(36,'offline')
            assert c.execute(sa.text('SELECT entry_fee,payment_method FROM tournaments WHERE id=702')).one()==(20,'online')
            assert c.execute(sa.text('SELECT status,payment,order_id,seat_expires_at FROM match_registrations')).one()==('approved','offline',None,None)
            inspector=sa.inspect(c)
            assert any(f['constrained_columns']==['post_id'] and f['referred_table']=='match_posts' for f in inspector.get_foreign_keys('booking_orders'))
            assert any(f['constrained_columns']==['order_id'] and f['referred_table']=='booking_orders' for f in inspector.get_foreign_keys('match_registrations'))
            with pytest.raises(sa.exc.IntegrityError):c.execute(sa.text('UPDATE match_registrations SET order_id=99999'))
            c.rollback()
    finally:
        engine.dispose()
        with admin.begin() as c:c.execute(sa.text('DROP DATABASE '+name))
        admin.dispose()
