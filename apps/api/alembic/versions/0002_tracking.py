"""Durable source observations and anonymous subscriptions."""
from alembic import op
import sqlalchemy as sa
revision='0002'
down_revision='0001'
branch_labels=None
depends_on=None

def upgrade():
    # 0001 currently bootstraps metadata; checkfirst allows fresh + existing DBs.
    metadata=sa.MetaData()
    for table in (
        sa.Table('tracked_matches',metadata,sa.Column('id',sa.String,primary_key=True),
            sa.Column('payload',sa.JSON,nullable=False),sa.Column('revision',sa.Integer,nullable=False),
            sa.Column('observed_at',sa.DateTime(timezone=True),nullable=False)),
        sa.Table('device_subscriptions',metadata,sa.Column('audience',sa.String,primary_key=True),
            sa.Column('favorites',sa.JSON,nullable=False),sa.Column('enabled',sa.Boolean,nullable=False))):
        table.create(op.get_bind(),checkfirst=True)

def downgrade():
    op.drop_table('device_subscriptions')
    op.drop_table('tracked_matches')
