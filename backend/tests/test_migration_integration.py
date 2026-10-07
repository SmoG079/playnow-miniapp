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


def data_hash(connection):
    """Hash all legacy values, normalizing only the reviewed NTRP conversion."""
    result = {}
    for name in sa.inspect(connection).get_table_names():
        if name == "alembic_version":
            continue
        rows = []
        for row in connection.execute(sa.text(f"SELECT * FROM `{name}` ORDER BY id")).mappings():
            row = dict(row)
            if name == "users" and row["ntrp_level"] is not None:
                row["ntrp_level"] = str(Decimal(str(row["ntrp_level"])).normalize())
            rows.append(row)
        result[name] = rows
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
                expected = str(column.type.compile(dialect=connection.dialect)).lower().replace(" ", "")
                observed = str(actual[column.name]["type"].compile(dialect=connection.dialect)).lower().replace(" ", "").split("characterset", 1)[0].split("collate", 1)[0]
                if expected in ("bool", "boolean"):
                    self.assertIn(observed, ("bool", "boolean", "tinyint(1)"))
                else:
                    self.assertEqual(expected, observed, f"{name}.{column.name}")
                self.assertEqual(column.nullable, actual[column.name]["nullable"], f"{name}.{column.name}")
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
        self.assertFalse(plan_alignment(connection))
        self.assertEqual(connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one(), REVISION)

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
                before = data_hash(connection)
                self.assertNotIn("alembic_version", sa.inspect(connection).get_table_names())
            check = run_cli(engine, "scripts/adopt_legacy_database.py")
            self.assertEqual(check.returncode, 0, check.stderr)
            with engine.connect() as connection:
                self.assertEqual(before, data_hash(connection))
                self.assertNotIn("alembic_version", sa.inspect(connection).get_table_names())
            result = run_cli(engine, "scripts/adopt_legacy_database.py", "--apply")
            self.assertEqual(result.returncode, 0, result.stderr)
            with engine.connect() as connection:
                self.assertEqual(before, data_hash(connection))
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
