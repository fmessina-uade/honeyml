#!/usr/bin/env bash
# Arranque de Elasticsearch: aplica la plantilla ECS componible de HoneyML.
# Es idempotente, así que se puede correr todas las veces que haga falta.
set -euo pipefail

ES_URL="${ES_URL:-http://localhost:9200}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE_FILE="${SCRIPT_DIR}/../templates/honeypot-ecs-template.json"
TEMPLATE_DECISIONES="${SCRIPT_DIR}/../templates/honeyml-decisiones-template.json"

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

echo "==> Aplicando plantilla componible honeyml-decisiones ..."
curl -sf -X PUT "${ES_URL}/_index_template/honeyml-decisiones" \
  -H 'Content-Type: application/json' \
  --data-binary "@${TEMPLATE_DECISIONES}" >/dev/null

echo "==> Plantilla aplicada. Verificación:"
curl -sf "${ES_URL}/_index_template/honeyml-decisiones" \
  | python3 -c "import sys,json; t=json.load(sys.stdin)['index_templates'][0]; print('    nombre:', t['name']); print('    patrones:', t['index_template']['index_patterns']); print('    dinamico:', t['index_template']['template']['mappings']['dynamic'])"

# Una plantilla solo alcanza a los índices que se crean después, así que sobre uno que ya existe no
# hace nada. Con `dynamic: strict` eso no se nota hasta que el motor manda un campo nuevo y
# Elasticsearch rechaza el documento, con el evento ya sacado del bus. Agregar campos a un mapeo
# vivo sí está permitido; cambiar el tipo de uno existente no, y ahí conviene que falle fuerte.
if curl -sf -o /dev/null "${ES_URL}/honeyml-decisiones"; then
  echo "==> El índice honeyml-decisiones ya existe: sincronizando su mapeo ..."
  python3 -c "import sys,json; print(json.dumps({'properties': json.load(open(sys.argv[1]))['template']['mappings']['properties']}))" \
    "${TEMPLATE_DECISIONES}" \
    | curl -sf -X PUT "${ES_URL}/honeyml-decisiones/_mapping" \
        -H 'Content-Type: application/json' --data-binary @- >/dev/null \
    || { echo "ERROR: el mapeo del índice vivo no admite la plantilla actual." >&2; exit 1; }
  echo "    mapeo al día."
fi

echo "==> Bootstrap completo."
