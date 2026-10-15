"""Convert the obsolete daily-price rule name once."""
from alembic import op
import sqlalchemy as sa

revision = "20261015_price_rule_names"
down_revision = "20261015_remove_legacy"
branch_labels = depends_on = None


def canonical_rules(rules):
    if rules is None:
        return None
    if not isinstance(rules, list) or any(not isinstance(rule, dict) for rule in rules):
        raise RuntimeError("Invalid court pricing rules; repair the source data before migration")
    return [dict(rule, type="daily_time") if rule.get("type") == "time_range" else rule for rule in rules]


def upgrade():
    bind = op.get_bind()
    venues = sa.Table("venues", sa.MetaData(), autoload_with=bind)
    for ident, rules in bind.execute(sa.select(venues.c.id, venues.c.price_rules)):
        normalized = canonical_rules(rules)
        if normalized != rules:
            bind.execute(venues.update().where(venues.c.id == ident).values(price_rules=normalized))


def downgrade():
    raise RuntimeError("Price rules were normalized; restore a verified backup instead")
