"""Persist the canonical tournament organizer; audit actors remain historical facts."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = '20261019_tournament_owner'
down_revision = '20261016_utr_records'
branch_labels = depends_on = None


def upgrade():
    bind = op.get_bind()
    # Resolve every historical owner before any DDL. No invented default user.
    missing = bind.execute(sa.text("""SELECT t.id FROM tournaments t
      LEFT JOIN (SELECT tournament_id,MIN(id) audit_id FROM tournament_audits
                 WHERE action='created' GROUP BY tournament_id) a ON a.tournament_id=t.id
      LEFT JOIN tournament_audits audit ON audit.id=a.audit_id
      LEFT JOIN users u ON u.id=audit.actor_id WHERE u.id IS NULL""")).scalars().all()
    if missing:
        raise RuntimeError(f'Tournament organizers must be assigned before migration: {missing}')
    op.add_column('tournaments',sa.Column('user_id',mysql.VARCHAR(64,collation='utf8mb4_bin'),nullable=True))
    bind.execute(sa.text("""UPDATE tournaments t JOIN
      (SELECT tournament_id,MIN(id) audit_id FROM tournament_audits WHERE action='created' GROUP BY tournament_id) a ON a.tournament_id=t.id
      JOIN tournament_audits audit ON audit.id=a.audit_id SET t.user_id=audit.actor_id"""))
    op.alter_column('tournaments','user_id',existing_type=mysql.VARCHAR(64,collation='utf8mb4_bin'),nullable=False)
    op.create_index('ix_tournaments_user_id','tournaments',['user_id'])
    op.create_foreign_key('fk_tournaments_organizer_user','tournaments','users',['user_id'],['id'])


def downgrade():
    raise RuntimeError('Organizer ownership is canonical data; restore a verified backup instead of dropping it')
