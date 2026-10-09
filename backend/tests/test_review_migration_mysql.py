"""Rehearse the new migration against prior-head data and reject corruption before DDL."""

import os
from pathlib import Path
import subprocess
import sys
import pytest
import sqlalchemy as sa
from sqlalchemy.engine import make_url
from app.services.public_identity import public_user_id

URL = os.environ.get("REVIEW_MIGRATION_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not URL, reason="Explicit isolated review migration MySQL required"
)
BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture
def prior_db():
    url = make_url(URL)
    if url.host not in ("127.0.0.1", "localhost") or url.database not in (
        "playnow_migration_review_legacy",
        "playnow_migration_review_reject",
    ):
        raise RuntimeError("Refusing to reset a non-isolated review database")
    engine = sa.create_engine(
        url.set(drivername="mysql+pymysql"), poolclass=sa.pool.NullPool
    )
    with engine.begin() as conn:
        conn.execute(sa.text("SET FOREIGN_KEY_CHECKS=0"))
        for name in sa.inspect(conn).get_table_names():
            conn.execute(sa.text(f"DROP TABLE `{name}`"))
        conn.execute(sa.text("SET FOREIGN_KEY_CHECKS=1"))
    env = dict(
        os.environ,
        DATABASE_URL=url.set(drivername="mysql+asyncmy").render_as_string(
            hide_password=False
        ),
    )

    def upgrade(target="head"):
        return subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", target],
            cwd=BACKEND,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )

    result = upgrade("20261008_optional_host")
    assert result.returncode == 0, result.stderr
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO users(id,openid,role) VALUES('review-openid','review-openid','user')"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO clubs(id,name,sport_types,opening_time,closing_time,split_ratio,status,view_count,exposure_count,approval_status) VALUES(1,'isolated',JSON_ARRAY('tennis'),'08:00','22:00',0.1,'active',0,0,'approved')"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO venues(id,club_id,name,sport_type,price_per_hour,max_capacity,sort_order,status) VALUES(1,1,'court','tennis',100,4,0,'active')"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO venue_time_slots(id,venue_id,date,start_time,end_time,status) VALUES(1,1,'2030-01-02','10:00','10:30','booked'),(2,1,'2030-01-02','10:30','11:00','booked')"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO booking_orders(id,order_no,user_id,venue_id,slot_id,slot_ids,club_id,amount,status,business_type) VALUES(1,'isolated-order','review-openid',1,1,JSON_ARRAY(1,2),1,100,'paid','booking')"
            )
        )
    yield engine, upgrade
    engine.dispose()


def test_prior_head_booking_migration_preserves_history_and_enforces_detail_fk(
    prior_db,
):
    engine, upgrade = prior_db
    result = upgrade()
    assert result.returncode == 0, result.stderr
    result = upgrade()
    assert result.returncode == 0, result.stderr
    with engine.connect() as conn:
        assert (
            conn.execute(
                sa.text("SELECT amount FROM booking_orders WHERE id=1")
            ).scalar_one()
            == 100
        )
        assert conn.execute(
            sa.text("SELECT public_id FROM users")
        ).scalar_one() == public_user_id("review-openid")
        assert (
            conn.execute(
                sa.text("SELECT COUNT(*) FROM booking_slots WHERE amount IS NULL")
            ).scalar_one()
            == 2
        )
        assert (
            conn.execute(
                sa.text(
                    "SELECT COUNT(*) FROM venue_time_slots WHERE booking_order_id=1"
                )
            ).scalar_one()
            == 2
        )
        assert (
            conn.execute(
                sa.text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            == "20261009_review_integrity"
        )
    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO booking_slots(order_id,slot_id,amount) VALUES(1,999,10)"
                )
            )
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO settlement_records(order_id,total_amount,platform_amount,club_amount,split_ratio,status,scheduled_at) VALUES(1,100,10,90,0.1,'pending',NOW())"
            )
        )
    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO settlement_records(order_id,total_amount,platform_amount,club_amount,split_ratio,status,scheduled_at) VALUES(1,100,10,90,0.1,'pending',NOW())"
                )
            )


@pytest.mark.parametrize(
    "corruption", ["missing_slot", "duplicate_settlement", "bad_price", "overlap"]
)
def test_invalid_history_is_refused_before_any_new_ddl(prior_db, corruption):
    engine, upgrade = prior_db
    with engine.begin() as conn:
        if corruption == "missing_slot":
            conn.execute(
                sa.text(
                    "UPDATE booking_orders SET slot_ids=JSON_ARRAY(1,999) WHERE id=1"
                )
            )
        elif corruption == "bad_price":
            conn.execute(
                sa.text(
                    "UPDATE venues SET price_rules=JSON_ARRAY(JSON_OBJECT('type','daily_time','start_time','08:00','end_time','22:00','price',-1)) WHERE id=1"
                )
            )
        elif corruption == "overlap":
            conn.execute(
                sa.text("UPDATE venue_time_slots SET start_time='10:15' WHERE id=2")
            )
        else:
            for _ in range(2):
                conn.execute(
                    sa.text(
                        "INSERT INTO settlement_records(order_id,total_amount,platform_amount,club_amount,split_ratio,status,scheduled_at) VALUES(1,100,10,90,0.1,'pending',NOW())"
                    )
                )
    result = upgrade()
    assert result.returncode != 0
    assert "Integrity preflight refused before DDL" in result.stderr
    with engine.connect() as conn:
        assert "public_id" not in {
            c["name"] for c in sa.inspect(conn).get_columns("users")
        }
        assert "booking_slots" not in sa.inspect(conn).get_table_names()
        assert (
            conn.execute(
                sa.text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            == "20261008_optional_host"
        )


def seed_two_draws(conn):
    conn.execute(
        sa.text(
            "INSERT INTO activities(id,kind,created_at) VALUES(10,'tournament',NOW())"
        )
    )
    conn.execute(
        sa.text(
            "INSERT INTO tournaments(id,club_id,title,start_time,end_time,lock_venue,current_participants,entry_fee,auto_title,registration_closed,roster_frozen,draw_version,published_version,status) VALUES(10,1,'isolated','2030-01-02','2030-01-03',0,0,0,0,0,0,2,0,'open')"
        )
    )
    conn.execute(
        sa.text(
            "INSERT INTO tournament_draws(id,tournament_id,version,stage,idempotency_key,seed,snapshot,created_by) VALUES(10,10,1,'group','isolated-1','seed',JSON_OBJECT(),'review-openid'),(11,10,2,'group','isolated-2','seed',JSON_OBJECT(),'review-openid')"
        )
    )
    conn.execute(
        sa.text(
            "INSERT INTO tournament_teams(id,draw_id,group_no,name) VALUES(10,10,1,'isolated-team')"
        )
    )


def test_cross_draw_historical_reference_is_refused_before_ddl(prior_db):
    engine, upgrade = prior_db
    with engine.begin() as conn:
        seed_two_draws(conn)
        conn.execute(
            sa.text(
                "INSERT INTO tournament_team_members(draw_id,team_id,user_id) VALUES(11,10,'review-openid')"
            )
        )
    result = upgrade()
    assert result.returncode != 0 and "crosses draw" in result.stderr
    with engine.connect() as conn:
        assert "public_id" not in {
            c["name"] for c in sa.inspect(conn).get_columns("users")
        }


def test_composite_foreign_keys_reject_new_cross_draw_references(prior_db):
    engine, upgrade = prior_db
    result = upgrade()
    assert result.returncode == 0, result.stderr
    with engine.begin() as conn:
        seed_two_draws(conn)
    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO tournament_team_members(draw_id,team_id,user_id) VALUES(11,10,'review-openid')"
                )
            )
    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO tournament_matches(draw_id,group_no,round_no,position,kind,team_a_id,source_outcome,is_draw,walkover,status) VALUES(11,1,1,1,'group',10,'winner',0,0,'pending')"
                )
            )
