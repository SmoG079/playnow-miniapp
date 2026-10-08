"""MySQL integration checks against disposable empty/restored databases.

The harness must provide three MIGRATION_*_DATABASE_URL variables. Production
database names are deliberately refused. No customer rows are printed.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.engine import make_url

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "alembic"))
from app.models.models import Base
from schema_alignment import REVISION, plan_alignment


def engine_for(scenario):
    url = make_url(os.environ[f"MIGRATION_{scenario}_DATABASE_URL"])
    if not url.database.startswith("playnow_migration_"):
        raise RuntimeError("Migration tests require a disposable playnow_migration_* database")
    return sa.create_engine(url.set(drivername="mysql+pymysql"), poolclass=sa.pool.NullPool)


def run_cli(engine, *args):
    env = os.environ.copy()
    env["DATABASE_URL"] = engine.url.set(drivername="mysql+asyncmy").render_as_string(hide_password=False)
    return subprocess.run([sys.executable, *args], cwd=BACKEND, env=env, text=True, capture_output=True)


def data_hash(connection, columns=None):
    """Hash all legacy values, normalizing only the reviewed NTRP conversion."""
    result = {}
    tables = sa.inspect(connection).get_table_names()
    aliases = {"post": {}, "tournament": {}}
    user_ids = {}
    user_refs = {}
    if "user_id_migrations" in tables:
        for legacy_id, openid in connection.execute(sa.text("SELECT legacy_id,openid FROM user_id_migrations")):
            user_ids[openid] = legacy_id
        for table in tables:
            user_refs[table] = [fk["constrained_columns"][0] for fk in sa.inspect(connection).get_foreign_keys(table) if fk["referred_table"] == "users"]
    def restore_user_json(value, key=None):
        if isinstance(value, dict): return {k: restore_user_json(v, k) for k,v in value.items()}
        if key in ("user_id", "partner_user_id", "actor_id", "created_by", "locked_by"):
            return user_ids.get(value, value)
        if isinstance(value, list):
            if key in ("users", "user_ids"): return [user_ids.get(v,v) for v in value]
            return [restore_user_json(v) for v in value]
        return value
    if "activities" in tables:
        for row in connection.execute(sa.text("SELECT id, kind, legacy_id FROM activities WHERE legacy_id IS NOT NULL")).mappings():
            aliases[row["kind"]][row["id"]] = row["legacy_id"]
    for name in sa.inspect(connection).get_table_names():
        if name == "alembic_version" or (columns is not None and name not in columns):
            continue
        rows = []
        for row in connection.execute(sa.text(f"SELECT * FROM `{name}` ORDER BY {'legacy_id' if name == 'user_id_migrations' else 'id'}")).mappings():
            row = dict(row)
            if name == "users": row["id"] = user_ids.get(row["id"], row["id"])
            for field in user_refs.get(name, []): row[field] = user_ids.get(row[field], row[field])
            if name in ("tournament_draws", "tournament_audits"):
                field = "snapshot" if name == "tournament_draws" else "detail"
                value = json.loads(row[field]) if isinstance(row[field], str) else row[field]
                row[field] = restore_user_json(value)
            # The reviewed global-ID migration changes IDs and their references,
            # but every other historical value must retain the same hash.
            if name in ("match_posts", "tournaments"):
                kind = "post" if name == "match_posts" else "tournament"
                row["id"] = aliases[kind].get(row["id"], row["id"])
            if name in ("match_registrations", "comments"):
                row["post_id"] = aliases["post"].get(row["post_id"], row["post_id"])
            if name in ("booking_orders", "tournament_registrations", "tournament_draws", "tournament_audits") and "tournament_id" in row:
                row["tournament_id"] = aliases["tournament"].get(row["tournament_id"], row["tournament_id"])
            if name == "notifications":
                kind = {"match_post": "post", "tournament": "tournament"}.get(row["ref_type"])
                if kind:
                    row["ref_id"] = aliases[kind].get(row["ref_id"], row["ref_id"])
            if columns is not None:
                row = {key: value for key, value in row.items() if key in columns[name]}
            if name == "users" and row["ntrp_level"] is not None:
                row["ntrp_level"] = str(Decimal(str(row["ntrp_level"])).normalize())
            rows.append(row)
        result[name] = sorted(rows, key=lambda row: row.get("id", row.get("legacy_id")))
    return hashlib.sha256(json.dumps(result, sort_keys=True, default=str).encode()).hexdigest()


@unittest.skipUnless(all(os.environ.get(f"MIGRATION_{s}_DATABASE_URL") for s in ("EMPTY", "LEGACY", "REJECT")),
    "Requires three disposable MySQL databases; see docs/database-migration-runbook.md")
class MigrationIntegrationTests(unittest.TestCase):
    def assert_model_schema(self, connection):
        inspector = sa.inspect(connection)
        self.assertTrue(set(Base.metadata.tables).issubset(inspector.get_table_names()))
        for name, table in Base.metadata.tables.items():
            actual = {c["name"]: c for c in inspector.get_columns(name)}
            for column in table.columns:
                self.assertIn(column.name, actual, f"{name}.{column.name}")
                expected = str(column.type.compile(dialect=connection.dialect)).lower().replace(" ", "").split("characterset", 1)[0].split("collate", 1)[0]
                observed = str(actual[column.name]["type"].compile(dialect=connection.dialect)).lower().replace(" ", "").split("characterset", 1)[0].split("collate", 1)[0]
                if expected in ("bool", "boolean"):
                    self.assertIn(observed, ("bool", "boolean", "tinyint(1)"))
                else:
                    self.assertEqual(expected, observed, f"{name}.{column.name}")
                self.assertEqual(column.nullable, actual[column.name]["nullable"], f"{name}.{column.name}")
                if (name == "activities" and column.name == "kind") or column.name == "activity_kind":
                    self.assertEqual(actual[column.name]["type"].collation, "ascii_bin")
            indexes = inspector.get_indexes(name)
            for index in table.indexes:
                self.assertTrue(any(i["column_names"] == [c.name for c in index.columns] and bool(i["unique"]) == index.unique for i in indexes), f"{name}.{index.name}")
            uniques = inspector.get_unique_constraints(name)
            fks = inspector.get_foreign_keys(name)
            for constraint in table.constraints:
                columns = [c.name for c in constraint.columns]
                if isinstance(constraint, sa.UniqueConstraint):
                    self.assertTrue(any(u["column_names"] == columns for u in uniques) or any(i["unique"] and i["column_names"] == columns for i in indexes), f"{name} unique {columns}")
                elif isinstance(constraint, sa.ForeignKeyConstraint):
                    target = constraint.elements[0].column.table.name
                    dest = [e.column.name for e in constraint.elements]
                    self.assertTrue(any(f["constrained_columns"] == columns and f["referred_table"] == target and f["referred_columns"] == dest for f in fks), f"{name} FK {columns}")
                elif isinstance(constraint, sa.CheckConstraint):
                    self.assertTrue(any(c["name"] == constraint.name for c in inspector.get_check_constraints(name)), f"{name} check {constraint.name}")
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        head = ScriptDirectory.from_config(Config(str(BACKEND / "alembic.ini"))).get_current_head()
        self.assertEqual(connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one(), head)

    def test_empty_database_upgrades_and_repeats(self):
        engine = engine_for("EMPTY")
        try:
            result = run_cli(engine, "-m", "alembic", "upgrade", "head")
            self.assertEqual(result.returncode, 0, result.stderr)
            result = run_cli(engine, "-m", "alembic", "upgrade", "head")
            self.assertEqual(result.returncode, 0, result.stderr)
            with engine.connect() as connection:
                self.assert_model_schema(connection)
        finally:
            engine.dispose()

    def test_legacy_adoption_preserves_values_and_extra_columns(self):
        engine = engine_for("LEGACY")
        try:
            with engine.connect() as connection:
                columns = {name: {c["name"] for c in sa.inspect(connection).get_columns(name)} for name in sa.inspect(connection).get_table_names()}
                before = data_hash(connection, columns)
                self.assertNotIn("alembic_version", sa.inspect(connection).get_table_names())
            check = run_cli(engine, "scripts/adopt_legacy_database.py")
            self.assertEqual(check.returncode, 0, check.stderr)
            with engine.connect() as connection:
                self.assertEqual(before, data_hash(connection, columns))
                self.assertNotIn("alembic_version", sa.inspect(connection).get_table_names())
            result = run_cli(engine, "scripts/adopt_legacy_database.py", "--apply")
            self.assertEqual(result.returncode, 0, result.stderr)
            with engine.connect() as connection:
                self.assertEqual(before, data_hash(connection, columns))
                self.assert_model_schema(connection)
                extra = {c["name"] for c in sa.inspect(connection).get_columns("venues")}
                self.assertTrue({"open_time", "close_time", "opening_time", "closing_time", "slot_interval_minutes"}.issubset(extra))
            result = run_cli(engine, "-m", "alembic", "upgrade", "head")
            self.assertEqual(result.returncode, 0, result.stderr)
        finally:
            engine.dispose()

    def test_invalid_data_stops_before_ddl_or_stamp(self):
        engine = engine_for("REJECT")
        try:
            with engine.begin() as connection:
                connection.execute(sa.text("UPDATE users SET ntrp_level='invalid' WHERE id=(SELECT id FROM (SELECT MIN(id) AS id FROM users) x)"))
            result = run_cli(engine, "scripts/adopt_legacy_database.py", "--apply")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("NTRP values cannot be converted", result.stderr)
            with engine.connect() as connection:
                self.assertNotIn("alembic_version", sa.inspect(connection).get_table_names())
                self.assertFalse(next(c for c in sa.inspect(connection).get_columns("booking_orders") if c["name"] == "slot_id")["nullable"])
            with engine.begin() as connection:
                connection.execute(sa.text("UPDATE users SET ntrp_level=NULL WHERE ntrp_level='invalid'"))
                connection.execute(sa.text("UPDATE clubs SET view_count=0"))
                insert = sa.text("INSERT INTO settlement_records (order_id,total_amount,platform_amount,club_amount,split_ratio,status,scheduled_at,out_order_no) SELECT MIN(id),1,0,1,0.1,'pending',NOW(),'duplicate-check' FROM booking_orders")
                connection.execute(insert)
                connection.execute(insert)
            result = run_cli(engine, "scripts/adopt_legacy_database.py", "--apply")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Duplicate values prevent unique index", result.stderr)
            with engine.connect() as connection:
                self.assertNotIn("alembic_version", sa.inspect(connection).get_table_names())
            with engine.begin() as connection:
                connection.execute(sa.text("DELETE FROM settlement_records WHERE out_order_no='duplicate-check'"))
                connection.execute(sa.text("UPDATE clubs SET view_count=NULL"))
            result = run_cli(engine, "scripts/adopt_legacy_database.py", "--apply")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("NULL values prevent NOT NULL", result.stderr)
            with engine.connect() as connection:
                self.assertNotIn("alembic_version", sa.inspect(connection).get_table_names())
                self.assertFalse(next(c for c in sa.inspect(connection).get_columns("booking_orders") if c["name"] == "slot_id")["nullable"])
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
