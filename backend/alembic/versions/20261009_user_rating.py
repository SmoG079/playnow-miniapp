"""Reserve UTR and store NTRP self-assessment history without changing existing levels."""
from alembic import op
import sqlalchemy as sa

revision = "20261009_user_rating"
down_revision = "20261009_review_integrity"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("utr_rating", sa.DECIMAL(4, 2), nullable=True,
                                   comment="预留UTR等级，当前不赋值或展示"))
    op.add_column("users", sa.Column("rating_assessment", sa.JSON(), nullable=True,
                                   comment="定级问卷答案及算法版本"))
    op.add_column("users", sa.Column("rating_assessed_at", sa.DateTime(), nullable=True))


def downgrade():
    raise RuntimeError("Rating assessment history requires backup-based recovery; do not discard it by downgrade")
