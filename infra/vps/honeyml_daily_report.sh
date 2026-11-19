#!/usr/bin/env bash
# honeyml_daily_report.sh: el resumen del día. Lo corre cron a las 10 de Argentina y lo manda al
# canal de avisos.
#
# Además de resumir, hace de latido. Las alertas salen solo cuando algo falla, así que un canal
# callado no distingue un servidor sano de uno caído, o de un chequeo que dejó de correr. Este
# mensaje llega todos los días, y el día que no aparece hay que entrar a mirar.
#
# Los conteos salen del índice y no de los registros crudos de los sensores: así cubren las últimas
# 24 horas justas y de paso confirman que la ingesta sigue andando. Al canal van solo números,
# ninguna dirección.

set -euo pipefail

ES_URL="http://localhost:9200"
LOG="/var/log/honeyml_health.log"
WATCHDOG_LOG="/var/log/honeyml_watchdog.log"
BACKUP_LOG="/var/log/honeyml_backup.log"
AVISO="/usr/local/bin/honeyml_aviso.sh"
# los mismos que revisa el chequeo de salud; el que no existe en este servidor no se cuenta
CONTENEDORES=(cowrie dionaea elasticsearch logstash filebeat valkey motor api)
ULTIMO_DIA='{"range":{"@timestamp":{"gte":"now-24h"}}}'

TS=$(date -u '+%Y-%m-%d %H:%M:%S')
HACE_UN_DIA=$(date -u -d '24 hours ago' '+%Y-%m-%d %H:%M:%S')

# Va directo al registro del chequeo de salud, con el mismo formato, porque el panel lo muestra en la
# vista de auditoría. Esa vista marca como alerta toda línea que contenga alert, error, aviso, fallo,
# cuelgue o reinici, en mayúsculas o minúsculas. Por eso la línea de un reporte sano no usa esas
# palabras, y la de uno con problemas empieza con AVISO.
log() { echo "[$TS] $*" >> "$LOG"; }

# El número que sigue a la clave en la respuesta del índice, o nada si el índice no contesta. Una
# respuesta con fragmentos fallidos también se descarta: Elasticsearch la devuelve con código 200 y
# el conteo de los fragmentos que sí contestaron, que pasaría por un total.
consultar() {
    local ruta="$1" cuerpo="$2" clave="$3" respuesta
    respuesta=$(curl -s --max-time 30 -X POST -H 'Content-Type: application/json' \
        "${ES_URL}/${ruta}" -d "$cuerpo" 2>/dev/null) || return 0
    [[ "$respuesta" == *'"failed":0'* ]] || return 0
    grep -o "${clave}[0-9]*" <<< "$respuesta" | head -1 | grep -o '[0-9]*$' || true
}

# separador de miles con punto, como se escriben los números en castellano
miles() {
    local n="$1" resto=""
    [[ "$n" =~ ^[0-9]+$ ]] || { echo "$n"; return; }
    while (( ${#n} > 3 )); do
        resto=".${n: -3}${resto}"
        n=${n:0:${#n}-3}
    done
    echo "${n}${resto}"
}

# las líneas de un registro escritas en las últimas 24 horas, que empiezan con la hora UTC entre
# corchetes y por eso se comparan como texto
del_ultimo_dia() {
    [[ -f "$1" ]] || return 0
    awk -v desde="$HACE_UN_DIA" 'substr($0, 2, 19) >= desde' "$1"
}

# Las líneas del vigilante de las últimas 24 horas que coinciden con el filtro, contadas por sensor.
# Devuelve "total|Dionaea 2, Cowrie 1": el nombre es la palabra que sigue al prefijo.
contar_vigilante() {
    del_ultimo_dia "$WATCHDOG_LOG" | awk -v filtro="$1" -v prefijo="$2" '
        $0 ~ filtro {
            n = substr($0, index($0, prefijo) + length(prefijo)); sub(/[^a-z].*/, "", n)
            c[n]++; total++
        }
        END {
            s = ""
            for (k in c) s = s (s == "" ? "" : ", ") toupper(substr(k, 1, 1)) substr(k, 2) " " c[k]
            print total + 0 "|" s
        }'
}

texto_vigilante() {
    local l_total=${1%%|*} l_detalle=${1#*|} f_total=${2%%|*} f_detalle=${2#*|} partes=()
    case "$l_total" in
        0) ;;
        1) partes+=("un reinicio automático (${l_detalle% 1})") ;;
        *) partes+=("${l_total} reinicios automáticos (${l_detalle})") ;;
    esac
    case "$f_total" in
        0) ;;
        1) partes+=("un reinicio fallido (${f_detalle% 1})") ;;
        *) partes+=("${f_total} reinicios fallidos (${f_detalle})") ;;
    esac
    case "${#partes[@]}" in
        0) echo "sensores estables, sin reinicios automáticos" ;;
        1) echo "${partes[0]}" ;;
        *) echo "${partes[0]} y ${partes[1]}" ;;
    esac
}

main() {
    local problemas=()

    local cowrie dionaea direcciones decisiones sensores motor
    cowrie=$(consultar "honeypot-cowrie-*/_count?ignore_unavailable=true" \
        "{\"query\":${ULTIMO_DIA}}" '"count":')
    dionaea=$(consultar "honeypot-dionaea-*/_count?ignore_unavailable=true" \
        "{\"query\":${ULTIMO_DIA}}" '"count":')
    direcciones=$(consultar "honeypot-cowrie-*,honeypot-dionaea-*/_search?ignore_unavailable=true" \
        "{\"size\":0,\"track_total_hits\":false,\"query\":${ULTIMO_DIA},\"aggs\":{\"direcciones\":{\"cardinality\":{\"field\":\"source.ip\"}}}}" \
        '"direcciones":{"value":')
    decisiones=$(consultar "honeyml-decisiones/_count?ignore_unavailable=true&allow_no_indices=true" \
        "{\"query\":${ULTIMO_DIA}}" '"count":')

    if [[ -n "$cowrie" && -n "$dionaea" ]]; then
        sensores="Cowrie $(miles "$cowrie") eventos y Dionaea $(miles "$dionaea"), desde $(miles "${direcciones:-?}") direcciones distintas"
        if (( cowrie + dionaea == 0 )); then
            sensores+=". Ningún evento: revisar la ingesta"
            problemas+=("ningún evento de los sensores")
        fi
    else
        sensores="el índice no contestó"
        problemas+=("el índice no contestó")
    fi
    if [[ -n "$decisiones" ]]; then
        motor="$(miles "$decisiones") decisiones"
    else
        motor="el índice no contestó"
    fi

    # Con el demonio de Docker parado, cada consulta falla igual que la de un contenedor que no
    # existe, y el conteo saldría "0 de 0" como si nada.
    local contenedores nombre estado en_marcha=0 existentes=0 frenados=()
    if docker info >/dev/null 2>&1; then
        for nombre in "${CONTENEDORES[@]}"; do
            estado=$(docker inspect --format='{{.State.Status}}' "$nombre" 2>/dev/null || true)
            [[ -n "$estado" ]] || continue
            existentes=$((existentes + 1))
            if [[ "$estado" == "running" ]]; then
                en_marcha=$((en_marcha + 1))
            else
                frenados+=("$nombre")
            fi
        done
        contenedores="${en_marcha} de ${existentes} en marcha"
        if (( ${#frenados[@]} > 0 )); then
            contenedores+=", sin correr: ${frenados[*]}"
            problemas+=("sin correr: ${frenados[*]}")
        fi
    else
        contenedores="Docker no contesta"
        problemas+=("Docker no contesta")
    fi

    # El vigilante escribe "Reiniciando" antes de intentarlo, así que se cuentan los resultados: el
    # reinicio logrado y el fallido, cada uno por sensor, porque decir cuál se colgó sirve más que
    # el total.
    local vigilante logrados fallidos
    logrados=$(contar_vigilante 'OK: [a-z]+ reiniciado' 'OK: ')
    fallidos=$(contar_vigilante 'falló el reinicio de [a-z]+' 'falló el reinicio de ')
    vigilante=$(texto_vigilante "$logrados" "$fallidos")
    if [[ "${fallidos%%|*}" != "0" ]]; then
        problemas+=("el vigilante no pudo reiniciar un sensor")
    fi

    # El respaldo corre una vez por día, así que en las últimas 24 horas tiene que haber dejado su
    # línea final. Si Elasticsearch no le contestó, igual la deja, pero sin ninguna decisión volcada.
    local respaldo lineas_respaldo fallas
    lineas_respaldo=$(del_ultimo_dia "$BACKUP_LOG")
    fallas=$(grep -c 'ERROR' <<< "$lineas_respaldo" || true)
    if ! grep -q 'OK:' <<< "$lineas_respaldo"; then
        respaldo="no terminó"
        problemas+=("el respaldo no terminó")
    elif (( fallas == 1 )); then
        respaldo="terminó, con un volcado fallido"
        problemas+=("el respaldo tuvo un volcado fallido")
    elif (( fallas > 1 )); then
        respaldo="terminó, con ${fallas} volcados fallidos"
        problemas+=("el respaldo tuvo volcados fallidos")
    elif grep -q 'no se volcó ninguna decisión' <<< "$lineas_respaldo"; then
        respaldo="terminó, pero sin ninguna decisión volcada"
        problemas+=("el respaldo no volcó decisiones")
    else
        respaldo="completo"
    fi

    # Un reinicio del servidor en las últimas 24 horas es un hecho a contar; si no hubo, alcanza con
    # decir desde cuándo está en marcha.
    local segundos memoria disco_uso="" disco_libre="" servidor
    segundos=$(awk '{print int($1)}' /proc/uptime 2>/dev/null || true)
    memoria=$(free 2>/dev/null | awk '/^Mem:/ {printf "%d", $3 * 100 / $2}' || true)
    read -r disco_uso disco_libre < <(df -hP / | awk 'NR == 2 {print $5, $4}') || true
    if [[ -z "$segundos" ]]; then
        servidor=""
    elif (( segundos < 3600 )); then
        servidor="reiniciado hace menos de una hora, "
    elif (( segundos < 7200 )); then
        servidor="reiniciado hace una hora, "
    elif (( segundos < 86400 )); then
        servidor="reiniciado hace $((segundos / 3600)) horas, "
    elif (( segundos < 172800 )); then
        servidor="en marcha hace un día, "
    else
        servidor="en marcha hace $((segundos / 86400)) días, "
    fi
    servidor+="memoria al ${memoria:-?}%, disco al ${disco_uso:-?} (${disco_libre:-?} libres)"

    local anfitrion color estado_resumen
    anfitrion=$(hostname -f 2>/dev/null || hostname)
    local items=()
    if (( ${#problemas[@]} > 0 )); then
        local juntos
        juntos=$(printf '%s; ' "${problemas[@]}")
        juntos=${juntos%; }
        # ámbar: es el nivel medio de la escala del panel, el de lo que hay que mirar
        color="#D4860A"
        estado_resumen="Para revisar: ${juntos}"
        items+=("Para revisar" "$juntos")
    else
        # teal: en la paleta es el color del funcionamiento correcto
        color="#00B894"
        estado_resumen="Todo en orden"
    fi
    items+=("Sensores (últimas 24 hs)" "$sensores"
        "Motor (últimas 24 hs)" "$motor"
        "Contenedores" "$contenedores"
        "Vigilante (últimas 24 hs)" "$vigilante"
        "Respaldo de la madrugada" "$respaldo"
        "Servidor" "$servidor")

    # a mano, desde una terminal, el reporte también se ve en pantalla
    if [[ -t 1 ]]; then
        printf 'Reporte diario %s\n' "$anfitrion"
        printf '%s: %s\n' "${items[@]}"
    fi

    local argumentos=(--titulo "Reporte diario ${anfitrion}" --color "$color" --resumen "$estado_resumen") i
    for (( i = 0; i < ${#items[@]}; i += 2 )); do
        argumentos+=(--item "${items[i]}" "${items[i + 1]}")
    done
    local salida=0 respuesta=""
    if [[ -x "$AVISO" ]]; then
        respuesta=$("$AVISO" "${argumentos[@]}") || salida=$?
    else
        salida=1
    fi
    local resumen="Cowrie ${cowrie:-?}, Dionaea ${dionaea:-?}, ${decisiones:-?} decisiones, ${en_marcha} de ${existentes} contenedores en marcha"
    case "$salida" in
        0) log "Reporte diario enviado al canal. ${resumen}" ;;
        1) log "Reporte diario sin webhook configurado, queda solo en este registro. ${resumen}" ;;
        *) log "AVISO: el reporte diario no llegó al canal (${respuesta}). ${resumen}" ;;
    esac
    if (( ${#problemas[@]} > 0 )); then
        log "AVISO: el reporte diario encontró problemas: ${juntos}"
    fi
}

main "$@"
