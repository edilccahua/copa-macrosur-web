"""add laps and unique bib

Revision ID: 9f1a2b3c4d5e
Revises: b5d638d28e84
Create Date: 2026-10-15 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9f1a2b3c4d5e'
down_revision: Union[str, Sequence[str], None] = 'b5d638d28e84'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: vueltas por circuito y unicidad de dorsal por fecha."""
    with op.batch_alter_table('stages') as batch:
        batch.add_column(sa.Column('laps', sa.Integer(), nullable=False, server_default='1'))
        batch.add_column(sa.Column('strava_route_url', sa.String(), nullable=True))

    with op.batch_alter_table('stage_entries') as batch:
        batch.add_column(sa.Column('laps', sa.Integer(), nullable=False, server_default='1'))
        batch.create_unique_constraint(
            'uq_stage_entry_stage_bib', ['stage_id', 'bib_number']
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('stage_entries') as batch:
        batch.drop_constraint('uq_stage_entry_stage_bib', type_='unique')
        batch.drop_column('laps')

    with op.batch_alter_table('stages') as batch:
        batch.drop_column('strava_route_url')
        batch.drop_column('laps')
