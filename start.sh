#!/usr/bin/env bash
set -e

echo "=== INICIANDO KÚSPIDE MTB WEB ==="

# 1. Asegurar base de datos inicializada
echo "[1/3] Verificando base de datos y seed..."
PYTHONPATH=. python3 -m backend.app.seed

# 2. Levantar backend en segundo plano
echo "[2/3] Levantando backend FastAPI en http://localhost:8000..."
PYTHONPATH=. python3 -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# 3. Levantar frontend Astro
echo "[3/3] Levantando frontend Astro en http://localhost:4321..."
cd frontend
npm run dev &
FRONTEND_PID=$!

echo "Kúspide MTB activo:"
echo "  - Portal Web: http://localhost:4321"
echo "  - API Backend: http://localhost:8000/docs"
echo "  - Panel Juez PWA: http://localhost:4321/admin/juez"

trap "kill $BACKEND_PID $FRONTEND_PID" EXIT
wait
