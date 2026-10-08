"""Persist map-selected meeting addresses separately from club locations."""
from alembic import op
import sqlalchemy as sa
revision = '20261008_post_address'
down_revision = '20261008_user_openid'
branch_labels = None
depends_on = None

def upgrade():
    columns = {c['name'] for c in sa.inspect(op.get_bind()).get_columns('match_posts')}
    if 'address' not in columns:
        op.add_column('match_posts', sa.Column('address', sa.String(256), nullable=True))
    # Only linked venues have an authoritative historical address.
    op.execute(sa.text('UPDATE match_posts p JOIN venues v ON p.venue_id=v.id SET p.address=v.address WHERE p.address IS NULL AND v.address IS NOT NULL'))

def downgrade():
    raise RuntimeError('Meeting addresses must not be discarded by automatic downgrade')
