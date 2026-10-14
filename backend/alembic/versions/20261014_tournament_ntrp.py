"""Optional NTRP requirements for tournaments, preserving existing events."""
from alembic import op
import sqlalchemy as sa
revision="20261014_tournament_ntrp"
down_revision="20261012_tournament_prizes"
branch_labels=depends_on=None

def upgrade():
    columns={c["name"] for c in sa.inspect(op.get_bind()).get_columns("tournaments")}
    if "level_required" not in columns:
        op.add_column("tournaments",sa.Column("level_required",sa.String(32),nullable=True))

def downgrade():
    raise RuntimeError("NTRP requirements must be preserved; restore a verified backup instead")
