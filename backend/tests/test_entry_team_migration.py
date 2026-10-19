"""Upgrade a real previous schema, preserving formed teams and chat contexts."""
import os
import uuid
from pathlib import Path
from datetime import datetime, timedelta
import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session
from sqlalchemy.engine import make_url
from alembic import command
from alembic.config import Config
from app.models.models import User, Activity, MatchPost, Tournament, TournamentDraw, TournamentTeam, TournamentTeamMember


@pytest.mark.skipif(not os.environ.get("TOURNAMENT_MYSQL_TEST_DATABASE_URL"), reason="Explicit disposable MySQL required")
def test_previous_schema_migrates_entry_teams_and_conversation_contexts():
    source = make_url(os.environ["TOURNAMENT_MYSQL_TEST_DATABASE_URL"])
    if source.host not in ("localhost", "127.0.0.1") or not (source.database == "test_db" or source.database.startswith("playnow_test_")):
        raise RuntimeError("Only isolated local MySQL may run this migration test")
    name = "playnow_migration_entries_" + uuid.uuid4().hex[:10]
    admin = sa.create_engine(source.set(drivername="mysql+pymysql", database=None), hide_parameters=True)
    with admin.begin() as c: c.execute(sa.text("CREATE DATABASE " + name + " CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))
    database = sa.create_engine(source.set(drivername="mysql+pymysql", database=name), hide_parameters=True)
    try:
        with database.connect() as c:
            backend = Path(__file__).resolve().parents[1]
            cfg = Config(str(backend / "alembic.ini")); cfg.set_main_option("script_location", str(backend / "alembic")); cfg.attributes["connection"] = c
            command.upgrade(cfg, "20261015_location_names"); c.commit()
            with Session(c) as session:
                session.add_all([User(id=str(i),openid="entry-migration-"+str(i)) for i in range(1,4)])
                session.add_all([Activity(id=501,kind="tournament"),Activity(id=502,kind="post")]); session.flush()
                session.add(MatchPost(id=502,user_id="1",title="chat context"))
                legacy_events = sa.Table("tournaments",sa.MetaData(),autoload_with=c)
                session.execute(legacy_events.insert().values(id=501,title="existing mixed teams",start_time=datetime(2030,1,1),end_time=datetime(2030,1,2),max_participants=8,
                    config={"discipline":"mixed","format":"knockout","group_count":2},draw_version=1,published_version=1,
                    lock_venue=False,current_participants=0,entry_fee=0,prizes=[],auto_title=False,
                    registration_closed=False,roster_frozen=False,status="open",created_at=datetime(2026,1,1),updated_at=datetime(2026,1,1)))
                audits=sa.Table("tournament_audits",sa.MetaData(),autoload_with=c)
                session.execute(audits.insert().values(tournament_id=501,actor_id="1",action="created",detail={},created_at=datetime(2026,1,1)))
                session.flush()
                draw = TournamentDraw(tournament_id=501,version=1,stage="initial",idempotency_key="migration-draw",seed="fixed",snapshot={"positions":[]},created_by="1")
                session.add(draw); session.flush()
                team = TournamentTeam(draw_id=draw.id,group_no=1,name="Existing pair")
                session.add(team); session.flush()
                session.add_all([TournamentTeamMember(draw_id=draw.id,team_id=team.id,user_id=str(i)) for i in (2,3)])
                session.commit()
            regs = sa.Table("tournament_registrations",sa.MetaData(),autoload_with=c)
            c.execute(regs.insert(),[dict(tournament_id=501,user_id=str(i),status="confirmed",approval="approved",payment="none",admission="active",gender=gender,
                requested_group=1,pairing="fixed",partner_user_id=str(5-i),created_at=datetime(2026,1,1),updated_at=datetime(2026,1,1)) for i,gender in ((2,"male"),(3,"female"))])
            conversations = sa.Table("direct_conversations",sa.MetaData(),autoload_with=c)
            c.execute(conversations.insert().values(id="context",pair_key="migration-pair",participant_a="1",participant_b="2",post_id=502,read_a=17,read_b=12,created_at=datetime(2026,1,1)))
            c.commit()
            command.upgrade(cfg,"head"); c.commit()
            command.upgrade(cfg,"head"); c.commit()
            inspector = sa.inspect(c)
            assert "pairing" not in {x["name"] for x in inspector.get_columns("tournament_registrations")}
            assert "post_id" not in {x["name"] for x in inspector.get_columns("direct_conversations")}
            assert c.scalar(sa.text("SELECT COUNT(*) FROM tournament_entry_teams WHERE tournament_id=501")) == 4
            migrated = c.execute(sa.text("SELECT user_id,entry_team_id,entry_seat,requested_group,partner_user_id FROM tournament_registrations ORDER BY user_id")).all()
            assert migrated[0][1] == migrated[1][1] and [r[2] for r in migrated] == [1,2]
            assert [r[3:] for r in migrated] == [(1,"3"),(1,"2")]
            assert c.execute(sa.text("SELECT activity_id,read_a,read_b FROM direct_conversations")).one() == (502,17,12)
            assert c.scalar(sa.text("SELECT COUNT(*) FROM tournament_team_members")) == 2
    finally:
        database.dispose()
        with admin.begin() as c: c.execute(sa.text("DROP DATABASE " + name))
        admin.dispose()
