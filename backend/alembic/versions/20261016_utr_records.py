"""Store official UTR match statistics and age-group world rank."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "20261016_utr_records"
down_revision = "20261015_entry_teams"
branch_labels = depends_on = None


def upgrade():
    # Rating and NTRP retain their existing canonical users columns.
    op.create_table(
        "user_utr_records",
        sa.Column("user_id", mysql.VARCHAR(64, collation="utf8mb4_bin"), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("matches_played", sa.Integer(), nullable=True),
        sa.Column("wins", sa.Integer(), nullable=True),
        sa.Column("losses", sa.Integer(), nullable=True),
        sa.Column("world_rank", sa.Integer(), nullable=True),
        sa.Column("age_group", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade():
    raise RuntimeError("UTR records contain official data; restore a verified backup instead of dropping them")
