"""Optional structured prizes; preserve legacy prize text."""
from alembic import op
import sqlalchemy as sa
revision = "20261012_tournament_prizes"
down_revision = "20261009_user_rating"
branch_labels = depends_on = None


def upgrade():
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("tournaments")}
    if "prizes" not in columns:
        op.add_column("tournaments", sa.Column("prizes", sa.JSON(), nullable=True))


def downgrade():
    raise RuntimeError("Structured prize data must be preserved; restore a verified backup instead")
