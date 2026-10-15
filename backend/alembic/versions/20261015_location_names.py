"""Store the map location name separately from the street address."""
from alembic import op
import sqlalchemy as sa
revision = "20261015_location_names"
down_revision = "20261015_price_rule_names"
branch_labels = depends_on = None


def upgrade():
    bind = op.get_bind()
    for table in ("match_posts", "tournaments"):
        op.add_column(table, sa.Column("location_name", sa.String(256), nullable=False, server_default=""))
        activity = sa.Table(table, sa.MetaData(), autoload_with=bind)
        venue = sa.Table("venues", sa.MetaData(), autoload_with=bind)
        name = sa.select(venue.c.name).where(venue.c.id == activity.c.venue_id).scalar_subquery()
        bind.execute(activity.update().where(activity.c.venue_id.is_not(None)).values(location_name=sa.func.coalesce(name, "")))


def downgrade():
    raise RuntimeError("Location names would be lost; restore a verified backup instead")
