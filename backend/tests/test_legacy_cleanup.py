"""One-time conversions are tested independently of runtime compatibility."""
from datetime import datetime, timedelta, date, time
import importlib.util
import os
from pathlib import Path
import uuid
import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session
from sqlalchemy.engine import make_url
from alembic import command
from alembic.config import Config
from app.models.models import User, Club, Venue, VenueTimeSlot, Activity, Tournament, TournamentDraw, TournamentTeam, TournamentMatch
from app.services import tournament_engine as engine

BACKEND = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("cleanup_revision", BACKEND / "alembic/versions/20261015_remove_legacy.py")
revision = importlib.util.module_from_spec(spec)
spec.loader.exec_module(revision)


@pytest.mark.parametrize("people", [3, 4, 5, 6])
def test_migration_recovers_round_robin_order_without_changing_matches(people):
    ids = list(range(people, 0, -1))
    matches = engine.round_robin(ids, 1)
    teams = [dict(id=ident, group_no=1) for ident in sorted(ids)]
    positions = revision.migrate_positions(teams, matches)
    assert [position["team_id"] for position in positions] == ids


@pytest.mark.skipif(not os.environ.get("CLEANUP_MYSQL_TEST_DATABASE_URL"), reason="Explicit disposable MySQL required")
def test_mysql_migrates_single_slots_prizes_and_draw_positions():
    source = make_url(os.environ["CLEANUP_MYSQL_TEST_DATABASE_URL"])
    if source.host not in ("localhost", "127.0.0.1") or not (source.database == "test_db" or source.database.startswith("playnow_test_")):
        raise RuntimeError("Cleanup migration test requires isolated local infrastructure")
    name = "playnow_migration_cleanup_" + uuid.uuid4().hex[:10]
    admin = sa.create_engine(source.set(drivername="mysql+pymysql", database=None), hide_parameters=True)
    with admin.begin() as connection:
        connection.execute(sa.text("CREATE DATABASE " + name + " CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))
    database = sa.create_engine(source.set(drivername="mysql+pymysql", database=name), hide_parameters=True)
    try:
        with database.connect() as connection:
            config = Config(str(BACKEND / "alembic.ini"))
            config.set_main_option("script_location", str(BACKEND / "alembic"))
            config.attributes["connection"] = connection
            command.upgrade(config, "20261015_post_people")
            with Session(connection) as session:
                user = User(openid="isolated-cleanup-user")
                club = Club(name="isolated-cleanup-club")
                session.add_all([user, club]); session.flush()
                venue = Venue(club_id=club.id, name="court", sport_type="tennis", price_per_hour=100)
                session.add(venue); session.flush()
                slot = VenueTimeSlot(venue_id=venue.id, date=date(2030, 1, 1), start_time=time(9), end_time=time(9, 30))
                session.add(slot)
                session.add(Activity(id=101, kind="tournament")); session.flush()
                # Seed the historical table, never today's ORM schema at an older revision.
                events_before = sa.Table("tournaments", sa.MetaData(), autoload_with=connection)
                connection.execute(events_before.insert().values(id=101, activity_kind="tournament", club_id=club.id,
                    venue_id=venue.id, title="fixture", start_time=datetime(2030,1,1), end_time=datetime(2030,1,2),
                    max_participants=4, current_participants=0, entry_fee=0, status="draft", lock_venue=False,
                    auto_title=False, roster_frozen=False, registration_closed=False, draw_version=0,
                    created_at=datetime.utcnow(), updated_at=datetime.utcnow()))
                draw = TournamentDraw(tournament_id=101, version=1, stage="initial", idempotency_key="fixture", seed="fixture", snapshot={}, created_by=user.id)
                session.add(draw); session.flush()
                teams = [TournamentTeam(draw_id=draw.id, group_no=1, name=str(ident)) for ident in range(3)]
                session.add_all(teams); session.flush()
                ids = [team.id for team in reversed(teams)]
                for match in engine.round_robin(ids):
                    session.add(TournamentMatch(draw_id=draw.id, **{key: match[key] for key in ("group_no", "round_no", "position", "kind", "team_a_id", "team_b_id")}))
                session.flush()
                connection.execute(sa.text("INSERT INTO booking_orders(id,order_no,user_id,venue_id,club_id,slot_id,slot_ids,amount,status,business_type) VALUES (991,'isolated-old-slot',:user,:venue,:club,:slot,NULL,50,'cancelled','booking')"),
                    dict(user=user.id, venue=venue.id, club=club.id, slot=slot.id))
                connection.execute(sa.text("UPDATE tournaments SET prize='旧奖项',prizes=NULL WHERE id=101"))
                connection.execute(sa.text("UPDATE venues SET price_rules=JSON_ARRAY(JSON_OBJECT('type','time_range','start_time','09:00','end_time','11:00','price',120)) WHERE id=:id"), {'id':venue.id})
                slot_id, draw_id = slot.id, draw.id
                session.commit()
            connection.commit()
            command.upgrade(config, "head"); command.upgrade(config, "head")
            metadata = sa.MetaData()
            orders = sa.Table("booking_orders", metadata, autoload_with=connection)
            events = sa.Table("tournaments", metadata, autoload_with=connection)
            draws = sa.Table("tournament_draws", metadata, autoload_with=connection)
            assert connection.execute(sa.select(orders.c.slot_ids).where(orders.c.id == 991)).scalar_one() == [slot_id]
            assert connection.execute(sa.text("SELECT amount FROM booking_slots WHERE order_id=991")).scalar_one() is None
            assert connection.execute(sa.text("SELECT amount FROM booking_orders WHERE id=991")).scalar_one() == 50
            assert connection.execute(sa.select(events.c.prizes).where(events.c.id == 101)).scalar_one() == [{"name":"奖项", "description":"旧奖项"}]
            snapshot = connection.execute(sa.select(draws.c.snapshot).where(draws.c.id == draw_id)).scalar_one()
            assert [position["team_id"] for position in snapshot["positions"]] == ids
            venues = sa.Table("venues", metadata, autoload_with=connection)
            rules = connection.execute(sa.select(venues.c.price_rules)).scalar_one()
            assert rules == [{"type":"daily_time", "start_time":"09:00", "end_time":"11:00", "price":120}]
            assert connection.execute(sa.select(events.c.location_name).where(events.c.id == 101)).scalar_one() == "court"
            assert "slot_id" not in orders.c and "prize" not in events.c
            assert "user_id_migrations" not in sa.inspect(connection).get_table_names()
    finally:
        database.dispose()
        with admin.begin() as connection:
            connection.execute(sa.text("DROP DATABASE " + name))
        admin.dispose()
