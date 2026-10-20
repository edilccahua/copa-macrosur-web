"""add stage live closed at

Revision ID: f6a7b8c9d0e1
Revises: b3e1a7c9d4f2
Create Date: 2026-10-20

Añade `stages.live_closed_at`: el cierre MANUAL de la transmisión de llegadas.

La apertura es automática a las 08:00 de Lima el día de la carrera
(`live_service.py`, specs/02 §6); el organizador la cierra desde `/admin`
cuando termina de llegar el último ciclista. `NULL` = nunca se cerró.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, Sequence[str], None] = 'b3e1a7c9d4f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('stages') as batch:
        batch.add_column(sa.Column('live_closed_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('stages') as batch:
        batch.drop_column('live_closed_at')
