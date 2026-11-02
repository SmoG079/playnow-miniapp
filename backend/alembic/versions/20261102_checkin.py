"""Independent tournament attendance; historical registrations remain unchecked."""
from alembic import op
import sqlalchemy as sa
revision = "20261102_checkin"
down_revision = "20261102_activity_wallet"
branch_labels = depends_on = None

def upgrade():
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("tournament_registrations")}
    if "checked_in_at" not in columns:
        op.add_column("tournament_registrations", sa.Column("checked_in_at", sa.DateTime(), nullable=True))
    if "checked_in_by" not in columns:
        op.add_column("tournament_registrations", sa.Column("checked_in_by", sa.String(64), nullable=True))

def downgrade():
    raise RuntimeError("Attendance history must be preserved; do not automatically downgrade")
