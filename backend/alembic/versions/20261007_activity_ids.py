"""One shared AUTO_INCREMENT activity primary key, with typed child tables."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql
from activity_backfill import backfill, TOURNAMENT_REFERENCES

revision = "20261007_activity_ids"
down_revision = "20261007_post_history"
branch_labels = None
depends_on = None

REFERENCES = {**{table: ("tournament_id", "tournaments") for table in TOURNAMENT_REFERENCES},
              "match_registrations": ("post_id", "match_posts"),
              "comments": ("post_id", "match_posts")}


def upgrade():
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    if connection.dialect.name != "mysql":
        raise RuntimeError("Activity ID migration requires an isolated MySQL rehearsal")
    if connection.dialect.server_version_info < (8, 0, 16):
        raise RuntimeError("MySQL 8.0.16+ with enforced CHECK constraints is required")
    maximum = connection.scalar(sa.text("SELECT GREATEST(COALESCE((SELECT MAX(id) FROM match_posts),0), COALESCE((SELECT MAX(id) FROM tournaments),0))"))
    count = connection.scalar(sa.text("SELECT (SELECT COUNT(*) FROM match_posts) + (SELECT COUNT(*) FROM tournaments)"))
    invalid = connection.scalar(sa.text("SELECT (SELECT COUNT(*) FROM match_posts WHERE id <= 0) + (SELECT COUNT(*) FROM tournaments WHERE id <= 0)"))
    if invalid or maximum + count > 9007199254740991:
        raise RuntimeError("Historical IDs cannot be safely converted")
    # This migration must run with API and workers stopped. Reject unreviewed references
    # before temporarily removing incoming FKs to convert conflicting primary keys.
    incoming = []
    for table in inspector.get_table_names():
        for fk in inspector.get_foreign_keys(table):
            if fk["referred_table"] not in ("match_posts", "tournaments"):
                continue
            if (table not in REFERENCES or fk["constrained_columns"] != [REFERENCES[table][0]]
                    or fk["referred_columns"] != ["id"]
                    or (fk.get("options", {}).get("ondelete") or "RESTRICT") not in ("RESTRICT", "NO ACTION")
                    or (fk.get("options", {}).get("onupdate") or "RESTRICT") not in ("RESTRICT", "NO ACTION")):
                raise RuntimeError(f"Unreviewed activity foreign key: {table}.{fk['name']}")
            incoming.append((table, fk["name"]))
    for table, (column, parent) in REFERENCES.items():
        count = connection.scalar(sa.text(f"SELECT COUNT(*) FROM {table} c LEFT JOIN {parent} p ON p.id=c.{column} WHERE c.{column} IS NOT NULL AND p.id IS NULL"))
        if count:
            raise RuntimeError(f"Orphan activity references in {table}")

    if "activities" not in inspector.get_table_names():
        op.create_table("activities",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("kind", mysql.VARCHAR(16, charset="ascii", collation="ascii_bin"), nullable=False),
            sa.Column("legacy_id", sa.BigInteger(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("id", "kind", name="uq_activity_id_kind"),
            sa.UniqueConstraint("kind", "legacy_id", name="uq_activity_legacy"),
            sa.CheckConstraint("kind IN ('post', 'tournament')", name="ck_activity_kind"),
        )
    for table, kind in (("match_posts", "post"), ("tournaments", "tournament")):
        if "activity_kind" not in {c["name"] for c in sa.inspect(connection).get_columns(table)}:
            op.add_column(table, sa.Column("activity_kind", mysql.VARCHAR(16, charset="ascii", collation="ascii_bin"), nullable=False, server_default=kind))
    for table, name in incoming:
        op.drop_constraint(name, table, type_="foreignkey")
    for table in ("match_posts", "tournaments"):
        column = next(c for c in sa.inspect(connection).get_columns(table) if c["name"] == "id")
        if column.get("autoincrement"):
            op.alter_column(table, "id", existing_type=sa.BigInteger(), existing_nullable=False, autoincrement=False)
    backfill(connection)
    # Commit conversion by restoring constraints (MySQL DDL commits), then enforce type.
    for table, (column, parent) in REFERENCES.items():
        existing = sa.inspect(connection).get_foreign_keys(table)
        if not any(f["referred_table"] == parent and f["constrained_columns"] == [column] for f in existing):
            op.create_foreign_key(f"fk_{table}_activity_parent", table, parent, [column], ["id"])
    for table, kind, prefix in (("match_posts", "post", "post"), ("tournaments", "tournament", "tournament")):
        fk_name = f"fk_{prefix}_activity"
        if not any(f["name"] == fk_name for f in sa.inspect(connection).get_foreign_keys(table)):
            op.create_foreign_key(fk_name, table, "activities", ["id", "activity_kind"], ["id", "kind"])
        check_name = f"ck_{prefix}_activity_kind"
        if not any(c["name"] == check_name for c in sa.inspect(connection).get_check_constraints(table)):
            op.create_check_constraint(check_name, table, f"activity_kind = '{kind}'")
    for table, name in (("match_registrations", "idx_post_registration_user_created"),
                        ("tournament_registrations", "idx_tournament_registration_user_created")):
        if not any(i["name"] == name for i in sa.inspect(connection).get_indexes(table)):
            op.create_index(name, table, ["user_id", "created_at", "id"])


def downgrade():
    raise RuntimeError("Shared IDs and legacy mappings require verified backup recovery; destructive downgrade refused")
