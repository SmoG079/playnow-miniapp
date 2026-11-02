"""Separate ordinary community membership from administrator permissions."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql
revision = "20261102_community"
down_revision = "20261020_activity_payment"
branch_labels = depends_on = None

def upgrade():
    op.add_column("clubs", sa.Column("logo_image",sa.String(512),nullable=True))
    op.create_table("community_members",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("club_id", sa.BigInteger(), sa.ForeignKey("clubs.id"), nullable=False),
        sa.Column("user_id", mysql.VARCHAR(64, collation="utf8mb4_bin"), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("club_id", "user_id", name="uq_community_member"))

    op.execute("INSERT INTO community_members (club_id,user_id,created_at) SELECT club_id,user_id,COALESCE(created_at,UTC_TIMESTAMP()) FROM club_members")

def downgrade():
    raise RuntimeError("Preserve membership records; restore a verified backup instead")
