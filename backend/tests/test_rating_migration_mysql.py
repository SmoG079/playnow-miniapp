"""Rehearse rating columns on isolated empty and prior-head MySQL databases."""
import os
from pathlib import Path
import subprocess
import sys
import pytest
import sqlalchemy as sa
from sqlalchemy.engine import make_url

URL = os.environ.get("RATING_MIGRATION_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="Explicit isolated rating migration MySQL required")
BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture
def isolated_db():
    url = make_url(URL)
    if url.host not in ("127.0.0.1", "localhost") or url.database != "playnow_migration_rating_test":
        raise RuntimeError("Refusing to reset a non-isolated rating database")
    engine = sa.create_engine(url.set(drivername="mysql+pymysql"), poolclass=sa.pool.NullPool)
    with engine.begin() as connection:
        connection.execute(sa.text("SET FOREIGN_KEY_CHECKS=0"))
        for table in sa.inspect(connection).get_table_names():
            connection.execute(sa.text(f"DROP TABLE `{table}`"))
        connection.execute(sa.text("SET FOREIGN_KEY_CHECKS=1"))
    def upgrade(target="head"):
        result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", target], cwd=BACKEND,
            env=dict(os.environ, DATABASE_URL=url.set(drivername="mysql+asyncmy").render_as_string(hide_password=False)),
            capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stderr
    yield engine, upgrade
    engine.dispose()


def test_empty_upgrade_and_repeat(isolated_db):
    engine, upgrade = isolated_db
    upgrade(); upgrade()
    with engine.connect() as connection:
        columns = {column["name"]: column for column in sa.inspect(connection).get_columns("users")}
        assert all(columns[name]["nullable"] for name in ("utr_rating", "rating_assessment", "rating_assessed_at"))
        assert connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one() == "20261009_user_rating"


def test_existing_ntrp_unchanged_and_assessment_persists(isolated_db):
    engine, upgrade = isolated_db
    upgrade("20261009_review_integrity")
    with engine.begin() as connection:
        connection.execute(sa.text("INSERT INTO users(id,openid,public_id,nickname,ntrp_level,role) VALUES('rating-fixture','rating-fixture','bb0f0e55-3c6a-4ff0-aa65-9c84ade6c115','隔离用户',3.5,'user')"))
        before = dict(connection.execute(sa.text("SELECT * FROM users")).mappings().one())
    upgrade(); upgrade()
    with engine.begin() as connection:
        after = dict(connection.execute(sa.text("SELECT * FROM users")).mappings().one())
        assert all(after[field] == value for field, value in before.items())
        assert after["utr_rating"] is None and after["rating_assessment"] is None
        connection.execute(sa.text("UPDATE users SET utr_rating=16.50,rating_assessment=JSON_OBJECT('version','fixture'),rating_assessed_at=UTC_TIMESTAMP()"))
    upgrade()
    with engine.connect() as connection:
        assert str(connection.execute(sa.text("SELECT utr_rating FROM users")).scalar_one()) == "16.50"
        assert connection.execute(sa.text("SELECT JSON_UNQUOTE(JSON_EXTRACT(rating_assessment,'$.version')) FROM users")).scalar_one() == "fixture"
