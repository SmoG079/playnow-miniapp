"""Explicitly reconcile an unversioned database before recording its revision."""
import argparse
import os
from pathlib import Path
import sys

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND / "alembic"))
from alembic import command
from alembic.config import Config
import sqlalchemy as sa
from sqlalchemy.engine import make_url
from schema_alignment import METADATA, REVISION, apply_alignment, plan_alignment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Apply after backup and an isolated restore rehearsal")
    args = parser.parse_args()
    value = os.environ.get("DATABASE_URL")
    if not value:
        raise RuntimeError("DATABASE_URL must be explicitly provided; no fallback database is used")
    url = make_url(value).set(drivername="mysql+pymysql")
    engine = sa.create_engine(url, poolclass=sa.pool.NullPool)
    try:
        with engine.connect() as connection:
            inspector = sa.inspect(connection)
            tables = set(inspector.get_table_names())
            if "alembic_version" in tables:
                raise RuntimeError("Database already has Alembic tracking; use alembic upgrade head")
            if not set(METADATA.tables).issubset(tables):
                raise RuntimeError("Not the audited legacy schema: required tables are missing")
            # This entrypoint adopts the audited database, not an arbitrary unknown schema.
            for name, table in METADATA.tables.items():
                actual = {c["name"] for c in inspector.get_columns(name)}
                if not set(table.columns.keys()).issubset(actual):
                    raise RuntimeError(f"Not the audited legacy schema: columns missing from {name}")
            actions = plan_alignment(connection)
            print(f"Preflight passed: {len(actions)} schema actions; legacy columns will be preserved")
            if not args.apply:
                print("Read-only check complete. Use --apply only after a verified backup and rehearsal.")
                return
            apply_alignment(connection)
            # MySQL DDL is not transactional. Stamp only after alignment and verification.
            connection.commit()
            config = Config(str(BACKEND / "alembic.ini"))
            config.attributes["connection"] = connection
            config.attributes["target_metadata"] = METADATA
            command.stamp(config, REVISION)
            connection.commit()
            print(f"Baseline verified and revision recorded: {REVISION}")
            # Apply later, separately frozen revisions after verified legacy adoption.
            command.upgrade(config, "head")
            connection.commit()
            print("Subsequent migrations completed")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
