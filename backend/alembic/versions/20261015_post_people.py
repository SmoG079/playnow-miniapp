"""Replace external places with minimum/maximum total attendance."""
from alembic import op
import sqlalchemy as sa

revision = "20261015_post_people"
down_revision = "20261014_direct_messages"
branch_labels = depends_on = None


def upgrade():
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("match_posts")}
    if "min_players" not in columns:
        op.add_column("match_posts", sa.Column("min_players", sa.Integer(), nullable=False, server_default="2"))
    if "max_players" not in columns:
        op.add_column("match_posts", sa.Column("max_players", sa.Integer(), nullable=True))
    # An organizer is already attending; keep any historical self-registration
    # as cancelled history instead of counting them twice or deleting records.
    bind.execute(sa.text("""
        UPDATE match_registrations r JOIN match_posts p ON p.id = r.post_id
        SET r.status = 'cancelled'
        WHERE r.user_id = p.user_id AND r.status IN ('approved', 'pending')
    """))
    if "players_needed" in columns:
        bind.execute(sa.text("""
            UPDATE match_posts p SET p.max_players = GREATEST(
                COALESCE(p.players_needed, 1) + 1, 2,
                (SELECT COUNT(*) + 1 FROM match_registrations r
                 WHERE r.post_id = p.id AND r.status = 'approved'))
        """))
    # Normalize partial deployments as well as migrated rows before NOT NULL.
    bind.execute(sa.text("UPDATE match_posts SET max_players = 2 WHERE max_players IS NULL OR max_players < 2"))
    bind.execute(sa.text("UPDATE match_posts SET min_players = 2 WHERE min_players > max_players OR min_players < 2"))
    bind.execute(sa.text("""
        UPDATE match_posts p SET p.status = CASE
            WHEN (SELECT COUNT(*) + 1 FROM match_registrations r
                  WHERE r.post_id = p.id AND r.status = 'approved') >= p.max_players
            THEN 'full' ELSE 'open' END
        WHERE p.status IN ('open', 'full')
    """))
    op.alter_column("match_posts", "max_players", existing_type=sa.Integer(), nullable=False, server_default="2")
    if "players_needed" in columns:
        op.drop_column("match_posts", "players_needed")


def downgrade():
    raise RuntimeError("Preserve configured attendance targets; restore a verified backup instead")
