"""Row-lock integration tests. Only explicitly provided disposable MySQL is accepted."""

import asyncio
from datetime import datetime, timedelta
import os
import secrets

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.api.v1 import tournaments as api
from app.models.models import (
    Club,
    User,
    UserRole,
    Tournament,
    TournamentRegistration,
    TournamentDraw,
    TournamentTeam,
    TournamentTeamMember,
    TournamentMatch,
    TournamentAudit,
)
from app.schemas.tournament import (
    TournamentCreate,
    TournamentConfig,
    RegistrationCommand,
    DrawCommand,
)

URL = os.environ.get("TOURNAMENT_MYSQL_TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not URL, reason="Explicit disposable MySQL required"),
]


@pytest.mark.parametrize("operation", ["register", "draw"])
async def test_mysql_serializes_last_seat_and_draw_versions(operation, monkeypatch):
    import redis.asyncio as redis
    from app.services import activity_ids
    from app.core.config import get_settings
    redis_client = redis.from_url(get_settings().REDIS_URL, decode_responses=True)
    monkeypatch.setattr(activity_ids, "redis_client", redis_client)
    url = make_url(URL)
    if url.drivername != "mysql+asyncmy" or not (
        url.database == "test_db"
        or url.database.startswith(("playnow_test_", "playnow_migration_"))
    ):
        raise RuntimeError("Refusing non-disposable tournament test database")
    engine = create_async_engine(url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    club_id = event_id = None
    user_ids = []
    try:
        async with factory() as db:
            club = Club(name="并发测试" + secrets.token_hex(8))
            db.add(club)
            await db.flush()
            club_id = club.id
            users = [
                User(
                    openid="concurrency_" + secrets.token_hex(12),
                    nickname=f"测试{i}",
                    role=UserRole.platform_admin if i == 0 else UserRole.user,
                )
                for i in range(4)
            ]
            db.add_all(users)
            await db.flush()
            user_ids = [u.id for u in users]
            event = await api.create_tournament(
                TournamentCreate(
        address="测试网球场",
                    club_id=club_id,
                    title="并发测试",
                    start_time=datetime.utcnow() + timedelta(days=1),
                    end_time=datetime.utcnow() + timedelta(days=2),
                    max_participants=2,
                    config=TournamentConfig(),
                ),
                users[0],
                db,
            )
            event_id = event["id"]
            await api.register_tournament(event_id, RegistrationCommand(), users[1], db)
            if operation == "draw":
                await api.register_tournament(
                    event_id, RegistrationCommand(), users[2], db
                )
                await api.close_registration(event_id, users[0], db)
            await db.commit()
        barrier = asyncio.Event()

        async def compete(index):
            async with factory() as db:
                user = await db.get(
                    User,
                    user_ids[index + 2] if operation == "register" else user_ids[0],
                )
                await barrier.wait()
                try:
                    if operation == "register":
                        await api.register_tournament(
                            event_id, RegistrationCommand(), user, db
                        )
                    else:
                        await api.create_draw(
                            event_id,
                            DrawCommand(idempotency_key=f"concurrent-draw-{index}"),
                            user,
                            db,
                        )
                    await db.commit()
                    return 200
                except HTTPException as error:
                    await db.rollback()
                    return error.status_code

        tasks = [asyncio.create_task(compete(i)) for i in range(2)]
        barrier.set()
        assert sorted(await asyncio.gather(*tasks)) == [200, 409]
        async with factory() as db:
            t = await db.get(Tournament, event_id)
            if operation == "register":
                rows = (
                    (
                        await db.execute(
                            select(TournamentRegistration).where(
                                TournamentRegistration.tournament_id == event_id
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                assert len(rows) == 2 and t.current_participants == 2
            else:
                draws = (
                    (
                        await db.execute(
                            select(TournamentDraw).where(
                                TournamentDraw.tournament_id == event_id
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                assert len(draws) == 1 and t.draw_version == 1
    finally:
        async with factory() as db:
            if event_id:
                draw_ids = select(TournamentDraw.id).where(
                    TournamentDraw.tournament_id == event_id
                )
                for model in (TournamentMatch, TournamentTeamMember, TournamentTeam):
                    await db.execute(delete(model).where(model.draw_id.in_(draw_ids)))
                for model in (TournamentAudit, TournamentRegistration, TournamentDraw):
                    await db.execute(
                        delete(model).where(model.tournament_id == event_id)
                    )
                await db.execute(delete(Tournament).where(Tournament.id == event_id))
            if user_ids:
                await db.execute(delete(User).where(User.id.in_(user_ids)))
            if club_id:
                await db.execute(delete(Club).where(Club.id == club_id))
            await db.commit()
        await redis_client.aclose()
        await engine.dispose()
