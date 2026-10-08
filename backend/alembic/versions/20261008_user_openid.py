"""Use WeChat openid as the user primary key and migrate every user reference."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql
import json
import os

revision = '20261008_user_openid'
down_revision = '20261008_discovery_city'
branch_labels = None
depends_on = None
USER_ID = mysql.VARCHAR(64, collation='utf8mb4_bin')


def remap_json(value, mapping, key=None):
    if isinstance(value, dict):
        return {k: remap_json(v, mapping, k) for k, v in value.items()}
    if key in ('user_id', 'partner_user_id', 'actor_id', 'created_by', 'locked_by') and value is not None:
        return mapping[str(value)]
    if isinstance(value, list):
        if key in ('users', 'user_ids'):
            return [mapping[str(v)] for v in value]
        return [remap_json(v, mapping) for v in value]
    return value


def upgrade():
    conn = op.get_bind()
    if conn.dialect.name != 'mysql':
        raise RuntimeError('User primary-key conversion must be rehearsed and applied on MySQL')
    inspector = sa.inspect(conn)
    if 'user_id_migrations' in inspector.get_table_names():
        raise RuntimeError('Partially applied user migration requires backup-based recovery; do not retry blindly')
    rows = conn.execute(sa.text('SELECT id,openid FROM users')).all()
    mapping = {str(ident): openid for ident, openid in rows}
    if any(not openid or len(openid) > 64 for openid in mapping.values()) or len(set(mapping.values())) != len(mapping):
        raise RuntimeError('Missing or duplicate WeChat openid must be resolved before migration')
    references = []
    for table in inspector.get_table_names():
        for fk in inspector.get_foreign_keys(table):
            if fk['referred_table'] == 'users':
                if fk['referred_columns'] != ['id'] or len(fk['constrained_columns']) != 1:
                    raise RuntimeError('Unsupported composite user foreign key')
                column = fk['constrained_columns'][0]
                nullable = next(c['nullable'] for c in inspector.get_columns(table) if c['name'] == column)
                references.append((table, column, nullable, fk))
                missing = conn.execute(sa.text(f'SELECT 1 FROM `{table}` t LEFT JOIN users u ON t.`{column}`=u.id WHERE t.`{column}` IS NOT NULL AND u.id IS NULL LIMIT 1')).first()
                if missing:
                    raise RuntimeError(f'Orphan user reference in {table}.{column}')
    json_updates = []
    for table, column in (('tournament_draws','snapshot'),('tournament_audits','detail')):
        for ident, value in conn.execute(sa.text(f'SELECT id,`{column}` FROM `{table}`')):
            if isinstance(value, str): value = json.loads(value)
            json_updates.append((table,column,ident,remap_json(value,mapping)))
    # Existing booking locks carry the old user ID. Probe Redis before any DDL,
    # then preserve each remaining lock's TTL while replacing only its owner.
    redis_client = None
    locked = conn.execute(sa.text('SELECT 1 FROM venue_time_slots WHERE locked_by IS NOT NULL LIMIT 1')).first()
    if locked:
        import redis
        if not os.environ.get('REDIS_URL'):
            raise RuntimeError('Explicit Redis URL required to migrate active booking lock owners')
        redis_client = redis.Redis.from_url(os.environ['REDIS_URL'], decode_responses=True)
        redis_client.ping()
    op.create_table('user_id_migrations',
        sa.Column('legacy_id',sa.BigInteger(),primary_key=True,autoincrement=False),
        sa.Column('openid',USER_ID,nullable=False))
    if rows:
        conn.execute(sa.text('INSERT INTO user_id_migrations(legacy_id,openid) VALUES (:legacy_id,:openid)'),
                     [dict(legacy_id=ident,openid=openid) for ident,openid in rows])
    for table, column, nullable, fk in references:
        op.drop_constraint(fk['name'],table,type_='foreignkey')
        op.alter_column(table,column,type_=USER_ID,existing_type=sa.BigInteger(),existing_nullable=nullable)
    op.alter_column('users','id',type_=USER_ID,existing_type=sa.BigInteger(),existing_nullable=False,autoincrement=False)
    op.alter_column('users','openid',type_=USER_ID,existing_type=sa.String(64),existing_nullable=False)
    for table,column,nullable,fk in references:
        conn.execute(sa.text(f'UPDATE `{table}` t JOIN user_id_migrations m ON t.`{column}`=CAST(m.legacy_id AS CHAR) SET t.`{column}`=m.openid'))
    conn.execute(sa.text("UPDATE users SET id=CONCAT('migrating_user_',id)"))
    conn.execute(sa.text('UPDATE users SET id=openid'))
    for table,column,ident,value in json_updates:
        conn.execute(sa.text(f'UPDATE `{table}` SET `{column}`=:value WHERE id=:id'),dict(value=json.dumps(value,ensure_ascii=False),id=ident))
    for table,column,nullable,fk in references:
        options = {k:v for k,v in fk.get('options',{}).items() if k in ('onupdate','ondelete')}
        op.create_foreign_key(fk['name'],table,'users',[column],['id'],**options)
    op.create_foreign_key('fk_user_id_migrations_user','user_id_migrations','users',['openid'],['id'])
    if redis_client:
        try:
            for key in redis_client.scan_iter(match='slot:*'):
                old = redis_client.get(key)
                if old in mapping:
                    redis_client.eval("if redis.call('GET',KEYS[1]) == ARGV[1] then return redis.call('SET',KEYS[1],ARGV[2],'KEEPTTL') end return nil",1,key,old,mapping[old])
        finally: redis_client.close()
    if conn.execute(sa.text('SELECT 1 FROM users WHERE BINARY id <> BINARY openid LIMIT 1')).first():
        raise RuntimeError('User ID conversion verification failed')


def downgrade():
    raise RuntimeError('User identity conversion requires backup-based recovery, not automatic downgrade')
