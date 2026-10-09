"""Read-only preflight; report only table identifiers, never customer details."""

import json
import sqlalchemy as sa


def plan_integrity(conn):
    errors, details, owners = [], [], {}
    slots = {
        r["id"]: r
        for r in conn.execute(
            sa.text(
                "SELECT id,venue_id,date,start_time,end_time,status,locked_by FROM venue_time_slots"
            )
        ).mappings()
    }
    for row in conn.execute(
        sa.text(
            "SELECT id FROM venue_time_slots WHERE price_override<0 OR end_time<=start_time"
        )
    ):
        errors.append(f"venue_time_slots:{row[0]}: invalid price/interval")
    for left, right in conn.execute(
        sa.text(
            "SELECT a.id,b.id FROM venue_time_slots a JOIN venue_time_slots b "
            "ON a.venue_id=b.venue_id AND a.date=b.date AND a.id<b.id "
            "AND a.start_time<b.end_time AND a.end_time>b.start_time"
        )
    ):
        errors.append(f"venue_time_slots:{left},{right}: overlapping intervals")
    for row in conn.execute(
        sa.text("SELECT id,price_per_hour,price_rules FROM venues")
    ).mappings():
        try:
            from app.schemas.schemas import VenueUpdate

            rules = (
                json.loads(row["price_rules"])
                if isinstance(row["price_rules"], str)
                else row["price_rules"]
            )
            VenueUpdate(price_per_hour=row["price_per_hour"], price_rules=rules)
        except (ValueError, TypeError):
            errors.append(f"venues:{row['id']}: invalid pricing")
    for order in conn.execute(
        sa.text(
            "SELECT id,user_id,venue_id,slot_id,slot_ids,status,business_type FROM booking_orders"
        )
    ).mappings():
        if order["business_type"] != "booking":
            continue
        raw = order["slot_ids"]
        ids = json.loads(raw) if isinstance(raw, str) else raw
        if ids is not None and not isinstance(ids, list):
            errors.append(f"booking_orders:{order['id']}: invalid slot JSON")
            continue
        ids = ids or ([order["slot_id"]] if order["slot_id"] else [])
        if (
            not isinstance(ids, list)
            or any(type(i) is not int or i not in slots for i in ids)
            or len(set(ids)) != len(ids)
        ):
            errors.append(f"booking_orders:{order['id']}: invalid slot references")
            continue
        if (
            not ids
            and order["status"] in ("pending", "paid", "refunding", "completed")
            and order["venue_id"] is not None
        ):
            errors.append(f"booking_orders:{order['id']}: missing slot references")
        if order["slot_id"] is not None and order["slot_id"] not in ids:
            errors.append(f"booking_orders:{order['id']}: first slot mismatch")
        selected = [slots[i] for i in ids]
        selected.sort(key=lambda r: r["start_time"])
        if (
            any(r["venue_id"] != order["venue_id"] for r in selected)
            or len({r["date"] for r in selected}) > 1
            or any(
                a["end_time"] != b["start_time"] for a, b in zip(selected, selected[1:])
            )
        ):
            errors.append(
                f"booking_orders:{order['id']}: venue/date/continuity mismatch"
            )
        for ident in ids:
            details.append(dict(order_id=order["id"], slot_id=ident, amount=None))
            if order["status"] in (
                "pending",
                "paid",
                "refunding",
                "completed",
            ) and slots[ident]["status"] in (
                "locked",
                "booked",
            ):
                if ident in owners:
                    errors.append(f"venue_time_slots:{ident}: multiple active orders")
                if (
                    slots[ident]["status"] == "locked"
                    and slots[ident]["locked_by"] != order["user_id"]
                ):
                    errors.append(f"venue_time_slots:{ident}: lock owner mismatch")
                owners[ident] = order["id"]
    for ident, slot in slots.items():
        if slot["status"] in ("locked", "booked") and ident not in owners:
            errors.append(f"venue_time_slots:{ident}: missing active booking owner")
    for row in conn.execute(
        sa.text(
            "SELECT order_id FROM settlement_records GROUP BY order_id HAVING COUNT(*)>1"
        )
    ):
        errors.append(f"settlement_records: order {row[0]} duplicated")
    refs = [("tournament_team_members", "team_id", "tournament_teams")]
    refs += [
        ("tournament_matches", c, "tournament_teams")
        for c in ("team_a_id", "team_b_id", "winner_id")
    ]
    refs += [
        ("tournament_matches", c, "tournament_matches")
        for c in ("source_a_id", "source_b_id")
    ]
    for table, column, target in refs:
        for row in conn.execute(
            sa.text(
                f"SELECT x.id FROM {table} x LEFT JOIN {target} y ON x.{column}=y.id WHERE x.{column} IS NOT NULL AND (y.id IS NULL OR x.draw_id<>y.draw_id)"
            )
        ):
            errors.append(f"{table}:{row[0]}: {column} crosses draw")
    if errors:
        raise RuntimeError(
            "Integrity preflight refused before DDL:\n" + "\n".join(errors)
        )
    return details, owners
