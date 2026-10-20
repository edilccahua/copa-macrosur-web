#!/usr/bin/env bash
set -e

# Modo: dev (por defecto) | prod
#   dev  -> astro dev (SSR en modo desarrollo)
#   prod -> astro build + node dist/server/entry.mjs (adaptador Node)
MODE="${1:-dev}"

echo "=== INICIANDO KÚSPIDE MTB WEB (modo: $MODE) ==="

# 1. Asegurar base de datos inicializada
echo "[1/3] Verificando base de datos y seed..."
PYTHONPATH=. python3 -m backend.app.seed

# 2. Levantar backend FastAPI en segundo plano
echo "[2/3] Levantando backend FastAPI en http://localhost:8000..."
if [ "$MODE" = "prod" ]; then
  PYTHONPATH=. python3 -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 &
else
  # En desarrollo, --reload: sin él, un cambio en los modelos no llega al
  # servidor y el frontend lee campos inexistentes (specs/03 §0.2).
  PYTHONPATH=. python3 -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload &
fi
BACKEND_PID=$!

# 2b. Esperar a que el API responda antes de levantar el frontend: si el
# backend no está listo, el SSR devuelve 503 en todas las páginas de datos.
echo "     Esperando al backend..."
for i in $(seq 1 30); do
  if curl -sf http://localhost:8000/api/v1/stages > /dev/null 2>&1; then
    echo "     Backend listo."
    break
  fi
  if [ "$i" = "30" ]; then
    echo "     ERROR: el backend no respondió en 30 s. Revisa el log de uvicorn." >&2
    exit 1
  fi
  sleep 1
done

# 3. Levantar frontend Astro
cd frontend
if [ "$MODE" = "prod" ]; then
  echo "[3/3] Construyendo y levantando el servidor SSR de Astro en http://localhost:4321..."
  npm run build
  PORT=4321 HOST=0.0.0.0 node dist/server/entry.mjs &
else
  echo "[3/3] Levantando frontend Astro (dev) en http://localhost:4321..."
  npm run dev &
fi
FRONTEND_PID=$!

echo "Kúspide MTB activo:"
echo "  - Portal Web: http://localhost:4321"
echo "  - API Backend: http://localhost:8000/docs"
echo "  - Panel Juez PWA: http://localhost:4321/admin/juez"

trap "kill $BACKEND_PID $FRONTEND_PID" EXIT
wait
