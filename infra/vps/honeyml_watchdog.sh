#!/usr/bin/env bash
# honeyml_watchdog.sh: detecta el cuelgue de un sensor, guarda con qué estaba ocupado y lo reinicia.
# Lo corre cron cada 5 minutos.
#
# En el cuelgue el contenedor sigue vivo y su puerto sigue aceptando TCP (lo hace el proxy de
# Docker), así que ni la política de reinicio ni una sonda de puerto lo ven. Lo que lo delata es que
# el registro deja de crecer.
#
# Hay dos umbrales. Con la CPU clavada, diez minutos sin escribir ya son un cuelgue: el proceso
# trabaja al máximo y no produce nada. Con la CPU tranquila se espera media hora, porque puede ser
# una pausa del tráfico. Clavada se mide contra el tope del contenedor y no contra un núcleo entero:
# Cowrie tiene medio núcleo, así que trabado marca 50 % y nunca llegaría al 90 %. La cuenta arranca,
# como mucho, cuando arrancó el contenedor: un reinicio reciente no hereda la antigüedad del
# registro y no se encadenan reinicios.
#
# Antes de reiniciar se guarda la pila del proceso y el uso de CPU por hilo, porque el reinicio borra
# esa evidencia y sin ella no hay forma de saber dónde quedó trabado. La pila la lee py-spy desde un
# contenedor que comparte el espacio de procesos del sensor, así no se instala nada en el anfitrión.
#
# Para comprobar que la captura funciona sin reiniciar nada:
#     honeyml_watchdog.sh --diagnosticar dionaea

set -euo pipefail

DIONAEA_LOG="/var/lib/docker/volumes/honeypots_dionaea_var/_data/lib/dionaea/dionaea.json"
COWRIE_LOG="/var/lib/docker/volumes/honeypots_cowrie_logs/_data/cowrie.json"
LOG="/var/log/honeyml_watchdog.log"
DIAGNOSTICOS="/var/log/honeyml_diagnosticos"
IMAGEN_PYSPY="honeyml-pyspy"
AVISO="/usr/local/bin/honeyml_aviso.sh"

# segundos sin escribir que alcanzan cuando la CPU supera LIMITE_CPU (en porcentaje del tope del
# contenedor)
UMBRAL_CON_CPU=600
LIMITE_CPU=90
# segundos sin escribir que alcanzan con cualquier CPU
UMBRAL_SIN_CPU=1800

TS=$(date -u '+%Y-%m-%d %H:%M:%S')
log() { echo "[$TS] $*" >> "$LOG"; }

# El aviso al canal es un agregado: si no hay webhook o el envío falla, el reinicio igual queda en
# el registro, y eso no puede frenar al vigilante. Las opciones del envío, como --una-por-hora, van
# antes de las líneas del mensaje.
avisar() {
    local opciones=()
    if [[ "${1:-}" == "--una-por-hora" ]]; then
        opciones=("$1" "$2")
        shift 2
    fi
    if [[ -x "$AVISO" ]]; then
        "$AVISO" "${opciones[@]}" "HoneyML [aviso] en $(hostname -f), $TS UTC" "$@" >/dev/null 2>&1 || true
    fi
}

edad_registro() {
    local archivo="$1"
    [[ -f "$archivo" ]] || { echo -1; return; }
    echo $(( $(date +%s) - $(stat -c %Y "$archivo") ))
}

desde_arranque() {
    local inicio
    inicio=$(docker inspect -f '{{.State.StartedAt}}' "$1" 2>/dev/null) || { echo -1; return; }
    echo $(( $(date +%s) - $(date -d "$inicio" +%s) ))
}

cpu_de() {
    # la parte entera del porcentaje, o vacío si Docker no contesta
    docker stats "$1" --no-stream --format '{{.CPUPerc}}' 2>/dev/null | tr -d '%' | cut -d. -f1 || true
}

tope_cpu_de() {
    # lo que marca docker stats con el contenedor al máximo: 100 por núcleo asignado, y 100 si no
    # tiene tope, que es lo que ocupa un proceso de un solo hilo trabado
    local nano
    nano=$(docker inspect -f '{{.HostConfig.NanoCpus}}' "$1" 2>/dev/null || echo 0)
    if [[ "${nano:-0}" -gt 0 ]]; then
        echo $(( nano / 10000000 ))
    else
        echo 100
    fi
}

diagnosticar() {
    local nombre="$1" destino pid
    mkdir -p "$DIAGNOSTICOS"
    destino="${DIAGNOSTICOS}/${nombre}-$(date -u '+%Y%m%dT%H%M%SZ').txt"
    pid=$(docker inspect -f '{{.State.Pid}}' "$nombre" 2>/dev/null || true)
    (
        # un paso que falle no puede dejar la captura a medias ni frenar el reinicio
        set +e
        echo "[contenedor]"
        docker stats "$nombre" --no-stream
        if [[ -n "$pid" && "$pid" != "0" ]]; then
            echo "[cpu por hilo]"
            top -H -b -n 1 -p "$pid" | head -40
            echo "[hilo, estado, espera y nombre]"
            for tarea in /proc/"$pid"/task/*; do
                echo "$(basename "$tarea") $(cut -d' ' -f3 "$tarea/stat") $(cat "$tarea/wchan") $(cat "$tarea/comm")"
            done
            echo "[conexiones]"
            nsenter -t "$pid" -n ss -tanp | head -60
        fi
        # dos lecturas separadas: si la pila se repite, el proceso está girando en ese lugar
        for vuelta in 1 2; do
            echo "[pila, lectura ${vuelta}]"
            # sin --native: con el intérprete embebido en el binario del sensor, esa opción falla
            # al resolver el hilo del sistema y no devuelve ninguna pila
            timeout 60 docker run --rm --network none --pid="container:${nombre}" \
                --cap-add SYS_PTRACE "$IMAGEN_PYSPY" dump --pid 1
            if [[ "$vuelta" -eq 1 ]]; then
                sleep 5
            fi
        done
    ) > "$destino" 2>&1
    # un mes de capturas alcanza para comparar varios cuelgues entre sí
    find "$DIAGNOSTICOS" -name '*.txt' -mtime +30 -delete 2>/dev/null || true
    log "DIAGNOSTICO: ${nombre} en ${destino}"
}

revisar() {
    local nombre="$1" archivo="$2"
    local edad arranque cpu clavada pids
    # Un sensor bajado a propósito, por ejemplo para reconstruir su imagen, no existe como
    # contenedor: su registro envejece y reiniciarlo fallaría en cada corrida.
    if ! docker inspect "$nombre" >/dev/null 2>&1; then
        return
    fi
    edad=$(edad_registro "$archivo")
    if [[ "$edad" -lt 0 ]]; then
        log "AVISO: no existe el registro de ${nombre} (${archivo})"
        return
    fi
    arranque=$(desde_arranque "$nombre")
    if [[ "$arranque" -ge 0 && "$arranque" -lt "$edad" ]]; then
        edad=$arranque
    fi
    if [[ "$edad" -le "$UMBRAL_CON_CPU" ]]; then
        return
    fi

    cpu=$(cpu_de "$nombre")
    clavada=$(( $(tope_cpu_de "$nombre") * LIMITE_CPU / 100 ))
    if [[ "$edad" -le "$UMBRAL_SIN_CPU" && "${cpu:-0}" -lt "$clavada" ]]; then
        return
    fi

    pids=$(docker stats "$nombre" --no-stream --format '{{.PIDs}}' 2>/dev/null || echo '?')
    log "ALERTA: ${nombre} sin escribir hace ${edad}s (pids=${pids} cpu=${cpu:-?}%). Reiniciando."
    diagnosticar "$nombre"

    if docker restart "$nombre" >/dev/null 2>&1; then
        sleep 20
        log "OK: ${nombre} reiniciado; antigüedad del registro ahora $(edad_registro "$archivo")s"
        avisar "El vigilante reinició ${nombre}: llevaba ${edad} s sin escribir. La pila quedó en ${DIAGNOSTICOS}."
    else
        log "ERROR: falló el reinicio de ${nombre}"
        avisar --una-por-hora "vigilante ${nombre} sin reiniciar" \
            "${nombre} está colgado y el vigilante no pudo reiniciarlo: hay que entrar a mirar."
    fi
}

main() {
    if [[ "${1:-}" == "--diagnosticar" ]]; then
        diagnosticar "${2:-dionaea}"
        return
    fi
    revisar dionaea "$DIONAEA_LOG"
    revisar cowrie "$COWRIE_LOG"
}

main "$@"
