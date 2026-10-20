"""add official figures and prize tiers

- `stages.distance_km` y `stages.elevation_gain_m` pasan a NULLABLE: la Fecha 4
  (Quequeña Xtreme III) no tiene ruta, ni GPX, ni Strava, así que su distancia
  y su desnivel no se pueden afirmar. En la BD valían 45 km y +950 m, inventados
  en el plan. `NULL` = "por confirmar", que es lo que ya decía la página.
- `stages.official_results` y `stages.official_points`: las cifras PUBLICADAS
  en el PDF oficial de resultados, para contrastarlas con las que recalcula el
  motor (specs/01 §3.1). En Z Xtreme difieren: el PDF no imprime el 6º lugar de
  OPEN DAMAS (554 pts) y el motor, al rellenar el hueco, reparte 555.
- Tabla `prize_tiers`: la escala de premios en dólares por categoría y ámbito
  (por fecha 70/50/30, acumulada 300/200/100).

Revision ID: b3e1a7c9d4f2
Revises: a1c7d3e9f2b4
Create Date: 2026-10-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b3e1a7c9d4f2'
down_revision: Union[str, Sequence[str], None] = 'a1c7d3e9f2b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # La distancia y el desnivel pueden no existir: se dejan en NULL.
    with op.batch_alter_table('stages') as batch:
        batch.alter_column('distance_km', existing_type=sa.Float(), nullable=True)
        batch.alter_column('elevation_gain_m', existing_type=sa.Integer(), nullable=True)
        batch.add_column(sa.Column('official_results', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('official_points', sa.Integer(), nullable=True))

    op.create_table(
        'prize_tiers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('scope', sa.String(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('amount_usd', sa.Integer(), nullable=False),
        sa.Column('label', sa.String(), nullable=False),
        sa.Column('currency', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_prize_tiers_scope'), 'prize_tiers', ['scope'], unique=False)

    # Escala de premios: por categoría y por ámbito.
    op.bulk_insert(
        sa.table(
            'prize_tiers',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('scope', sa.String(), nullable=False),
            sa.Column('position', sa.Integer(), nullable=False),
            sa.Column('amount_usd', sa.Integer(), nullable=False),
            sa.Column('label', sa.String(), nullable=False),
            sa.Column('currency', sa.String(), nullable=False),
        ),
        [
            {'id': 1, 'scope': 'FECHA', 'position': 1, 'amount_usd': 70,
             'label': '1er puesto de cada categoría', 'currency': 'USD'},
            {'id': 2, 'scope': 'FECHA', 'position': 2, 'amount_usd': 50,
             'label': '2do puesto de cada categoría', 'currency': 'USD'},
            {'id': 3, 'scope': 'FECHA', 'position': 3, 'amount_usd': 30,
             'label': '3er puesto de cada categoría', 'currency': 'USD'},
            {'id': 4, 'scope': 'ACUMULADO', 'position': 1, 'amount_usd': 300,
             'label': 'Campeón de cada categoría', 'currency': 'USD'},
            {'id': 5, 'scope': 'ACUMULADO', 'position': 2, 'amount_usd': 200,
             'label': 'Subcampeón de cada categoría', 'currency': 'USD'},
            {'id': 6, 'scope': 'ACUMULADO', 'position': 3, 'amount_usd': 100,
             'label': 'Tercer puesto de cada categoría', 'currency': 'USD'},
        ],
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_prize_tiers_scope'), table_name='prize_tiers')
    op.drop_table('prize_tiers')

    with op.batch_alter_table('stages') as batch:
        batch.drop_column('official_points')
        batch.drop_column('official_results')
        batch.alter_column('elevation_gain_m', existing_type=sa.Integer(), nullable=False)
        batch.alter_column('distance_km', existing_type=sa.Float(), nullable=False)
