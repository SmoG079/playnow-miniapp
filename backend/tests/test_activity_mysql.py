"""Real MySQL + Redis concurrent identity checks; disposable infrastructure only."""
import asyncio
import os
import secrets
from datetime import datetime, timedelta
import pytest
import redis.asyncio as redis
from sqlalchemy import delete, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import NullPool
from app.models.models import Activity, Club, User, UserRole, MatchPost, Tournament, TournamentAudit
from app.api.v1 import posts, tournaments
from app.schemas.schemas import PostCreate
from app.schemas.tournament import TournamentCreate, TournamentConfig
from app.services import activity_ids

DATABASE = os.environ.get("ACTIVITY_MYSQL_TEST_DATABASE_URL")
REDIS = os.environ.get("ACTIVITY_REDIS_TEST_URL")
pytestmark = pytest.mark.skipif(not DATABASE or not REDIS, reason="isolated MySQL and Redis are required")


@pytest.mark.asyncio
async def test_shared_sequence_under_real_mysql_and_redis(monkeypatch):
    url = make_url(DATABASE)
    if url.drivername != "mysql+asyncmy" or not (url.database == "test_db" or url.database.startswith(("playnow_test_", "playnow_migration_"))):
        raise RuntimeError("Refusing non-disposable activity test database")
    if not REDIS.rstrip("/").endswith("/15"):
        raise RuntimeError("Activity Redis test must use isolated DB 15")
    engine = create_async_engine(url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    client = redis.from_url(REDIS, decode_responses=True)
    monkeypatch.setattr(activity_ids, "redis_client", client)
    user_id = club_id = None
    created = []
    try:
        async with factory() as db:
            club = Club(name="统一编号测试" + secrets.token_hex(6))
            user = User(openid="activity-test-" + secrets.token_hex(12), role=UserRole.platform_admin)
            db.add_all([club, user])
            await db.flush()
            club_id, user_id = club.id, user.id
            await db.commit()
        barrier = asyncio.Event()
        async def worker(index):
            async with factory() as db:
                user = await db.get(User, user_id)
                await barrier.wait()
                if index % 2:
                    row = await posts.create_post(PostCreate(title="并发约球", price=0, preferred_date="2026-11-01", preferred_start="09:00", preferred_end="11:00", players_needed=2), user, db)
                    ident = row.id
                else:
                    row = await tournaments.create_tournament(TournamentCreate(
        address="测试网球场",
                        club_id=club_id, title="并发比赛", start_time=datetime.utcnow()+timedelta(days=1),
                        end_time=datetime.utcnow()+timedelta(days=2), max_participants=8, config=TournamentConfig(),
                    ), user, db)
                    ident = row["id"]
                await db.commit()
                created.append(ident)
                return ident
        tasks = [asyncio.create_task(worker(i)) for i in range(20)]
        barrier.set()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        assert all(isinstance(r, int) for r in results), [type(r).__name__ for r in results]
        assert len(set(results)) == 20
        async with factory() as db:
            post_id = await db.scalar(select(MatchPost.id).where(MatchPost.id.in_(created)).limit(1))
            db.add(Tournament(id=post_id, club_id=club_id, title="重复归属", start_time=datetime.utcnow(), end_time=datetime.utcnow()))
            with pytest.raises(IntegrityError):
                await db.flush()
            await db.rollback()
    finally:
        async with factory() as db:
            if created:
                await db.execute(delete(TournamentAudit).where(TournamentAudit.tournament_id.in_(created)))
                await db.execute(delete(Tournament).where(Tournament.id.in_(created)))
                await db.execute(delete(MatchPost).where(MatchPost.id.in_(created)))
                await db.execute(delete(Activity).where(Activity.id.in_(created)))
            if club_id:
                await db.execute(delete(Club).where(Club.id == club_id))
            if user_id:
                await db.execute(delete(User).where(User.id == user_id))
            await db.commit()
        await client.aclose()
        await engine.dispose()
