"""Persist booking ownership/quotes and enforce reviewed reference integrity."""

from alembic import op
import sqlalchemy as sa
from review_integrity import plan_integrity
from app.services.public_identity import public_user_id

revision = "20261009_review_integrity"
down_revision = "20261008_optional_host"
branch_labels = depends_on = None


def upgrade():
    conn = op.get_bind()
    if conn.dialect.name != "mysql":
        raise RuntimeError("Review migration requires isolated MySQL rehearsal")
    details, owners = plan_integrity(conn)  # All historical checks precede any DDL.
    op.add_column("users", sa.Column("public_id", sa.String(36), nullable=True))
    users = conn.execute(sa.text("SELECT id FROM users")).scalars().all()
    for ident in users:
        conn.execute(
            sa.text("UPDATE users SET public_id=:public WHERE id=:id"),
            {"id": ident, "public": public_user_id(ident)},
        )
    op.alter_column("users", "public_id", existing_type=sa.String(36), nullable=False)
    op.create_table(
        "private_uploads",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "user_id",
            sa.dialects.mysql.VARCHAR(64, collation="utf8mb4_bin"),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("backend", sa.String(16), nullable=False),
        sa.Column("content_type", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime()),
        mysql_charset="utf8mb4",
    )
    op.create_unique_constraint("uq_user_public_id", "users", ["public_id"])
    op.add_column(
        "venue_time_slots",
        sa.Column("booking_order_id", sa.BigInteger(), nullable=True),
    )
    op.create_index(
        "ix_venue_time_slots_booking_order_id", "venue_time_slots", ["booking_order_id"]
    )
    op.create_foreign_key(
        "fk_slot_booking_order",
        "venue_time_slots",
        "booking_orders",
        ["booking_order_id"],
        ["id"],
    )
    op.create_table(
        "booking_slots",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "order_id",
            sa.BigInteger(),
            sa.ForeignKey("booking_orders.id"),
            nullable=False,
        ),
        sa.Column(
            "slot_id",
            sa.BigInteger(),
            sa.ForeignKey("venue_time_slots.id"),
            nullable=False,
        ),
        sa.Column("amount", sa.DECIMAL(10, 2), nullable=True),
        sa.UniqueConstraint("order_id", "slot_id", name="uq_booking_slot"),
        mysql_charset="utf8mb4",
    )
    if details:
        conn.execute(
            sa.table(
                "booking_slots",
                sa.column("order_id"),
                sa.column("slot_id"),
                sa.column("amount"),
            ).insert(),
            details,
        )
    for slot_id, order_id in owners.items():
        conn.execute(
            sa.text(
                "UPDATE venue_time_slots SET booking_order_id=:order_id WHERE id=:slot_id"
            ),
            {"slot_id": slot_id, "order_id": order_id},
        )
    op.create_unique_constraint(
        "uq_settlement_order", "settlement_records", ["order_id"]
    )
    op.create_index(
        "idx_pending_order_recovery",
        "booking_orders",
        ["business_type", "status", "updated_at", "id"],
    )
    op.create_unique_constraint("uq_team_draw", "tournament_teams", ["id", "draw_id"])
    op.create_unique_constraint(
        "uq_match_draw", "tournament_matches", ["id", "draw_id"]
    )
    op.create_foreign_key(
        "fk_member_team_draw",
        "tournament_team_members",
        "tournament_teams",
        ["team_id", "draw_id"],
        ["id", "draw_id"],
    )
    for column, tag, target in [
        ("team_a_id", "team_a", "tournament_teams"),
        ("team_b_id", "team_b", "tournament_teams"),
        ("winner_id", "winner", "tournament_teams"),
        ("source_a_id", "source_a", "tournament_matches"),
        ("source_b_id", "source_b", "tournament_matches"),
    ]:
        op.create_foreign_key(
            f"fk_match_{tag}_draw",
            "tournament_matches",
            target,
            [column, "draw_id"],
            ["id", "draw_id"],
        )


def downgrade():
    raise RuntimeError(
        "Ownership and historical quotes require backup-based recovery, not destructive downgrade"
    )
