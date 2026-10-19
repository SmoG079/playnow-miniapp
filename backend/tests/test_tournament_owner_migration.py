"""Real MySQL migration: canonical owner backfill, foreign key, and rejection before DDL."""
import os
import uuid
from pathlib import Path
from datetime import datetime
import pytest
import sqlalchemy as sa
from sqlalchemy.engine import make_url
from alembic import command
from alembic.config import Config


@pytest.mark.parametrize('scenario',['empty','created','missing'])
@pytest.mark.skipif(not os.environ.get('TOURNAMENT_MYSQL_TEST_DATABASE_URL'),reason='Explicit disposable local MySQL required')
def test_tournament_owner_full_migration(scenario):
    source=make_url(os.environ['TOURNAMENT_MYSQL_TEST_DATABASE_URL'])
    if source.host not in ('localhost','127.0.0.1') or not (source.database=='test_db' or source.database.startswith('playnow_test_')):
        raise RuntimeError('Only isolated local MySQL may run ownership migration tests')
    name='playnow_migration_owner_'+uuid.uuid4().hex[:10]
    admin=sa.create_engine(source.set(drivername='mysql+pymysql',database=None),hide_parameters=True)
    with admin.begin() as c:c.execute(sa.text('CREATE DATABASE '+name+' CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci'))
    database=sa.create_engine(source.set(drivername='mysql+pymysql',database=name),hide_parameters=True)
    try:
        with database.connect() as c:
            backend=Path(__file__).resolve().parents[1]
            cfg=Config(str(backend/'alembic.ini'));cfg.set_main_option('script_location',str(backend/'alembic'));cfg.attributes['connection']=c
            command.upgrade(cfg,'20261016_utr_records');c.commit()
            if scenario!='empty':
                meta=sa.MetaData()
                users=sa.Table('users',meta,autoload_with=c)
                c.execute(users.insert(),[dict(id=str(i),openid='owner-test-'+str(i),public_id='owner-public-'+str(i),role='user') for i in (1,2)])
                activity=sa.Table('activities',meta,autoload_with=c);c.execute(activity.insert().values(id=501,kind='tournament',created_at=datetime(2026,1,1)))
                events=sa.Table('tournaments',meta,autoload_with=c)
                c.execute(events.insert().values(id=501,title='original event',start_time=datetime(2030,1,1),end_time=datetime(2030,1,2),config={'discipline':'singles','format':'knockout','group_count':1,'pairing':None},
                    lock_venue=False,max_participants=4,current_participants=0,entry_fee=1,prizes=[],auto_title=False,registration_closed=False,roster_frozen=False,draw_version=0,published_version=0,status='open'))
                if scenario=='created':
                    audits=sa.Table('tournament_audits',meta,autoload_with=c)
                    c.execute(audits.insert(),[dict(tournament_id=501,actor_id='2',action='created',detail={},created_at=datetime(2026,1,1)),dict(tournament_id=501,actor_id='1',action='updated',detail={},created_at=datetime(2026,1,2))])
                c.commit()
            if scenario=='missing':
                with pytest.raises(RuntimeError,match='organizers must be assigned'):command.upgrade(cfg,'head')
                c.rollback()
                assert 'user_id' not in {x['name'] for x in sa.inspect(c).get_columns('tournaments')}
                assert c.scalar(sa.text('SELECT version_num FROM alembic_version'))=='20261016_utr_records'
                return
            command.upgrade(cfg,'head');c.commit();command.upgrade(cfg,'head');c.commit()
            inspector=sa.inspect(c)
            assert next(x for x in inspector.get_columns('tournaments') if x['name']=='user_id')['nullable'] is False
            assert any(f['constrained_columns']==['user_id'] and f['referred_table']=='users' for f in inspector.get_foreign_keys('tournaments'))
            if scenario=='created':
                assert c.execute(sa.text('SELECT user_id,title,entry_fee FROM tournaments WHERE id=501')).one()==('2','original event',1)
                assert c.scalar(sa.text("SELECT actor_id FROM tournament_audits WHERE action='created'"))=='2'
                with pytest.raises(sa.exc.IntegrityError):c.execute(sa.text("UPDATE tournaments SET user_id='unknown' WHERE id=501"))
                c.rollback()
    finally:
        database.dispose()
        with admin.begin() as c:c.execute(sa.text('DROP DATABASE '+name))
        admin.dispose()
