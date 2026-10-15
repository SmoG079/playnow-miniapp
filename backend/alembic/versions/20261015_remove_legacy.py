"""Migrate obsolete representations once and remove runtime compatibility data."""
import sqlalchemy as sa
from alembic import op

revision = "20261015_remove_legacy"
down_revision = "20261015_post_people"
branch_labels = depends_on = None


def migrate_positions(teams, matches):
    """Freeze the former reconstruction algorithm for this one-time conversion."""
    if any(match["kind"] == "knockout" for match in matches):
        return [dict(group_no=match["group_no"], position=2*match["position"]+side,
                     team_id=match[f"team_{letter}_id"])
                for match in matches if match["kind"] == "knockout" and match["round_no"] == 1
                for side, letter in enumerate(("a", "b"))]
    positions = []
    for group in sorted({team["group_no"] for team in teams}):
        members = [team["id"] for team in teams if team["group_no"] == group]
        size = len(members) + len(members) % 2
        ordered = [None] * size
        for match in matches:
            if match["group_no"] == group and match["round_no"] == 1:
                ordered[match["position"]] = match["team_a_id"]
                ordered[size - 1 - match["position"]] = match["team_b_id"]
        missing = [ident for ident in members if ident not in ordered]
        if len(missing) > 1:
            raise RuntimeError("Cannot reconstruct historical round-robin positions")
        if missing:
            ordered[0] = missing[0]
        positions.extend(dict(group_no=group, position=position, team_id=ident)
                         for position, ident in enumerate(ident for ident in ordered if ident is not None))
    return positions


def upgrade():
    bind = op.get_bind()
    metadata = sa.MetaData()
    orders = sa.Table("booking_orders", metadata, autoload_with=bind)
    details = sa.Table("booking_slots", metadata, autoload_with=bind)
    slots = sa.Table("venue_time_slots", metadata, autoload_with=bind)
    # Do not infer prices, ownership, payments or refunds during format migration.
    for order in bind.execute(sa.select(orders)).mappings():
        ids = list(order["slot_ids"] or [])
        if "slot_id" in order and order["slot_id"] is not None:
            ids.append(order["slot_id"])
        existing = set(bind.execute(sa.select(details.c.slot_id).where(details.c.order_id == order["id"])).scalars())
        ids = set(ids) | existing
        if any(not isinstance(ident, int) or isinstance(ident, bool) or ident < 1 for ident in ids):
            raise RuntimeError(f"Invalid slot references on order {order['id']}")
        selected = list(bind.execute(sa.select(slots.c.id).where(slots.c.id.in_(ids))
            .order_by(slots.c.date, slots.c.start_time, slots.c.id)).scalars())
        if set(selected) != ids:
            raise RuntimeError(f"Missing slot references on order {order['id']}")
        if order["business_type"] == "booking" and not selected:
            raise RuntimeError(f"Booking {order['id']} has no recoverable slot intent")
        bind.execute(orders.update().where(orders.c.id == order["id"]).values(slot_ids=selected))
        for ident in ids - existing:
            bind.execute(details.insert().values(order_id=order["id"], slot_id=ident, amount=None))
    op.alter_column("booking_orders", "slot_ids", existing_type=sa.JSON(), nullable=False)
    if "slot_id" in orders.c:
        for foreign in sa.inspect(bind).get_foreign_keys("booking_orders"):
            if foreign["constrained_columns"] == ["slot_id"]:
                op.drop_constraint(foreign["name"], "booking_orders", type_="foreignkey")
        op.drop_column("booking_orders", "slot_id")

    events = sa.Table("tournaments", metadata, autoload_with=bind)
    for event in bind.execute(sa.select(events)).mappings():
        prizes = event["prizes"]
        if prizes is None:
            text = event.get("prize") or ""
            prizes = [{"name": "奖项", "description": text}] if text.strip() else []
        if not isinstance(prizes, list) or any(not isinstance(p, dict) or not isinstance(p.get("name"), str)
                or not isinstance(p.get("description"), str) for p in prizes):
            raise RuntimeError(f"Invalid structured prizes on tournament {event['id']}")
        bind.execute(events.update().where(events.c.id == event["id"]).values(prizes=prizes))
    op.alter_column("tournaments", "prizes", existing_type=sa.JSON(), nullable=False)
    if "prize" in events.c:
        op.drop_column("tournaments", "prize")

    draws = sa.Table("tournament_draws", metadata, autoload_with=bind)
    teams = sa.Table("tournament_teams", metadata, autoload_with=bind)
    matches = sa.Table("tournament_matches", metadata, autoload_with=bind)
    for draw in bind.execute(sa.select(draws)).mappings():
        snapshot = dict(draw["snapshot"] or {})
        if snapshot.get("positions") is None:
            roster = list(bind.execute(sa.select(teams).where(teams.c.draw_id == draw["id"])
                .order_by(teams.c.id)).mappings())
            rows = list(bind.execute(sa.select(matches).where(matches.c.draw_id == draw["id"])
                .order_by(matches.c.round_no, matches.c.position, matches.c.id)).mappings())
            snapshot["positions"] = migrate_positions(roster, rows)
            bind.execute(draws.update().where(draws.c.id == draw["id"]).values(snapshot=snapshot))

    if "price_override" in {column["name"] for column in sa.inspect(bind).get_columns("venue_time_slots")}:
        # Current quotes already use venue price rules, not this obsolete column.
        op.drop_column("venue_time_slots", "price_override")

    columns = {column["name"] for column in sa.inspect(bind).get_columns("activities")}
    if "legacy_id" in columns:
        op.drop_constraint("uq_activity_legacy", "activities", type_="unique")
        op.drop_column("activities", "legacy_id")
    if "user_id_migrations" in sa.inspect(bind).get_table_names():
        op.drop_table("user_id_migrations")


def downgrade():
    raise RuntimeError("Obsolete fields were migrated and removed; restore a verified backup instead")
