"""add route_summits and strava segment metadata

Revision ID: c4d8e1f2a9b0
Revises: b7459cffc816
Create Date: 2026-10-19

Añade la tabla de cimas de la ruta (`route_summits`) y enriquece
`strava_segments` con la ubicación, las altitudes, el tipo de tramo
(CLIMB/DESCENT/FLAT) y la categoría de puerto.
"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = 'c4d8e1f2a9b0'
down_revision: Union[str, Sequence[str], None] = 'b7459cffc816'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'route_summits',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('stage_id', sa.Integer(), nullable=False),
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('category', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=''),
        sa.Column('distance_km', sa.Float(), nullable=False, server_default='0'),
        sa.Column('elevation_m', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('climb_gain_m', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('avg_grade_pct', sa.Float(), nullable=False, server_default='0'),
        sa.Column('max_grade_pct', sa.Float(), nullable=False, server_default='0'),
        sa.Column('lat', sa.Float(), nullable=True),
        sa.Column('lon', sa.Float(), nullable=True),
        sa.Column('name_source', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default='geo'),
        sa.ForeignKeyConstraint(['stage_id'], ['stages.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_route_summits_stage_id', 'route_summits', ['stage_id'])

    op.add_column('strava_segments', sa.Column('location', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column('strava_segments', sa.Column('elevation_min_m', sa.Integer(), nullable=True))
    op.add_column('strava_segments', sa.Column('elevation_max_m', sa.Integer(), nullable=True))
    op.add_column(
        'strava_segments',
        sa.Column('kind', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default='FLAT'),
    )
    op.add_column('strava_segments', sa.Column('category', sqlmodel.sql.sqltypes.AutoString(), nullable=True))


def downgrade() -> None:
    op.drop_column('strava_segments', 'category')
    op.drop_column('strava_segments', 'kind')
    op.drop_column('strava_segments', 'elevation_max_m')
    op.drop_column('strava_segments', 'elevation_min_m')
    op.drop_column('strava_segments', 'location')
    op.drop_index('ix_route_summits_stage_id', table_name='route_summits')
    op.drop_table('route_summits')
