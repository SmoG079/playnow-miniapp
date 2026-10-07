"""Compatibility helpers for historical migrations with overlapping columns."""
from alembic import op
import sqlalchemy as sa


def add_column_if_missing(table_name, column):
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table_name)}
    if column.name not in existing:
        op.add_column(table_name, column)
