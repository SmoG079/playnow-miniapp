"""Tournament management; historical events remain unconfigured."""

from alembic import op
import sqlalchemy as sa

revision = "20261007_tournaments"
down_revision = "20261007_schema_alignment"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "tournament_registrations",
        sa.Column("requested_group", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("tournaments", sa.Column("config", sa.JSON(), nullable=True))
    op.add_column(
        "tournaments", sa.Column("address", sa.String(length=256), nullable=True)
    )
    op.add_column(
        "tournaments", sa.Column("contact_name", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "tournaments", sa.Column("contact_phone", sa.String(length=20), nullable=True)
    )
    op.add_column(
        "tournaments",
        sa.Column("auto_title", sa.Boolean(), nullable=False, server_default="0"),
    )
    op.add_column(
        "tournaments", sa.Column("registration_deadline", sa.DateTime(), nullable=True)
    )
    op.add_column(
        "tournaments", sa.Column("cancellation_deadline", sa.DateTime(), nullable=True)
    )
    op.add_column(
        "tournaments",
        sa.Column(
            "registration_closed", sa.Boolean(), nullable=False, server_default="0"
        ),
    )
    op.add_column(
        "tournaments",
        sa.Column("roster_frozen", sa.Boolean(), nullable=False, server_default="0"),
    )
    op.add_column(
        "tournaments",
        sa.Column("draw_version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "tournaments",
        sa.Column(
            "published_version", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    op.add_column(
        "tournament_registrations",
        sa.Column(
            "approval", sa.String(length=16), nullable=False, server_default="approved"
        ),
    )
    op.add_column(
        "tournament_registrations",
        sa.Column(
            "payment", sa.String(length=16), nullable=False, server_default="none"
        ),
    )
    op.add_column(
        "tournament_registrations",
        sa.Column(
            "admission", sa.String(length=16), nullable=False, server_default="active"
        ),
    )
    op.add_column(
        "tournament_registrations",
        sa.Column("gender", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "tournament_registrations",
        sa.Column(
            "pairing", sa.String(length=16), nullable=False, server_default="random"
        ),
    )
    op.add_column(
        "tournament_registrations",
        sa.Column(
            "partner_user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=True
        ),
    )
    op.add_column(
        "tournament_registrations",
        sa.Column("invite_token", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "tournament_registrations",
        sa.Column("seat_expires_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "tournament_registrations",
        sa.Column("review_reason", sa.String(length=256), nullable=True),
    )
    op.add_column(
        "booking_orders",
        sa.Column(
            "tournament_id",
            sa.BigInteger(),
            sa.ForeignKey("tournaments.id"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_booking_orders_tournament_id", "booking_orders", ["tournament_id"]
    )
    op.add_column(
        "booking_orders",
        sa.Column(
            "business_type",
            sa.String(length=16),
            nullable=False,
            server_default="booking",
        ),
    )
    op.create_unique_constraint(
        "uq_registration_invite", "tournament_registrations", ["invite_token"]
    )
    op.alter_column(
        "booking_orders", "venue_id", existing_type=sa.BigInteger(), nullable=True
    )
    op.execute(
        "UPDATE booking_orders o JOIN tournament_registrations r ON r.order_id=o.id SET o.business_type='tournament', o.tournament_id=r.tournament_id"
    )
    op.execute(
        "UPDATE tournament_registrations r JOIN tournaments t ON t.id=r.tournament_id SET r.payment=IF(t.entry_fee>0,'unverified','none'), r.admission=IF(r.status='cancelled','cancelled','active')"
    )
    op.create_table(
        "tournament_draws",
        sa.Column(
            "id", sa.BigInteger(), nullable=False, primary_key=True, autoincrement=True
        ),
        sa.Column(
            "tournament_id",
            sa.BigInteger(),
            sa.ForeignKey("tournaments.id"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(length=16), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("seed", sa.String(length=64), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column(
            "created_by", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("reason", sa.String(length=256), nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("tie_orders", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint(
            "tournament_id", "version", name="uq_tournament_draw_version"
        ),
        sa.UniqueConstraint(
            "tournament_id", "idempotency_key", name="uq_tournament_draw_key"
        ),
    )
    op.create_table(
        "tournament_teams",
        sa.Column(
            "id", sa.BigInteger(), nullable=False, primary_key=True, autoincrement=True
        ),
        sa.Column(
            "draw_id",
            sa.BigInteger(),
            sa.ForeignKey("tournament_draws.id"),
            nullable=False,
        ),
        sa.Column("group_no", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("origin_group", sa.Integer(), nullable=True),
    )
    op.create_index("ix_tournament_teams_draw_id", "tournament_teams", ["draw_id"])
    op.create_table(
        "tournament_team_members",
        sa.Column(
            "id", sa.BigInteger(), nullable=False, primary_key=True, autoincrement=True
        ),
        sa.Column(
            "draw_id",
            sa.BigInteger(),
            sa.ForeignKey("tournament_draws.id"),
            nullable=False,
        ),
        sa.Column(
            "team_id",
            sa.BigInteger(),
            sa.ForeignKey("tournament_teams.id"),
            nullable=False,
        ),
        sa.Column(
            "user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.UniqueConstraint("draw_id", "user_id", name="uq_draw_member"),
    )
    op.create_table(
        "tournament_matches",
        sa.Column(
            "id", sa.BigInteger(), nullable=False, primary_key=True, autoincrement=True
        ),
        sa.Column(
            "draw_id",
            sa.BigInteger(),
            sa.ForeignKey("tournament_draws.id"),
            nullable=False,
        ),
        sa.Column("group_no", sa.Integer(), nullable=False),
        sa.Column("round_no", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column(
            "team_a_id",
            sa.BigInteger(),
            sa.ForeignKey("tournament_teams.id"),
            nullable=True,
        ),
        sa.Column(
            "team_b_id",
            sa.BigInteger(),
            sa.ForeignKey("tournament_teams.id"),
            nullable=True,
        ),
        sa.Column(
            "source_a_id",
            sa.BigInteger(),
            sa.ForeignKey("tournament_matches.id"),
            nullable=True,
        ),
        sa.Column(
            "source_b_id",
            sa.BigInteger(),
            sa.ForeignKey("tournament_matches.id"),
            nullable=True,
        ),
        sa.Column("source_outcome", sa.String(length=16), nullable=False),
        sa.Column(
            "winner_id",
            sa.BigInteger(),
            sa.ForeignKey("tournament_teams.id"),
            nullable=True,
        ),
        sa.Column("score", sa.String(length=128), nullable=True),
        sa.Column("is_draw", sa.Boolean(), nullable=False),
        sa.Column("walkover", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("court", sa.String(length=64), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(), nullable=True),
        sa.Column("scheduled_end", sa.DateTime(), nullable=True),
        sa.UniqueConstraint(
            "draw_id", "group_no", "round_no", "position", "kind", name="uq_draw_match"
        ),
    )
    op.create_index("ix_tournament_matches_draw_id", "tournament_matches", ["draw_id"])
    op.create_table(
        "tournament_audits",
        sa.Column(
            "id", sa.BigInteger(), nullable=False, primary_key=True, autoincrement=True
        ),
        sa.Column(
            "tournament_id",
            sa.BigInteger(),
            sa.ForeignKey("tournaments.id"),
            nullable=False,
        ),
        sa.Column(
            "actor_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=True
        ),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_tournament_audits_tournament_id", "tournament_audits", ["tournament_id"]
    )


def downgrade():
    raise RuntimeError(
        "Tournament results and money records require a verified backup; no destructive automatic downgrade"
    )
