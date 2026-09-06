"""Allow free match posts without a club.

Revision ID: 20260904_free_posts
Revises: 66096adfc14a
"""
from alembic import op
import sqlalchemy as sa

revision = '20260904_free_posts'
down_revision = '66096adfc14a'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('match_posts', 'club_id', existing_type=sa.BigInteger(), nullable=True)


def downgrade():
    count = op.get_bind().execute(sa.text('SELECT COUNT(*) FROM match_posts WHERE club_id IS NULL')).scalar()
    if count:
        raise RuntimeError('Cannot restore NOT NULL while free match posts exist; preserve these records first.')
    op.alter_column('match_posts', 'club_id', existing_type=sa.BigInteger(), nullable=False)
