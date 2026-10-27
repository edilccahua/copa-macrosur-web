#!/usr/bin/env bash
# Script para comprobar el estado de salud y latencia del backend de Kúspide
set -euo pipefail

URL="https://kuspide-api.onrender.com/health"

echo "=================================================="
echo " Consultando API Kúspide: $URL"
echo "=================================================="

# Medir código HTTP y tiempo de respuesta
RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}\nTIME_TOTAL:%{time_total}s\n" "$URL")

BODY=$(echo "$RESPONSE" | sed -e '$d' -e '$d')
HTTP_STATUS=$(echo "$RESPONSE" | grep "HTTP_STATUS" | cut -d':' -f2)
TIME_TOTAL=$(echo "$RESPONSE" | grep "TIME_TOTAL" | cut -d':' -f2)

echo "Respuesta: $BODY"
echo "Código HTTP: $HTTP_STATUS"
echo "Latencia: $TIME_TOTAL"

if [ "$HTTP_STATUS" -eq 200 ]; then
    echo " Backend despierto y saludable."
    exit 0
else
    echo " Error al contactar el backend."
    exit 1
fi
