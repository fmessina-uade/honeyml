#!/usr/bin/env bash
# honeyml_backup.sh: respaldo diario de la telemetría de los honeypots y de las decisiones.
# Ejecutado por cron todos los días a las 03:00 UTC.
#
# Por qué existe: los sensores rotan sus registros y eliminan los antiguos, así que el volumen
# Docker NO es un archivo histórico. Sin este respaldo, la evidencia más vieja que la ventana de
# rotación se pierde de forma irrecuperable.
#
# Estrategia:
#   - Los archivos ya rotados son inmutables: se copian comprimidos UNA sola vez y se conservan.
#     Son el archivo histórico y no se purgan.
#   - El archivo activo cambia todo el tiempo: se guarda una instantánea diaria comprimida, que
#     sí se purga, porque queda cubierta por el rotado del día siguiente.
#   - Las decisiones son la excepción que más importa: los eventos se pueden reingerir desde los
#     registros crudos, pero cada decisión costó una llamada paga y no se puede rehacer gratis. Se
#     vuelca el índice entero, que es chico, y el volcado se restaura con la misma operación masiva
#     con que se lo escribió.
#
# Todo esto queda en el mismo disco que produce los datos, así que es la mitad del respaldo. La otra
# mitad es sacarlo del servidor, y eso lo hace `make respaldar-decisiones` desde la estación.

set -euo pipefail

BACKUP_ROOT="/home/honeyml/backups"
COWRIE_SRC="/var/lib/docker/volumes/honeypots_cowrie_logs/_data"
DIONAEA_SRC="/var/lib/docker/volumes/honeypots_dionaea_var/_data/lib/dionaea"
LOG="/var/log/honeyml_backup.log"
# solo aplica a las instantáneas del archivo activo; los rotados se conservan siempre
SNAPSHOT_RETENTION_DAYS=14
# cada volcado de decisiones es el índice entero, así que unos pocos alcanzan para volver atrás
DECISIONES_RETENTION_DAYS=14
ES_URL="http://localhost:9200"
INDICE_DECISIONES="honeyml-decisiones"
OWNER="honeyml:honeyml"

TODAY=$(date -u '+%Y-%m-%d')
TS=$(date -u '+%Y-%m-%d %H:%M:%S')

log() { echo "[$TS] $*" >> "$LOG"; }

copiar_rotados() {
    local src_dir="$1" patron="$2" dest_dir="$3" nuevos=0
    shopt -s nullglob
    for archivo in "$src_dir"/$patron; do
        local base dest
        base=$(basename "$archivo")
        dest="$dest_dir/${base}.gz"
        # inmutable: si ya está respaldado, no se vuelve a copiar
        [[ -f "$dest" ]] && continue
        gzip -c "$archivo" > "$dest.tmp" && mv "$dest.tmp" "$dest"
        nuevos=$((nuevos + 1))
    done
    shopt -u nullglob
    echo "$nuevos"
}

instantanea_activo() {
    local origen="$1" dest_dir="$2" etiqueta="$3"
    [[ -f "$origen" ]] || { log "AVISO: no existe $origen, se omite $etiqueta"; return 0; }
    local dest="$dest_dir/${etiqueta}-activo-${TODAY}.json.gz"
    gzip -c "$origen" > "$dest.tmp" && mv "$dest.tmp" "$dest"
}

instantanea_decisiones() {
    local dest_dir="$1" volcadas=0
    # El índice solo existe donde corre la zona de análisis. En un anfitrión que solo tiene los
    # sensores no hay nada que volcar, y eso no es una falla.
    if ! curl -sf --max-time 10 "$ES_URL/$INDICE_DECISIONES/_count" >/dev/null 2>&1; then
        log "AVISO: no responde $INDICE_DECISIONES, se omiten las decisiones"
        echo 0
        return 0
    fi
    local dest="$dest_dir/decisiones-${TODAY}.ndjson.gz"
    # Se guarda el identificador junto al documento: es el `doc_id` del evento, y sin él una
    # restauración perdería la correspondencia entre la decisión y el evento que la originó.
    if volcadas=$(python3 - "$ES_URL" "$INDICE_DECISIONES" "$dest.tmp" <<'PY'
import gzip
import json
import sys
import urllib.request

es, indice, destino = sys.argv[1], sys.argv[2], sys.argv[3]


def pedir(ruta, cuerpo):
    pedido = urllib.request.Request(
        es + ruta, data=json.dumps(cuerpo).encode(), method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(pedido, timeout=120) as r:
        return json.load(r)


total = 0
with gzip.open(destino, "wt", encoding="utf-8") as f:
    r = pedir(f"/{indice}/_search?scroll=5m", {"size": 2000, "sort": ["_doc"]})
    while r["hits"]["hits"]:
        for h in r["hits"]["hits"]:
            f.write(json.dumps({"_id": h["_id"], "_source": h["_source"]}, ensure_ascii=False) + "\n")
            total += 1
        r = pedir("/_search/scroll", {"scroll": "5m", "scroll_id": r["_scroll_id"]})
print(total)
PY
    ); then
        mv "$dest.tmp" "$dest"
    else
        rm -f "$dest.tmp"
        log "ERROR: falló el volcado de decisiones"
        volcadas=0
    fi
    echo "$volcadas"
}

main() {
    mkdir -p "$BACKUP_ROOT/cowrie" "$BACKUP_ROOT/dionaea" "$BACKUP_ROOT/decisiones"

    local rotados_cowrie
    rotados_cowrie=$(copiar_rotados "$COWRIE_SRC" 'cowrie.json.*' "$BACKUP_ROOT/cowrie")
    instantanea_activo "$COWRIE_SRC/cowrie.json" "$BACKUP_ROOT/cowrie" "cowrie"

    # Dionaea no rota: solo hay archivo activo
    instantanea_activo "$DIONAEA_SRC/dionaea.json" "$BACKUP_ROOT/dionaea" "dionaea"

    local decisiones
    decisiones=$(instantanea_decisiones "$BACKUP_ROOT/decisiones")

    # purga las instantáneas del activo y los volcados viejos de decisiones; los rotados de los
    # sensores son el archivo histórico y no se tocan
    local purgadas
    purgadas=$(find "$BACKUP_ROOT" -name '*-activo-*.json.gz' \
        -mtime "+$SNAPSHOT_RETENTION_DAYS" -print -delete 2>/dev/null | wc -l)
    purgadas=$((purgadas + $(find "$BACKUP_ROOT/decisiones" -name 'decisiones-*.ndjson.gz' \
        -mtime "+$DECISIONES_RETENTION_DAYS" -print -delete 2>/dev/null | wc -l)))

    chown -R "$OWNER" "$BACKUP_ROOT" 2>/dev/null || true

    local total tamano
    total=$(find "$BACKUP_ROOT" -name '*.gz' | wc -l)
    tamano=$(du -sh "$BACKUP_ROOT" | cut -f1)
    log "OK: ${rotados_cowrie} rotados nuevos, instantáneas del día guardadas, ${decisiones} decisiones, ${purgadas} purgadas. Total: ${total} archivos, ${tamano}."
}

main "$@"
