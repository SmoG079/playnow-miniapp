"""Reconcile the schema against a frozen snapshot and preserve legacy columns."""
from alembic import op
from schema_alignment import apply_alignment

revision = "20261007_schema_alignment"
down_revision = "20260904_free_posts"
branch_labels = None
depends_on = None


def upgrade():
    apply_alignment(op.get_bind())


def downgrade():
    raise RuntimeError("Schema alignment has no lossless automatic downgrade; restore a verified backup")
