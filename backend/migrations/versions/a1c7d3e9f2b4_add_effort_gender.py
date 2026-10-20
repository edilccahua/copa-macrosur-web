"""add effort athlete gender

Revision ID: a1c7d3e9f2b4
Revises: e7f2a9c3b5d1
Create Date: 2026-10-20

Añade a `strava_efforts` el género del atleta según Strava (`athlete_gender`,
"M" o "F"). Los títulos de damas de la fecha —la Queen of the Mountain y la
Kamikaze— se resuelven con este campo, porque hay corredoras inscritas que no
están dadas de alta en `riders` y su intento solo se reconoce por el filtro de
género del leaderboard de Strava.
"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = 'a1c7d3e9f2b4'
down_revision: Union[str, Sequence[str], None] = 'e7f2a9c3b5d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'strava_efforts',
        sa.Column('athlete_gender', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )
    op.create_index(
        'ix_strava_efforts_athlete_gender', 'strava_efforts', ['athlete_gender']
    )


def downgrade() -> None:
    op.drop_index('ix_strava_efforts_athlete_gender', table_name='strava_efforts')
    op.drop_column('strava_efforts', 'athlete_gender')
