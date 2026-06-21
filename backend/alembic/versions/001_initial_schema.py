"""initial schema

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-06-12 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001_initial_schema'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all base tables."""
    op.create_table(
        'users',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('openid', sa.String(64), nullable=False),
        sa.Column('unionid', sa.String(64), nullable=True),
        sa.Column('nickname', sa.String(64), nullable=True),
        sa.Column('avatar_url', sa.String(512), nullable=True),
        sa.Column('phone', sa.String(20), nullable=True),
        sa.Column('ntrp_level', sa.DECIMAL(2, 1), nullable=True, comment='NTRP网球等级'),
        sa.Column('role', sa.Enum('user', 'club_admin', 'platform_admin', name='userrole'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('openid'),
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci',
    )

    op.create_table(
        'clubs',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(128), nullable=False),
        sa.Column('sport_types', sa.JSON(), nullable=True, comment='["badminton","basketball"]'),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('rules', sa.Text(), nullable=True, comment='场地规则'),
        sa.Column('cover_image', sa.String(512), nullable=True),
        sa.Column('images', sa.JSON(), nullable=True),
        sa.Column('documents', sa.JSON(), nullable=True, comment='PDF文件列表 [{name, url, size}]'),
        sa.Column('address', sa.String(256), nullable=True),
        sa.Column('latitude', sa.DECIMAL(10, 7), nullable=True),
        sa.Column('longitude', sa.DECIMAL(10, 7), nullable=True),
        sa.Column('contact_phone', sa.String(20), nullable=True),
        sa.Column('split_ratio', sa.DECIMAL(4, 3), nullable=False, server_default='0.100'),
        sa.Column('sub_merchant_id', sa.String(64), nullable=True),
        sa.Column('status', sa.Enum('active', 'inactive', name='clubstatus'), nullable=False, server_default='active'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci',
    )

    op.create_table(
        'club_members',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('club_id', sa.BigInteger(), sa.ForeignKey('clubs.id'), nullable=False),
        sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('role', sa.Enum('owner', 'admin', name='clubmemberrole'), nullable=False, server_default='admin'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('club_id', 'user_id', name='uq_club_user'),
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci',
    )

    op.create_table(
        'notifications',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('type', sa.Enum('booking', 'match', 'tournament', 'system', name='notificationtype'), nullable=False),
        sa.Column('title', sa.String(128), nullable=True),
        sa.Column('content', sa.String(512), nullable=True),
        sa.Column('ref_id', sa.BigInteger(), nullable=True),
        sa.Column('ref_type', sa.String(32), nullable=True),
        sa.Column('is_read', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('idx_user_read', 'user_id', 'is_read'),
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci',
    )

    op.create_table(
        'venues',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('club_id', sa.BigInteger(), sa.ForeignKey('clubs.id'), nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('sport_type', sa.String(32), nullable=False),
        sa.Column('price_per_hour', sa.DECIMAL(10, 2), nullable=False),
        sa.Column('max_capacity', sa.Integer(), nullable=False, server_default='4'),
        sa.Column('cover_image', sa.String(512), nullable=True),
        sa.Column('status', sa.Enum('active', 'maintenance', 'closed', name='venuestatus'), nullable=False, server_default='active'),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('idx_club_id', 'club_id'),
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci',
    )

    op.create_table(
        'venue_time_slots',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('venue_id', sa.BigInteger(), sa.ForeignKey('venues.id'), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('start_time', sa.Time(), nullable=False),
        sa.Column('end_time', sa.Time(), nullable=False),
        sa.Column('price_override', sa.DECIMAL(10, 2), nullable=True),
        sa.Column('status', sa.Enum('available', 'locked', 'booked', 'maintenance', name='slotstatus'), nullable=False, server_default='available'),
        sa.Column('locked_by', sa.BigInteger(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('locked_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('venue_id', 'date', 'start_time', name='uq_slot'),
        sa.Index('idx_venue_date', 'venue_id', 'date'),
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci',
    )

    op.create_table(
        'booking_orders',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('order_no', sa.String(32), nullable=False),
        sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('venue_id', sa.BigInteger(), sa.ForeignKey('venues.id'), nullable=False),
        sa.Column('slot_id', sa.BigInteger(), sa.ForeignKey('venue_time_slots.id'), nullable=False),
        sa.Column('club_id', sa.BigInteger(), sa.ForeignKey('clubs.id'), nullable=False),
        sa.Column('amount', sa.DECIMAL(10, 2), nullable=False),
        sa.Column('status', sa.Enum('pending', 'paid', 'cancelled', 'refunding', 'refunded', 'completed', name='orderstatus'), nullable=False, server_default='pending'),
        sa.Column('payment_time', sa.DateTime(), nullable=True),
        sa.Column('wx_transaction_id', sa.String(64), nullable=True),
        sa.Column('cancel_reason', sa.String(256), nullable=True),
        sa.Column('cancel_time', sa.DateTime(), nullable=True),
        sa.Column('refund_amount', sa.DECIMAL(10, 2), nullable=True),
        sa.Column('refund_id', sa.String(64), nullable=True),
        sa.Column('refund_time', sa.DateTime(), nullable=True),
        sa.Column('refund_status', sa.String(32), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('order_no'),
        sa.Index('idx_user_id', 'user_id'),
        sa.Index('idx_club_id', 'club_id'),
        sa.Index('idx_status', 'status'),
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci',
    )

    op.create_table(
        'settlement_records',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('order_id', sa.BigInteger(), sa.ForeignKey('booking_orders.id'), nullable=False),
        sa.Column('total_amount', sa.DECIMAL(10, 2), nullable=False),
        sa.Column('platform_amount', sa.DECIMAL(10, 2), nullable=False),
        sa.Column('club_amount', sa.DECIMAL(10, 2), nullable=False),
        sa.Column('split_ratio', sa.DECIMAL(4, 3), nullable=False, server_default='0.100'),
        sa.Column('wx_split_order_no', sa.String(64), nullable=True),
        sa.Column('status', sa.Enum('pending', 'processing', 'completed', 'failed', name='settlementstatus'), nullable=False, server_default='pending'),
        sa.Column('fail_reason', sa.String(512), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('idx_order_id', 'order_id'),
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci',
    )

    op.create_table(
        'match_posts',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('club_id', sa.BigInteger(), sa.ForeignKey('clubs.id'), nullable=False),
        sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('title', sa.String(256), nullable=False),
        sa.Column('sport_type', sa.String(32), nullable=True),
        sa.Column('preferred_date', sa.Date(), nullable=True),
        sa.Column('preferred_start', sa.Time(), nullable=True),
        sa.Column('preferred_end', sa.Time(), nullable=True),
        sa.Column('players_needed', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('level_required', sa.String(32), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('documents', sa.JSON(), nullable=True),
        sa.Column('venue_id', sa.BigInteger(), sa.ForeignKey('venues.id'), nullable=True),
        sa.Column('booking_id', sa.BigInteger(), sa.ForeignKey('booking_orders.id'), nullable=True),
        sa.Column('group_chat_id', sa.String(64), nullable=True),
        sa.Column('status', sa.Enum('open', 'closed', 'full', name='matchpoststatus'), nullable=False, server_default='open'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('idx_club_status', 'club_id', 'status'),
        sa.Index('idx_preferred_date', 'preferred_date'),
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci',
    )

    op.create_table(
        'match_registrations',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('post_id', sa.BigInteger(), sa.ForeignKey('match_posts.id'), nullable=False),
        sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('message', sa.String(256), nullable=True),
        sa.Column('status', sa.Enum('pending', 'approved', 'rejected', name='registrationstatus'), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('post_id', 'user_id', name='uq_post_user'),
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci',
    )

    op.create_table(
        'tournaments',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('club_id', sa.BigInteger(), sa.ForeignKey('clubs.id'), nullable=False),
        sa.Column('title', sa.String(256), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('sport_type', sa.String(32), nullable=True),
        sa.Column('start_time', sa.DateTime(), nullable=False),
        sa.Column('end_time', sa.DateTime(), nullable=False),
        sa.Column('venue_id', sa.BigInteger(), sa.ForeignKey('venues.id'), nullable=True),
        sa.Column('lock_venue', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('max_participants', sa.Integer(), nullable=True),
        sa.Column('current_participants', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('entry_fee', sa.DECIMAL(10, 2), nullable=False, server_default='0.00'),
        sa.Column('cover_image', sa.String(512), nullable=True),
        sa.Column('group_chat_id', sa.String(64), nullable=True),
        sa.Column('status', sa.Enum('draft', 'open', 'ongoing', 'finished', 'cancelled', name='tournamentstatus'), nullable=False, server_default='draft'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('idx_status_time', 'status', 'start_time'),
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci',
    )

    op.create_table(
        'tournament_registrations',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('tournament_id', sa.BigInteger(), sa.ForeignKey('tournaments.id'), nullable=False),
        sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('order_id', sa.BigInteger(), sa.ForeignKey('booking_orders.id'), nullable=True),
        sa.Column('status', sa.Enum('registered', 'confirmed', 'cancelled', name='tournamentregstatus'), nullable=False, server_default='registered'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tournament_id', 'user_id', name='uq_tournament_user'),
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci',
    )


def downgrade() -> None:
    """Drop all base tables."""
    op.drop_table('tournament_registrations')
    op.drop_table('tournaments')
    op.drop_table('match_registrations')
    op.drop_table('match_posts')
    op.drop_table('settlement_records')
    op.drop_table('booking_orders')
    op.drop_table('venue_time_slots')
    op.drop_table('venues')
    op.drop_table('notifications')
    op.drop_table('club_members')
    op.drop_table('clubs')
    op.drop_table('users')
