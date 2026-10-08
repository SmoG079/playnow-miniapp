"""Allow personal tournaments and their payment orders without a host club."""
from alembic import op
import sqlalchemy as sa
revision = '20261008_optional_host'
down_revision = '20261008_club_approval'
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    for table in ('tournaments', 'booking_orders'):
        column = next(c for c in sa.inspect(bind).get_columns(table) if c['name'] == 'club_id')
        if not column['nullable']:
            op.alter_column(table, 'club_id', existing_type=column['type'], nullable=True)

def downgrade():
    raise RuntimeError('Personal tournaments must not lose their hostless records')
