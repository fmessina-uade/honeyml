#!/usr/bin/env bash
# honeyml_watchdog.sh: detecta y corrige el cuelgue conocido de Dionaea.
# Ejecutado por cron cada 10 minutos.
#
# El fallo, observado dos veces: bajo carga sostenida Dionaea entra en un bucle que satura un
# núcleo y deja de procesar conexiones. El contenedor NO muere y su puerto sigue aceptando TCP
# (lo hace el proxy de Docker), así que ni la política de reinicio ni una sonda de puerto lo
# detectan. Lo único que lo delata es que el registro deja de crecer.
#
# Por eso la señal es la antigüedad del archivo de registro y no el estado del proceso. Con
# ~30.000 eventos diarios, media hora sin escribir no es un período tranquilo: es un cuelgue.

set -euo pipefail

DIONAEA_LOG="/var/lib/docker/volumes/honeypots_dionaea_var/_data/lib/dionaea/dionaea.json"
COWRIE_LOG="/var/lib/docker/volumes/honeypots_cowrie_logs/_data/cowrie.json"
LOG="/var/log/honeyml_watchdog.log"
# margen amplio: por debajo de esto habría falsos positivos en pausas legítimas del tráfico
STALE_SECONDS=1800

TS=$(date -u '+%Y-%m-%d %H:%M:%S')
log() { echo "[$TS] $*" >> "$LOG"; }

edad_registro() {
    local archivo="$1"
    [[ -f "$archivo" ]] || { echo -1; return; }
    echo $(( $(date +%s) - $(stat -c %Y "$archivo") ))
}

revisar() {
    local nombre="$1" archivo="$2"
    local edad
    edad=$(edad_registro "$archivo")

    if [[ "$edad" -lt 0 ]]; then
        log "AVISO: no existe el registro de ${nombre} (${archivo})"
        return
    fi
    if [[ "$edad" -le "$STALE_SECONDS" ]]; then
        return
    fi

    local pids cpu
    pids=$(docker stats "$nombre" --no-stream --format '{{.PIDs}}' 2>/dev/null || echo '?')
    cpu=$(docker stats "$nombre" --no-stream --format '{{.CPUPerc}}' 2>/dev/null || echo '?')
    log "ALERTA: ${nombre} sin escribir hace ${edad}s (pids=${pids} cpu=${cpu}). Reiniciando."

    if docker restart "$nombre" >/dev/null 2>&1; then
        sleep 20
        local nueva
        nueva=$(edad_registro "$archivo")
        log "OK: ${nombre} reiniciado; antigüedad del registro ahora ${nueva}s"
    else
        log "ERROR: falló el reinicio de ${nombre}"
    fi
}

main() {
    revisar dionaea "$DIONAEA_LOG"
    revisar cowrie "$COWRIE_LOG"
}

main "$@"
