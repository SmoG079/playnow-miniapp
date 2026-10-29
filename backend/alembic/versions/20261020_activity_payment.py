"""Explicit payment channels; preserve historical post/offline and tournament/online behavior."""
from alembic import op
import sqlalchemy as sa

revision = '20261020_activity_payment'
down_revision = '20261019_tournament_owner'
branch_labels = depends_on = None


def upgrade():
    op.add_column('match_posts', sa.Column('payment_method', sa.String(16), nullable=False, server_default='offline'))
    op.add_column('tournaments', sa.Column('payment_method', sa.String(16), nullable=False, server_default='online'))
    op.add_column('booking_orders', sa.Column('post_id', sa.BigInteger(), nullable=True))
    op.create_index('ix_booking_orders_post_id', 'booking_orders', ['post_id'])
    op.create_foreign_key('fk_booking_order_post', 'booking_orders', 'match_posts', ['post_id'], ['id'])
    op.add_column('match_registrations', sa.Column('payment', sa.String(16), nullable=False, server_default='none'))
    op.add_column('match_registrations', sa.Column('order_id', sa.BigInteger(), nullable=True))
    op.add_column('match_registrations', sa.Column('seat_expires_at', sa.DateTime(), nullable=True))
    op.create_foreign_key('fk_match_registration_order', 'match_registrations', 'booking_orders', ['order_id'], ['id'])
    op.execute("UPDATE match_registrations r JOIN match_posts p ON p.id=r.post_id SET r.payment='offline' WHERE p.price>0")


def downgrade():
    raise RuntimeError('Payment records must be preserved; restore a verified backup instead')
