"""Explicit activity cities; unknown historical cities stay quarantined from discovery."""
from alembic import op
import sqlalchemy as sa
revision='20261008_discovery_city'
down_revision='20261007_activity_ids'
branch_labels=None
depends_on=None

def upgrade():
    for table in ('clubs','venues','match_posts','tournaments'):
        columns={c['name'] for c in sa.inspect(op.get_bind()).get_columns(table)}
        if 'city' not in columns: op.add_column(table,sa.Column('city',sa.String(64),nullable=True))
        for coord in (() if table=='clubs' else ('latitude','longitude')):
            if coord not in columns: op.add_column(table,sa.Column(coord,sa.DECIMAL(10,7),nullable=True))
        if table == 'venues' and 'address' not in columns:
            op.add_column(table,sa.Column('address',sa.String(256),nullable=True))
        indexes={i['name'] for i in sa.inspect(op.get_bind()).get_indexes(table)}
        name='ix_'+table+'_city'
        if name not in indexes: op.create_index(name,table,['city'])
    # No location guesses from titles, user residence or club names.

def downgrade():
    raise RuntimeError('City data must not be discarded by automatic downgrade')
