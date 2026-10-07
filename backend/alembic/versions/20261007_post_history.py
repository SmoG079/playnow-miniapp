"""Retain cancelled post registrations instead of deleting their history."""
from alembic import op
import sqlalchemy as sa

revision = "20261007_post_history"
down_revision = "20261007_tournaments"
branch_labels = None
depends_on = None

old_type = sa.Enum("pending", "approved", "rejected", name="registrationstatus")
new_type = sa.Enum("pending", "approved", "rejected", "cancelled", name="registrationstatus")


def upgrade():
    op.alter_column("match_registrations", "status", existing_type=old_type,
                    type_=new_type, existing_nullable=False)


def downgrade():
    count = op.get_bind().scalar(sa.text(
        "SELECT COUNT(*) FROM match_registrations WHERE status = 'cancelled'"
    ))
    if count:
        raise RuntimeError("Cannot downgrade while cancelled registration history exists")
    op.alter_column("match_registrations", "status", existing_type=new_type,
                    type_=old_type, existing_nullable=False)
