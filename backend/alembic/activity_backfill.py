"""Frozen data conversion for 20261007_activity_ids; no live model imports."""
from datetime import datetime
import sqlalchemy as sa

TOURNAMENT_REFERENCES = (
    "booking_orders", "tournament_registrations", "tournament_draws", "tournament_audits",
)
POST_REFERENCES = ("match_registrations", "comments")


def backfill(connection):
    registry = sa.table("activities", sa.column("id", sa.BigInteger()),
                        sa.column("kind"), sa.column("legacy_id", sa.BigInteger()),
                        sa.column("created_at", sa.DateTime()))
    rows = {kind: connection.execute(sa.text(
        f"SELECT id, created_at FROM {table} ORDER BY id"
    )).mappings().all() for kind, table in (("post", "match_posts"), ("tournament", "tournaments"))}
    if any(row["id"] <= 0 or row["id"] > 9007199254740991 for batch in rows.values() for row in batch):
        raise RuntimeError("Historical activity ID is outside the supported positive integer range")

    def registered(ident):
        return connection.execute(sa.select(registry).where(registry.c.id == ident)).mappings().first()

    def alias(kind, ident):
        return connection.execute(sa.select(registry).where(
            registry.c.kind == kind, registry.c.legacy_id == ident,
        )).mappings().first()

    def insert(kind, row, ident=None):
        created = row["created_at"]
        if isinstance(created, str):
            created = datetime.fromisoformat(created)
        values = dict(kind=kind, legacy_id=row["id"], created_at=created or datetime.utcnow())
        if ident is not None:
            values["id"] = ident
        result = connection.execute(registry.insert().values(**values))
        return ident if ident is not None else result.lastrowid

    # Existing aliases identify rows already converted during an earlier attempt.
    pending = {kind: [row for row in batch if not (
        registered(row["id"]) and registered(row["id"])["kind"] == kind
    )] for kind, batch in rows.items()}
    conflicts = {row["id"] for row in pending["post"]} & {row["id"] for row in pending["tournament"]}
    maximum = max([row["id"] for batch in rows.values() for row in batch] + [0])
    if maximum + sum(len(batch) for batch in pending.values()) > 9007199254740991:
        raise RuntimeError("Insufficient client-safe activity ID space for historical conversion")
    # Reserve a floor above the complete old number space, including conflicts.
    # This is a one-time migration operation, never runtime MAX(id)+1 allocation.
    if connection.dialect.name == "mysql":
        connection.execute(sa.text(f"ALTER TABLE activities AUTO_INCREMENT = {maximum + 1}"))
    else:  # SQLite data conversion tests use its durable AUTOINCREMENT sequence.
        connection.execute(sa.text("INSERT INTO sqlite_sequence(name, seq) SELECT 'activities', :max WHERE NOT EXISTS (SELECT 1 FROM sqlite_sequence WHERE name='activities')"), {"max": maximum})
        connection.execute(sa.text("UPDATE sqlite_sequence SET seq = MAX(seq, :max) WHERE name='activities'"), {"max": maximum})
    for kind, batch in pending.items():
        for row in batch:
            if alias(kind, row["id"]):
                continue
            insert(kind, row, None if row["id"] in conflicts else row["id"])

    result = {}
    for kind, table, column, references, ref_type in (
        ("post", "match_posts", "post_id", POST_REFERENCES, "match_post"),
        ("tournament", "tournaments", "tournament_id", TOURNAMENT_REFERENCES, "tournament"),
    ):
        mappings = connection.execute(sa.select(registry.c.legacy_id, registry.c.id).where(
            registry.c.kind == kind, registry.c.legacy_id != registry.c.id,
        )).all()
        for old, new in mappings:
            for child in references:
                connection.execute(sa.text(f"UPDATE {child} SET {column} = :new WHERE {column} = :old"), {"old": old, "new": new})
            connection.execute(sa.text("UPDATE notifications SET ref_id = :new WHERE ref_id = :old AND ref_type = :kind"),
                               {"old": old, "new": new, "kind": ref_type})
            connection.execute(sa.text(f"UPDATE {table} SET id = :new WHERE id = :old"), {"old": old, "new": new})
        result[kind] = dict(mappings)
    return result
