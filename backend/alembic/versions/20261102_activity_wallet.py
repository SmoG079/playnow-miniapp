"""Durable activity receipts, withdrawal allocations and merchant transfer bills."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql
revision = '20261102_activity_wallet'
down_revision = '20261102_community'
branch_labels = depends_on = None


def owner():
    return sa.Column('owner_id', mysql.VARCHAR(64, collation='utf8mb4_bin'), sa.ForeignKey('users.id'), nullable=False)


def upgrade():
    op.create_table('activity_earnings', sa.Column('id',sa.BigInteger(),primary_key=True,autoincrement=True),
        sa.Column('order_id',sa.BigInteger(),sa.ForeignKey('booking_orders.id'),nullable=False,unique=True),sa.Column('fee_rate',sa.String(24)),sa.Column('unlock_at',sa.DateTime()),owner(),
        sa.Column('created_at',sa.DateTime(),nullable=False))
    op.create_index('ix_activity_earnings_owner_id','activity_earnings',['owner_id'])
    op.create_table('activity_withdrawals', sa.Column('id',sa.BigInteger(),primary_key=True,autoincrement=True),owner(),
        sa.Column('request_key',sa.String(64),nullable=False),sa.Column('allocations',sa.JSON(),nullable=False),
        sa.Column('created_at',sa.DateTime(),nullable=False),sa.UniqueConstraint('owner_id','request_key',name='uq_activity_withdrawal_request'))
    op.create_index('ix_activity_withdrawals_owner_id','activity_withdrawals',['owner_id'])
    op.create_table('activity_transfers',sa.Column('id',sa.BigInteger(),primary_key=True,autoincrement=True),
        sa.Column('withdrawal_id',sa.BigInteger(),sa.ForeignKey('activity_withdrawals.id'),nullable=False),
        sa.Column('out_bill_no',sa.String(32),nullable=False,unique=True),sa.Column('amount_cents',sa.Integer(),nullable=False),
        sa.Column('state',sa.String(24),nullable=False),sa.Column('transfer_bill_no',sa.String(64)),
        sa.Column('package_info',sa.Text()),sa.Column('request_payload',sa.JSON(),nullable=False),
        sa.Column('created_at',sa.DateTime(),nullable=False),sa.Column('updated_at',sa.DateTime(),nullable=False),
        sa.Column('completed_at',sa.DateTime()),sa.Column('error_code',sa.String(64)),
        sa.CheckConstraint('amount_cents > 0',name='ck_activity_transfer_amount'))
    op.create_index('ix_activity_transfers_withdrawal_id','activity_transfers',['withdrawal_id'])
    op.create_index('ix_activity_transfers_state','activity_transfers',['state'])
    # Snapshot historical beneficiaries without inventing paid income for offline/dev orders.
    op.execute("""INSERT INTO activity_earnings (order_id,owner_id,created_at,unlock_at)
        SELECT o.id,COALESCE(p.user_id,t.user_id),UTC_TIMESTAMP(),
        CASE WHEN o.business_type='post'
            THEN DATE_ADD(DATE_SUB(TIMESTAMP(p.preferred_date,p.preferred_end),INTERVAL 8 HOUR),INTERVAL 24 HOUR)
            ELSE DATE_ADD(t.end_time,INTERVAL 24 HOUR) END FROM booking_orders o
        LEFT JOIN match_posts p ON o.business_type='post' AND p.id=o.post_id
        LEFT JOIN tournaments t ON o.business_type='tournament' AND t.id=o.tournament_id
        WHERE o.wx_transaction_id IS NOT NULL AND o.wx_transaction_id NOT LIKE 'dev\\_%'
        AND o.status IN ('paid','completed','refunding','refunded') AND COALESCE(p.user_id,t.user_id) IS NOT NULL""")


def downgrade():
    raise RuntimeError('Preserve financial records; restore a verified backup instead')
