"""add refund fields and tables

Revision ID: add_refund_fields
Revises: 
Create Date: 2025-06-12

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = 'add_refund_fields'
down_revision = '001_initial_schema'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add refund fields to booking_orders
    op.add_column('booking_orders', sa.Column('refund_id', sa.String(64), nullable=True))
    op.add_column('booking_orders', sa.Column('refund_time', sa.DateTime(), nullable=True))
    op.add_column('booking_orders', sa.Column('refund_status', sa.String(32), nullable=True, server_default='pending'))
    
    # Create refund_records table
    op.create_table(
        'refund_records',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('order_id', sa.BigInteger(), sa.ForeignKey('booking_orders.id'), nullable=False),
        sa.Column('out_refund_no', sa.String(32), nullable=False, unique=True),
        sa.Column('wx_refund_id', sa.String(64), nullable=True),
        sa.Column('amount', sa.DECIMAL(10, 2), nullable=False),
        sa.Column('reason', sa.String(256), nullable=True),
        sa.Column('status', sa.String(32), nullable=True, server_default='pending'),
        sa.Column('created_at', sa.DateTime(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('idx_refund_order', 'order_id'),
    )
    
    # Create payment_logs table
    op.create_table(
        'payment_logs',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('order_id', sa.BigInteger(), nullable=True),
        sa.Column('type', sa.String(32), nullable=True),
        sa.Column('event_type', sa.String(64), nullable=True),
        sa.Column('raw_data', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('idx_payment_order', 'order_id'),
    )


def downgrade() -> None:
    op.drop_table('payment_logs')
    op.drop_table('refund_records')
    op.drop_column('booking_orders', 'refund_status')
    op.drop_column('booking_orders', 'refund_time')
    op.drop_column('booking_orders', 'refund_id')
