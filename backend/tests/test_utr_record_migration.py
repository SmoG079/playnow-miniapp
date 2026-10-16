"""Exercise new UTR storage on a real isolated MySQL previous/empty schema."""
import os
import uuid
from decimal import Decimal
from pathlib import Path
import pytest
import sqlalchemy as sa
from sqlalchemy.engine import make_url
from alembic import command
from alembic.config import Config


@pytest.mark.parametrize('previous', [False, True])
@pytest.mark.skipif(not os.environ.get('UTR_MYSQL_TEST_DATABASE_URL'), reason='Explicit disposable local MySQL required')
def test_utr_schema_upgrade_preserves_values(previous):
    source = make_url(os.environ['UTR_MYSQL_TEST_DATABASE_URL'])
    if source.host not in ('localhost', '127.0.0.1') or not (source.database == 'test_db' or source.database.startswith('playnow_test_')):
        raise RuntimeError('UTR migration tests require an isolated local MySQL database')
    name = 'playnow_migration_utr_' + uuid.uuid4().hex[:10]
    admin = sa.create_engine(source.set(drivername='mysql+pymysql', database=None), hide_parameters=True)
    with admin.begin() as c: c.execute(sa.text('CREATE DATABASE ' + name + ' CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci'))
    database = sa.create_engine(source.set(drivername='mysql+pymysql', database=name), hide_parameters=True)
    try:
        with database.connect() as c:
            backend = Path(__file__).resolve().parents[1]
            cfg = Config(str(backend/'alembic.ini')); cfg.set_main_option('script_location',str(backend/'alembic')); cfg.attributes['connection'] = c
            if previous:
                command.upgrade(cfg,'20261015_entry_teams'); c.commit()
                c.execute(sa.text("INSERT INTO users(id,openid,public_id,nickname,role,ntrp_level,utr_rating) VALUES ('utr-migration','utr-migration','utr-public','Existing user','user',4.5,3.40)")); c.commit()
            command.upgrade(cfg,'head'); c.commit()
            columns = {x['name']:x for x in sa.inspect(c).get_columns('user_utr_records')}
            for key in ('matches_played','wins','losses','world_rank','age_group'): assert columns[key]['nullable']
            assert c.scalar(sa.text('SELECT COUNT(*) FROM user_utr_records')) == 0
            if previous:
                assert tuple(c.execute(sa.text("SELECT role,ntrp_level,utr_rating FROM users WHERE id='utr-migration'")).one()) == ('user',Decimal('4.5'),Decimal('3.40'))
                c.execute(sa.text("INSERT INTO user_utr_records(user_id,matches_played,wins,losses,world_rank,age_group,created_at,updated_at) VALUES ('utr-migration',1,0,1,329791,'22–29',UTC_TIMESTAMP(),UTC_TIMESTAMP())")); c.commit()
            command.upgrade(cfg,'head'); c.commit()
            if previous:
                assert tuple(c.execute(sa.text('SELECT matches_played,wins,losses,world_rank,age_group FROM user_utr_records')).one()) == (1,0,1,329791,'22–29')
                c.execute(sa.text('UPDATE user_utr_records SET wins=NULL,world_rank=NULL')); c.commit()
                assert tuple(c.execute(sa.text('SELECT wins,world_rank FROM user_utr_records')).one()) == (None,None)
    finally:
        database.dispose()
        with admin.begin() as c: c.execute(sa.text('DROP DATABASE '+name))
        admin.dispose()
