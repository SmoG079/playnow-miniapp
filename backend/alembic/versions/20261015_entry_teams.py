"""Create entry teams before draws and migrate conversations to typed activities."""
from alembic import op
import sqlalchemy as sa
import json

revision = "20261015_entry_teams"
down_revision = "20261015_location_names"
branch_labels = depends_on = None

DEFAULT = dict(format="knockout", discipline="singles", pairing=None, group_count=1,
               courts=["1号场地"], match_minutes=45, third_place=False, allow_draw=False,
               max_parallel=None, qualifiers_per_group=2, approval_required=False,
               waitlist_enabled=False, ungrouped_display=False)


def migrate_entries(bind):
    meta = sa.MetaData()
    events = sa.Table("tournaments", meta, autoload_with=bind)
    registrations = sa.Table("tournament_registrations", meta, autoload_with=bind)
    teams = sa.Table("tournament_entry_teams", meta, autoload_with=bind)
    draws = sa.Table("tournament_draws", meta, autoload_with=bind)
    drawteams = sa.Table("tournament_teams", meta, autoload_with=bind)
    members = sa.Table("tournament_team_members", meta, autoload_with=bind)
    for event in bind.execute(sa.select(events).order_by(events.c.id)).mappings().all():
        cfg = event["config"]
        if isinstance(cfg, str): cfg = json.loads(cfg)
        cfg = dict(DEFAULT, **(cfg or {}))
        rows = [dict(r) for r in bind.execute(sa.select(registrations).where(
            registrations.c.tournament_id == event["id"]).order_by(registrations.c.created_at, registrations.c.id)).mappings()]
        live = [r for r in rows if r["admission"] in ("active", "review") and r["status"] != "cancelled"]
        cfg["pairing"] = None if cfg["discipline"] == "singles" else (
            "fixed" if any(r["pairing"] == "fixed" for r in live) else "random")
        size = 1 if cfg["discipline"] == "singles" else 2
        maximum = event["max_participants"] or max(16, len(live))
        maximum = max(maximum, size * cfg["group_count"] * 2)
        maximum += (-maximum) % size
        bind.execute(events.update().where(events.c.id == event["id"]).values(config=cfg, max_participants=maximum))
        pool = []
        for group in range(1, cfg["group_count"] + 1):
            count = maximum // size // cfg["group_count"] + int(group <= (maximum // size) % cfg["group_count"])
            for position in range(1, count + 1):
                ident = bind.execute(teams.insert().values(tournament_id=event["id"], group_no=group, position=position)).inserted_primary_key[0]
                pool.append(dict(id=ident, group=group, occupants={}))
        by_user = {r["user_id"]: r for r in live}
        assigned = set()

        def place(block, group=0):
            choices = [t for t in pool if (not group or t["group"] == group) and len(t["occupants"]) + len(block) <= size]
            for team in choices:
                seats = []
                for r in block:
                    seat = (1 if r["gender"] == "male" else 2) if cfg["discipline"] == "mixed" else next((n for n in range(1, size + 1) if n not in team["occupants"] and n not in seats), None)
                    if seat is None or seat in seats or seat in team["occupants"]: break
                    seats.append(seat)
                else:
                    for r, seat in zip(block, seats):
                        team["occupants"][seat] = r
                        assigned.add(r["user_id"])
                        bind.execute(registrations.update().where(registrations.c.id == r["id"]).values(
                            entry_team_id=team["id"], entry_seat=seat, requested_group=team["group"], pairing=cfg["pairing"] or "random"))
                    return True
            return False

        # Preserve published/current draw teams and their groups, then mutual
        # partner selections. No draw snapshots or match results are modified.
        draw = bind.execute(sa.select(draws).where(draws.c.tournament_id == event["id"]).order_by(draws.c.version.desc()).limit(1)).mappings().first()
        if draw:
            for team in bind.execute(sa.select(drawteams).where(drawteams.c.draw_id == draw["id"])).mappings():
                ids = list(bind.execute(sa.select(members.c.user_id).where(members.c.team_id == team["id"])).scalars())
                block = [by_user[u] for u in ids if u in by_user and u not in assigned]
                if block and not place(block, team["group_no"]):
                    raise RuntimeError("Cannot preserve existing draw team during entry migration")
        for r in live:
            mate = by_user.get(r["partner_user_id"])
            if r["user_id"] not in assigned and mate and mate["user_id"] not in assigned and mate["partner_user_id"] == r["user_id"]:
                if not place([r, mate], r["requested_group"] or mate["requested_group"]):
                    raise RuntimeError("Cannot preserve fixed partners during entry migration")
        for r in live:
            if r["user_id"] in assigned: continue
            if not place([r], r["requested_group"]) and r["admission"] == "active":
                raise RuntimeError("Cannot migrate an active entrant without a team seat")
        for team in pool:
            people = list(team["occupants"].values())
            for r in people:
                mate = next((p["user_id"] for p in people if p["user_id"] != r["user_id"]), None)
                bind.execute(registrations.update().where(registrations.c.id == r["id"]).values(partner_user_id=mate))


def upgrade():
    op.create_table("tournament_entry_teams",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tournament_id", sa.BigInteger(), sa.ForeignKey("tournaments.id"), nullable=False),
        sa.Column("group_no", sa.Integer(), nullable=False), sa.Column("position", sa.Integer(), nullable=False),
        sa.UniqueConstraint("tournament_id", "group_no", "position", name="uq_entry_team_position"))
    op.add_column("tournament_registrations", sa.Column("entry_team_id", sa.BigInteger()))
    op.add_column("tournament_registrations", sa.Column("entry_seat", sa.Integer()))
    op.create_foreign_key("fk_registration_entry_team", "tournament_registrations", "tournament_entry_teams", ["entry_team_id"], ["id"])
    op.create_unique_constraint("uq_entry_team_seat", "tournament_registrations", ["entry_team_id", "entry_seat"])
    op.create_check_constraint("ck_entry_team_seat", "tournament_registrations", "(entry_team_id IS NULL AND entry_seat IS NULL) OR (entry_team_id IS NOT NULL AND entry_seat IS NOT NULL AND entry_seat IN (1, 2))")
    bind = op.get_bind()
    migrate_entries(bind)
    op.drop_column("tournament_registrations", "pairing")
    op.alter_column("tournaments", "config", existing_type=sa.JSON(), nullable=False)
    for fk in sa.inspect(bind).get_foreign_keys("direct_conversations"):
        if fk["constrained_columns"] == ["post_id"]:
            op.drop_constraint(fk["name"], "direct_conversations", type_="foreignkey")
    op.alter_column("direct_conversations", "post_id", new_column_name="activity_id", existing_type=sa.BigInteger(), existing_nullable=False)
    op.create_foreign_key("fk_conversation_activity", "direct_conversations", "activities", ["activity_id"], ["id"])


def downgrade():
    raise RuntimeError("Entry teams and conversation contexts cannot be discarded; restore a verified backup")
