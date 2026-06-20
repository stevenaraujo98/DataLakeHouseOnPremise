#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# generate-config.sh
# Genera el archivo userlist.txt para PgBouncer con el hash de la contraseña
#
# Uso:
#   chmod +x pgbouncer/generate-config.sh
#   ./pgbouncer/generate-config.sh
#
# Requiere que el .env esté en el directorio padre (junto al docker-compose.yml)
# ─────────────────────────────────────────────────────────────────────────────

set -e

# Cargar variables del .env del directorio padre
ENV_FILE="$(dirname "$0")/../.env"
if [ ! -f "$ENV_FILE" ]; then
  echo "❌ No se encontró el archivo .env en: $ENV_FILE"
  exit 1
fi

source "$ENV_FILE"

if [ -z "$POSTGRES_USER" ] || [ -z "$POSTGRES_PASSWORD" ]; then
  echo "❌ POSTGRES_USER o POSTGRES_PASSWORD no están definidos en .env"
  exit 1
fi

OUTPUT="$(dirname "$0")/userlist.txt"

# PgBouncer con auth_type=scram-sha-256 puede usar la contraseña en texto plano
# en userlist.txt (la enviará hasheada al negociar con Postgres).
# Formato: "usuario" "contraseña"
echo "\"${POSTGRES_USER}\" \"${POSTGRES_PASSWORD}\"" > "$OUTPUT"

echo "✅ Generado: $OUTPUT"
echo "   Usuario: ${POSTGRES_USER}"
echo "   (contraseña ocultada)"