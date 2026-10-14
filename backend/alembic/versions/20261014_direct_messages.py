"""Private conversations and idempotent text messages."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql
revision='20261014_direct_messages'
down_revision='20261014_tournament_ntrp'
branch_labels=depends_on=None

def user_ref(name):
    return sa.Column(name,sa.String(64).with_variant(mysql.VARCHAR(64,collation='utf8mb4_bin'),'mysql'),sa.ForeignKey('users.id'),nullable=False)

def upgrade():
    op.create_table('direct_conversations',
        sa.Column('id',sa.String(32),primary_key=True),sa.Column('pair_key',sa.String(64),nullable=False,unique=True),
        user_ref('participant_a'),user_ref('participant_b'),
        sa.Column('post_id',sa.BigInteger,sa.ForeignKey('match_posts.id'),nullable=False),
        sa.Column('read_a',sa.BigInteger,nullable=False),sa.Column('read_b',sa.BigInteger,nullable=False),
        sa.Column('last_message_id',sa.BigInteger),sa.Column('last_message_preview',sa.String(200)),
        sa.Column('last_message_at',sa.DateTime),sa.Column('created_at',sa.DateTime,nullable=False))
    op.create_index('idx_direct_a_recent','direct_conversations',['participant_a','last_message_at'])
    op.create_index('idx_direct_b_recent','direct_conversations',['participant_b','last_message_at'])
    op.create_table('direct_messages',sa.Column('id',sa.BigInteger,primary_key=True,autoincrement=True),
        sa.Column('conversation_id',sa.String(32),sa.ForeignKey('direct_conversations.id'),nullable=False),
        user_ref('sender_id'),sa.Column('client_id',sa.String(64),nullable=False),sa.Column('content',sa.Text,nullable=False),
        sa.Column('created_at',sa.DateTime,nullable=False),sa.UniqueConstraint('conversation_id','sender_id','client_id',name='uq_direct_client_message'))
    op.create_index('idx_direct_history','direct_messages',['conversation_id','id'])

def downgrade():
    raise RuntimeError('Private message history must be preserved; restore a verified backup instead')
