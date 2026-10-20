"""
Rotación de los PIN de juez en la base de datos.

Los PIN **no viven en el repositorio**: se guardan en `stages.judge_pin` y su
valor viene del entorno (`JUDGE_PIN_F1`…`JUDGE_PIN_F4`). Este script los
escribe en la base de datos sin reejecutar el sembrado completo (que volvería
a reprocesar los Excel y los PDF oficiales).

Uso:

    PYTHONPATH=. python -m backend.scripts.rotate_judge_pins            # muestra
    PYTHONPATH=. python -m backend.scripts.rotate_judge_pins --apply    # escribe

Si algún PIN del entorno falta, ese campo queda como está (no se borra).
"""
import argparse
import asyncio
import sys

from sqlmodel import select

from backend.app.core.db import async_session_factory, engine, init_db
from backend.app.core.secrets import JUDGE_PIN_ENV, judge_pin_for
from backend.app.models.entities import Stage


async def rotate(apply: bool = False) -> int:
    await init_db()
    async with async_session_factory() as session:
        stages = (
            await session.exec(select(Stage).order_by(Stage.stage_number))
        ).all()

        cambios = 0
        for stage in stages:
            nuevo = judge_pin_for(stage.stage_number)
            if not nuevo:
                continue
            if stage.judge_pin == nuevo:
                print(f"  Fecha {stage.stage_number}: sin cambios")
                continue
            print(
                f"  Fecha {stage.stage_number}: "
                f"{stage.judge_pin or '(vacio)'} -> {nuevo}"
            )
            cambios += 1
            if apply:
                stage.judge_pin = nuevo
                session.add(stage)

        if apply and cambios:
            await session.commit()
            print(f"\nPIN actualizados en la base de datos: {cambios}")
        elif cambios:
            print(
                f"\n{cambios} PIN cambiarian. Repite con --apply para escribirlos."
            )
        else:
            print("\nNo hay cambios pendientes.")
    return cambios


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Muestra (o aplica) la rotacion de los PIN de juez."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Escribe los PIN del entorno en la base de datos.",
    )
    args = parser.parse_args()

    print("PIN de juez por fecha (desde el entorno):")
    for numero, env_name in JUDGE_PIN_ENV.items():
        print(f"  Fecha {numero} <- {env_name}")

    asyncio.run(rotate(apply=args.apply))
    return 0


if __name__ == "__main__":
    sys.exit(main())
