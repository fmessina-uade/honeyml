#!/usr/bin/env bash
# honeyml_backup.sh: respaldo diario de la telemetría de los honeypots.
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

set -euo pipefail

BACKUP_ROOT="/home/honeyml/backups"
COWRIE_SRC="/var/lib/docker/volumes/honeypots_cowrie_logs/_data"
DIONAEA_SRC="/var/lib/docker/volumes/honeypots_dionaea_var/_data/lib/dionaea"
LOG="/var/log/honeyml_backup.log"
# solo aplica a las instantáneas del archivo activo; los rotados se conservan siempre
SNAPSHOT_RETENTION_DAYS=14
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

main() {
    mkdir -p "$BACKUP_ROOT/cowrie" "$BACKUP_ROOT/dionaea"

    local rotados_cowrie
    rotados_cowrie=$(copiar_rotados "$COWRIE_SRC" 'cowrie.json.*' "$BACKUP_ROOT/cowrie")
    instantanea_activo "$COWRIE_SRC/cowrie.json" "$BACKUP_ROOT/cowrie" "cowrie"

    # Dionaea no rota: solo hay archivo activo
    instantanea_activo "$DIONAEA_SRC/dionaea.json" "$BACKUP_ROOT/dionaea" "dionaea"

    # purga solo las instantáneas del activo; los rotados son el archivo histórico
    local purgadas
    purgadas=$(find "$BACKUP_ROOT" -name '*-activo-*.json.gz' \
        -mtime "+$SNAPSHOT_RETENTION_DAYS" -print -delete 2>/dev/null | wc -l)

    chown -R "$OWNER" "$BACKUP_ROOT" 2>/dev/null || true

    local total tamano
    total=$(find "$BACKUP_ROOT" -name '*.gz' | wc -l)
    tamano=$(du -sh "$BACKUP_ROOT" | cut -f1)
    log "OK: ${rotados_cowrie} rotados nuevos, instantáneas del día guardadas, ${purgadas} purgadas. Total: ${total} archivos, ${tamano}."
}

main "$@"
