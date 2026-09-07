#!/usr/bin/env bash
# Arranque de Elasticsearch: aplica la plantilla ECS componible de HoneyML.
# Es idempotente, así que se puede correr todas las veces que haga falta.
set -euo pipefail

ES_URL="${ES_URL:-http://localhost:9200}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE_FILE="${SCRIPT_DIR}/../templates/honeypot-ecs-template.json"

echo "==> Esperando a Elasticsearch en ${ES_URL} ..."
for i in $(seq 1 30); do
  if curl -sf "${ES_URL}/_cluster/health" >/dev/null 2>&1; then
    break
  fi
  sleep 3
  if [ "$i" -eq 30 ]; then
    echo "ERROR: Elasticsearch no respondió a tiempo." >&2
    exit 1
  fi
done

echo "==> Aplicando plantilla componible honeypot-ecs ..."
curl -sf -X PUT "${ES_URL}/_index_template/honeypot-ecs" \
  -H 'Content-Type: application/json' \
  --data-binary "@${TEMPLATE_FILE}" >/dev/null

echo "==> Plantilla aplicada. Verificación:"
curl -sf "${ES_URL}/_index_template/honeypot-ecs" \
  | python3 -c "import sys,json; t=json.load(sys.stdin)['index_templates'][0]; print('    nombre:', t['name']); print('    patrones:', t['index_template']['index_patterns']); print('    prioridad:', t['index_template']['priority'])"

echo "==> Bootstrap completo."
