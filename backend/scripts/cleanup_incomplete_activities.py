"""Review then remove structurally incomplete activities; retain global IDs and bookings.

Run only after backup with API and Celery stopped. Default is read-only; --apply
requires the fingerprint returned by that review and refuses financial relations.
"""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
import sqlalchemy as sa
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy.engine import make_url

POST_BAD = "TRIM(COALESCE(title,''))='' OR preferred_date IS NULL OR preferred_start IS NULL OR preferred_end IS NULL OR preferred_end<=preferred_start OR players_needed IS NULL OR players_needed<1"
TOURNAMENT_BAD = "TRIM(COALESCE(title,''))='' OR start_time IS NULL OR end_time IS NULL OR end_time<=start_time OR max_participants IS NULL OR max_participants<2 OR (venue_id IS NULL AND TRIM(COALESCE(address,''))='')"


def plan(connection, lock=False):
    suffix=" FOR UPDATE" if lock else ""
    posts=connection.execute(sa.text("SELECT * FROM match_posts WHERE "+POST_BAD+suffix)).mappings().all()
    tournaments=connection.execute(sa.text("SELECT * FROM tournaments WHERE "+TOURNAMENT_BAD+suffix)).mappings().all()
    safe=[];blocked=[]
    for row in tournaments:
        has_order=connection.scalar(sa.text("SELECT (SELECT COUNT(*) FROM booking_orders WHERE tournament_id=:id)+(SELECT COUNT(*) FROM tournament_registrations WHERE tournament_id=:id AND order_id IS NOT NULL)"),{"id":row["id"]})
        (blocked if has_order else safe).append(row)
    snapshot={"posts":[dict(r) for r in posts],"tournaments":[dict(r) for r in safe],"blocked":[dict(r) for r in blocked]}
    fingerprint=hashlib.sha256(json.dumps(snapshot,sort_keys=True,default=str).encode()).hexdigest()
    return {"post_ids":sorted(r["id"] for r in posts),"tournament_ids":sorted(r["id"] for r in safe),"blocked_tournament_ids":sorted(r["id"] for r in blocked),"fingerprint":fingerprint}


def cleanup(connection, expected):
    reviewed=plan(connection,True)
    if reviewed["fingerprint"]!=expected: raise RuntimeError("Cleanup selection changed; review again")
    for ident in reviewed["post_ids"]:
        args={"id":ident}
        connection.execute(sa.text("DELETE FROM comments WHERE post_id=:id AND parent_id IS NOT NULL"),args)
        connection.execute(sa.text("DELETE FROM comments WHERE post_id=:id"),args)
        connection.execute(sa.text("DELETE FROM match_registrations WHERE post_id=:id"),args)
        connection.execute(sa.text("DELETE FROM notifications WHERE ref_type='match_post' AND ref_id=:id"),args)
        connection.execute(sa.text("DELETE FROM match_posts WHERE id=:id"),args)
    for ident in reviewed["tournament_ids"]:
        args={"id":ident}
        # Clear self-dependencies before deleting matches; never disable FK checking.
        connection.execute(sa.text("UPDATE tournament_matches m JOIN tournament_draws d ON d.id=m.draw_id SET m.source_a_id=NULL,m.source_b_id=NULL WHERE d.tournament_id=:id"),args)
        connection.execute(sa.text("DELETE m FROM tournament_matches m JOIN tournament_draws d ON d.id=m.draw_id WHERE d.tournament_id=:id"),args)
        connection.execute(sa.text("DELETE m FROM tournament_team_members m JOIN tournament_draws d ON d.id=m.draw_id WHERE d.tournament_id=:id"),args)
        connection.execute(sa.text("DELETE t FROM tournament_teams t JOIN tournament_draws d ON d.id=t.draw_id WHERE d.tournament_id=:id"),args)
        for table in ("tournament_draws","tournament_audits","tournament_registrations"):
            connection.execute(sa.text("DELETE FROM "+table+" WHERE tournament_id=:id"),args)
        connection.execute(sa.text("DELETE FROM notifications WHERE ref_type='tournament' AND ref_id=:id"),args)
        connection.execute(sa.text("DELETE FROM tournaments WHERE id=:id"),args)
    # Activities are intentionally retained: globally allocated IDs never get reused.
    return reviewed


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--expected-fingerprint')
    args=parser.parse_args()
    if args.apply and not args.expected_fingerprint: parser.error('--apply requires --expected-fingerprint')
    url=make_url(os.environ['DATABASE_URL']).set(drivername='mysql+pymysql')
    engine=sa.create_engine(url,poolclass=sa.pool.NullPool)
    try:
        with engine.begin() as connection:
            result=cleanup(connection,args.expected_fingerprint) if args.apply else plan(connection)
            print(json.dumps(dict(result,applied=args.apply),sort_keys=True))
    finally: engine.dispose()
if __name__=='__main__': main()
