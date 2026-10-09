"""Global identity, historical remapping and database constraint tests."""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
import importlib.util
import subprocess
import sys
import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
from redis.exceptions import LockError, ConnectionError as RedisConnectionError
from tests.test_post_booking_permissions import sqlite_bigint
from app.models.models import (Base, Activity, MatchPost, Tournament, User, UserRole,
                              Club, MatchRegistration, TournamentRegistration)
from app.api.v1 import posts, tournaments, users, activities
from app.schemas.schemas import PostCreate, RegisterPostRequest
from app.schemas.tournament import TournamentCreate, TournamentConfig, RegistrationCommand
from app.services import activity_ids

REAL_LOCK = activity_ids.allocation_lock


def test_alembic_discovers_shared_id_revision_without_loading_database(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(backend / "alembic.ini"), "heads"],
        cwd=tmp_path, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "20261009_review_integrity (head)"


@pytest_asyncio.fixture
async def database(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'activities.sqlite'}")
    @sa.event.listens_for(engine.sync_engine, "connect")
    def foreign_keys(conn, record):
        conn.execute("PRAGMA foreign_keys=ON")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        db.add(User(id='1', openid="global-admin", role=UserRole.platform_admin))
        db.add(User(id='2', openid="global-user"))
        db.add(Club(id=1, name="测试俱乐部"))
        await db.commit()
    semaphore = asyncio.Lock()
    @asynccontextmanager
    async def sql_only_lock():
        async with semaphore:
            yield
    monkeypatch.setattr(activity_ids, "allocation_lock", sql_only_lock)
    yield factory
    await engine.dispose()


async def create(db, kind):
    user = await db.get(User, 1)
    if kind == "post":
        return (await posts.create_post(PostCreate(title="约球", price=0, preferred_date="2026-11-01", preferred_start="09:00", preferred_end="11:00", players_needed=2), user, db)).id
    result = await tournaments.create_tournament(TournamentCreate(
        address="测试网球场",
        club_id=1, title="比赛", start_time=datetime.utcnow()+timedelta(days=1),
        end_time=datetime.utcnow()+timedelta(days=2), max_participants=8,
        config=TournamentConfig(),
    ), user, db)
    return result["id"]


@pytest.mark.asyncio
async def test_mixed_concurrent_creates_share_one_database_sequence(database):
    async def worker(i):
        async with database() as db:
            ident = await create(db, "post" if i % 2 else "tournament")
            await db.commit()
            return ident
    ids = await asyncio.gather(*(worker(i) for i in range(20)))
    assert len(ids) == len(set(ids)) == 20
    async with database() as db:
        assert await db.scalar(sa.select(sa.func.count(Activity.id))) == 20
        for model, kind in ((MatchPost, "post"), (Tournament, "tournament")):
            actual = (await db.execute(sa.select(model.id))).scalars().all()
            assert len(actual) == 10
            for ident in actual:
                assert (await db.get(Activity, ident)).kind == kind


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["missing_parent", "wrong_kind", "duplicate_child", "forged_kind"])
async def test_database_refuses_invalid_global_identity(database, case):
    async with database() as db:
        ident = await create(db, "post")
        await db.commit()
        if case == "missing_parent":
            db.add(MatchPost(id=999, user_id='1', title="无主编号"))
        elif case == "duplicate_child":
            db.add(MatchPost(id=ident, user_id='1', title="重复"))
        else:
            db.add(Tournament(id=ident, activity_kind="post" if case == "forged_kind" else "tournament",
                              club_id=1, title="错误类型", start_time=datetime.utcnow(), end_time=datetime.utcnow()))
        with pytest.raises(IntegrityError):
            await db.flush()
        await db.rollback()


@pytest.mark.asyncio
async def test_unified_personal_records_and_old_links_resolve_by_type(database):
    async with database() as db:
        post = await create(db, "post")
        tournament = await create(db, "tournament")
        user = await db.get(User, 2)
        await posts.register_post(post, RegisterPostRequest(), user, db)
        await tournaments.register_tournament(tournament, RegistrationCommand(), user, db)
        await db.commit()
        items = []
        for kind in ("post", "tournament"):
            result = await users.my_activities(kind, "joined", "all", "", 1, 50, user, db)
            items.extend(result.items)
            assert (await users.my_activities(kind, "joined", "all", "", 1, 50, await db.get(User, 1), db)).total == 0
        assert {r["activity_id"] for r in items} == {post, tournament}
        assert {r["kind"] for r in items} == {"post", "tournament"}
        assert (await activities.get_activity(post, user, db))["kind"] == "post"
        assert (await activities.get_activity(tournament, user, db))["kind"] == "tournament"
        (await db.get(Activity, post)).legacy_id = 100
        (await db.get(Activity, tournament)).legacy_id = 100
        await db.commit()
        assert (await posts.get_post(100, db)).id == post
        assert (await tournaments.get_tournament(100, user, db))["id"] == tournament


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [LockError("busy"), RedisConnectionError("unavailable")])
async def test_redis_failure_is_closed_without_allocating(database, monkeypatch, error):
    class Lock:
        async def __aenter__(self):
            raise error
        async def __aexit__(self, *args):
            pass
    class Redis:
        def lock(self, name, **options):
            assert name == "activity:id:allocate"
            assert options["timeout"] == 30 and options["blocking_timeout"] == 5
            return Lock()
    monkeypatch.setattr(activity_ids, "allocation_lock", REAL_LOCK)
    monkeypatch.setattr(activity_ids, "redis_client", Redis())
    async with database() as db:
        with pytest.raises(HTTPException) as exc:
            await activity_ids.allocate_activity(db, "post")
        assert exc.value.status_code == 503
        assert await db.scalar(sa.select(sa.func.count(Activity.id))) == 0


def test_historical_conflicts_all_renumber_and_references_follow():
    spec = importlib.util.spec_from_file_location("activity_backfill", Path(__file__).parents[1]/"alembic/activity_backfill.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = sa.create_engine("sqlite://")
    with engine.begin() as c:
        c.exec_driver_sql("CREATE TABLE activities (id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, legacy_id INTEGER, created_at DATETIME, UNIQUE(kind, legacy_id))")
        for table in ("match_posts", "tournaments"):
            c.exec_driver_sql(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, created_at DATETIME)")
        for table in module.POST_REFERENCES:
            c.exec_driver_sql(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, post_id INTEGER)")
            c.exec_driver_sql(f"INSERT INTO {table} VALUES (1, 1)")
        for table in module.TOURNAMENT_REFERENCES:
            c.exec_driver_sql(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, tournament_id INTEGER)")
            c.exec_driver_sql(f"INSERT INTO {table} VALUES (1, 1)")
        c.exec_driver_sql("CREATE TABLE notifications (id INTEGER PRIMARY KEY, ref_id INTEGER, ref_type TEXT)")
        c.exec_driver_sql("INSERT INTO notifications VALUES (1,1,'match_post'),(2,1,'tournament')")
        c.exec_driver_sql("INSERT INTO match_posts VALUES (1,'2026-10-07 12:00:00'),(3,NULL)")
        c.exec_driver_sql("INSERT INTO tournaments VALUES (1,NULL),(5,NULL)")
        mapping = module.backfill(c)
        assert mapping["post"][1] > 5 and mapping["tournament"][1] > 5
        assert mapping["post"][1] != mapping["tournament"][1]
        assert c.scalar(sa.text("SELECT id FROM match_posts WHERE id=3")) == 3
        assert c.scalar(sa.text("SELECT id FROM tournaments WHERE id=5")) == 5
        for table in module.POST_REFERENCES:
            assert c.scalar(sa.text(f"SELECT post_id FROM {table}")) == mapping["post"][1]
        for table in module.TOURNAMENT_REFERENCES:
            assert c.scalar(sa.text(f"SELECT tournament_id FROM {table}")) == mapping["tournament"][1]
        assert c.scalar(sa.text("SELECT ref_id FROM notifications WHERE id=1")) == mapping["post"][1]
        assert c.scalar(sa.text("SELECT ref_id FROM notifications WHERE id=2")) == mapping["tournament"][1]
        assert str(c.scalar(sa.text("SELECT created_at FROM activities WHERE kind='post' AND legacy_id=1"))).startswith("2026-10-07 12:00:00")
        assert module.backfill(c) == mapping
        assert c.scalar(sa.text("SELECT COUNT(*) FROM activities")) == 4
    engine.dispose()
