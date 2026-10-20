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
PYTHONPATH=. python3 -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

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
