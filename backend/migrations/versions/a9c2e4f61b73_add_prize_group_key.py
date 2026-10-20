"""add_prize_group_key

Añade `group_key` a `prize_tiers`.

El premio acumulado ya no es "por categoría": es por agrupación (PRO,
NORMAL) y ahora también por equipo. La columna dice a qué agrupación
pertenece la fila:

    · NULL         → el premio por fecha (cada una de las 11 categorías)
    · 'PRO'        → el podio del acumulado PRO
    · 'NORMAL'     → el podio del acumulado NORMAL
    · 'EQUIPOS'    → el podio de la Copa de Equipos acumulada

Revisión: 20-Oct-2026
"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "a9c2e4f61b73"
down_revision: Union[str, Sequence[str], None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "prize_tiers",
        sa.Column("group_key", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )
    op.create_index(op.f("ix_prize_tiers_group_key"), "prize_tiers", ["group_key"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_prize_tiers_group_key"), table_name="prize_tiers")
    op.drop_column("prize_tiers", "group_key")
