"""Require platform review for new club applications; retain legacy approvals."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql
revision = '20261008_club_approval'
down_revision = '20261008_post_address'
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    names = {c['name'] for c in sa.inspect(bind).get_columns('clubs')}
    user_id = mysql.VARCHAR(64, collation='utf8mb4_bin')
    columns = [sa.Column('approval_status', sa.String(16), nullable=False, server_default='approved'),
        sa.Column('created_by', user_id, nullable=True), sa.Column('review_reason', sa.String(256), nullable=True),
        sa.Column('reviewed_by', user_id, nullable=True), sa.Column('reviewed_at', sa.DateTime(), nullable=True)]
    for column in columns:
        if column.name not in names: op.add_column('clubs', column)
    fks = {f['name'] for f in sa.inspect(bind).get_foreign_keys('clubs')}
    for field in ('created_by', 'reviewed_by'):
        name = 'fk_club_' + field
        if name not in fks: op.create_foreign_key(name, 'clubs', 'users', [field], ['id'])
    indexes = {i['name'] for i in sa.inspect(bind).get_indexes('clubs')}
    for name, fields in [('idx_club_approval_created', ['approval_status','created_at','id']),
                         ('idx_club_creator_created', ['created_by','created_at','id'])]:
        if name not in indexes: op.create_index(name, 'clubs', fields)

    registration_columns = {c['name'] for c in sa.inspect(bind).get_columns('match_registrations')}
    if 'review_reason' not in registration_columns:
        op.add_column('match_registrations', sa.Column('review_reason', sa.String(256), nullable=True))
    for table, name, fields in [
        ('match_registrations', 'idx_post_review', ['post_id','status']),
        ('tournament_registrations', 'idx_tournament_review', ['tournament_id','approval','admission'])]:
        if name not in {i['name'] for i in sa.inspect(bind).get_indexes(table)}:
            op.create_index(name, table, fields)

def downgrade():
    raise RuntimeError('Club review history must not be discarded by automatic downgrade')
