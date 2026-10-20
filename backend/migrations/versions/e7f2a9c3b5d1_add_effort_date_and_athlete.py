"""add effort date and athlete id

Revision ID: e7f2a9c3b5d1
Revises: c4d8e1f2a9b0
Create Date: 2026-10-20

Añade a `strava_efforts` la fecha del intento (`measured_on`) y el
identificador del atleta en Strava (`strava_athlete_id`).

Sin la fecha no se puede distinguir un intento de la carrera de otro de años
atrás: Strava lista en un mismo segmento los intentos de 2019, 2023, 2024 y los
de la fecha de la carrera, todos juntos.
"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = 'e7f2a9c3b5d1'
down_revision: Union[str, Sequence[str], None] = 'c4d8e1f2a9b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'strava_efforts',
        sa.Column('measured_on', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )
    op.add_column(
        'strava_efforts',
        sa.Column('strava_athlete_id', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )
    op.create_index('ix_strava_efforts_measured_on', 'strava_efforts', ['measured_on'])
    op.create_index(
        'ix_strava_efforts_strava_athlete_id', 'strava_efforts', ['strava_athlete_id']
    )


def downgrade() -> None:
    op.drop_index('ix_strava_efforts_strava_athlete_id', table_name='strava_efforts')
    op.drop_index('ix_strava_efforts_measured_on', table_name='strava_efforts')
    op.drop_column('strava_efforts', 'strava_athlete_id')
    op.drop_column('strava_efforts', 'measured_on')
