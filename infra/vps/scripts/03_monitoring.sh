#!/bin/bash
# 03_monitoring.sh
# Monitoreo básico de salud del VPS. Instala el chequeo periódico con alertas por webhook (Slack,
# o Discord con /slack al final de la dirección), el reporte diario, el watchdog de los sensores, el
# respaldo y la purga de muestras, y los deja programados en cron. Sin webhook, las alertas quedan
# solo en el registro.
#
#     sudo bash 03_monitoring.sh              instala y conserva el webhook que ya estuviera
#     sudo bash 03_monitoring.sh --webhook    además pide la dirección del webhook y la guarda
#
# La dirección se pide sin mostrarla y no se acepta como argumento, para que no quede en el
# historial del shell ni en la lista de procesos. Se guarda en un archivo que solo root lee; para
# dejar de mandar avisos alcanza con borrarlo.

set -euo pipefail

LOG_FILE="/var/log/honeyml_setup.log"
WEBHOOK_DIR="/etc/honeyml"
WEBHOOK_FILE="$WEBHOOK_DIR/webhook"
AVISO_SCRIPT="/usr/local/bin/honeyml_aviso.sh"
DAILY_REPORT_SCRIPT="/usr/local/bin/honeyml_daily_report.sh"
HEALTHCHECK_SCRIPT="/usr/local/bin/honeyml_health.sh"
HEALTHCHECK_LOG="/var/log/honeyml_health.log"
THRESHOLD_CPU=85
THRESHOLD_MEM=90
THRESHOLD_DISK=80
# Eventos de atraso a partir de los cuales el motor dejó de consumir. En régimen el atraso vuelve a
# cero en minutos; este número solo se alcanza con el motor detenido durante horas.
THRESHOLD_ATRASO=5000
# los guiones del anfitrión y la imagen de diagnóstico viven en el repositorio, un nivel arriba
REPO_VPS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WATCHDOG_SCRIPT="/usr/local/bin/honeyml_watchdog.sh"
WATCHDOG_LOG="/var/log/honeyml_watchdog.log"
BACKUP_SCRIPT="/usr/local/bin/honeyml_backup.sh"
BACKUP_LOG="/var/log/honeyml_backup.log"
PURGA_SCRIPT="/usr/local/bin/honeyml_purga_muestras.sh"
PURGA_LOG="/var/log/honeyml_purga.log"
# Los flujos que graba Dionaea son evidencia, pero crecen sin techo y comparten disco con el índice.
BISTREAMS="/var/lib/docker/volumes/honeypots_dionaea_var/_data/lib/dionaea/bistreams"
RETENCION_BISTREAMS_DIAS=30

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

[[ $EUID -eq 0 ]] || { echo "Ejecutar como root." >&2; exit 1; }

# Todo lo que se instala desde el repositorio se busca antes de tocar nada. Si falta un archivo (un
# commit que no lo incluyó, un despliegue a medias), el instalador cortaría en el medio con el
# chequeo de salud ya reescrito y el cron viejo, y ninguna alerta saldría del servidor.
for origen in honeyml_aviso.sh honeyml_daily_report.sh honeyml_watchdog.sh honeyml_backup.sh \
    honeyml_purga_muestras.sh pyspy/Dockerfile; do
    if [[ ! -f "$REPO_VPS/$origen" ]]; then
        echo "Falta $REPO_VPS/$origen: el despliegue está incompleto y no se tocó nada." >&2
        exit 1
    fi
done

case "${1:-}" in
    "") ;;
    --webhook)
        if ! read -rsp "Dirección del webhook (no se muestra al pegarla): " url < /dev/tty; then
            echo "Hace falta una terminal para pedir la dirección: conectarse con ssh -t." >&2
            exit 1
        fi
        echo
        # Se rechaza lo que no sea una dirección https limpia. Una comilla o un espacio colados al
        # copiar rompen cada envío, y conviene frenarlo acá, con la persona adelante, y no
        # enterarse después por el registro.
        patron='^https://[A-Za-z0-9._~:/?#@!$&+,;=%-]+$'
        if [[ ! "$url" =~ $patron ]]; then
            echo "Eso no parece la dirección de un webhook: tiene que empezar con https:// y no llevar espacios ni comillas." >&2
            exit 1
        fi
        install -d -m 700 -o root -g root "$WEBHOOK_DIR"
        (umask 077 && printf '%s\n' "$url" > "$WEBHOOK_FILE.tmp")
        mv "$WEBHOOK_FILE.tmp" "$WEBHOOK_FILE"
        unset url
        ;;
    *)
        echo "Opción desconocida: $1. Sin opciones conserva el webhook; con --webhook lo pide." >&2
        exit 1
        ;;
esac

log "HoneyML: monitoreo de salud"

log "[1/4] Creando el chequeo de salud en $HEALTHCHECK_SCRIPT..."
cat > "$HEALTHCHECK_SCRIPT" << HEALTH_SCRIPT
#!/usr/bin/env bash
# honeyml_health.sh: chequeo periódico de métricas del VPS, lo corre cron cada 5 minutos.

set -euo pipefail

LOG="${HEALTHCHECK_LOG}"
AVISO="${AVISO_SCRIPT}"
THRESHOLD_CPU=${THRESHOLD_CPU}
THRESHOLD_MEM=${THRESHOLD_MEM}
THRESHOLD_DISK=${THRESHOLD_DISK}
HOSTNAME=\$(hostname -f)
TIMESTAMP=\$(date '+%Y-%m-%d %H:%M:%S')

log_entry() {
    echo "[\$TIMESTAMP] \$*" >> "\$LOG"
}

# La alerta queda siempre en el registro. Al canal va como mucho una vez por hora mientras dure,
# porque este chequeo corre cada cinco minutos y no recuerda lo que ya avisó. Si además no llega,
# se anota por qué: un webhook revocado no puede pasar desapercibido, porque es el único camino por
# el que las alertas salen.
send_alert() {
    local severity="\$1"
    local message="\$2"
    log_entry "ALERTA [\$severity]: \$message"

    local salida=0 respuesta=""
    if [[ -x "\$AVISO" ]]; then
        respuesta=\$("\$AVISO" --una-por-hora "\${severity} \${message}" \\
            "HoneyML [\${severity}] en \${HOSTNAME}, \${TIMESTAMP} UTC" "\$message") || salida=\$?
    fi
    if [[ "\$salida" -eq 2 ]]; then
        log_entry "AVISO: la alerta no llegó al canal (\${respuesta})"
    fi
}

# CPU
CPU_IDLE=\$(top -bn1 | grep 'Cpu(s)' | awk '{print \$8}' | tr -d '%id,' 2>/dev/null || echo "0")
CPU_USED=\$(echo "100 - \$CPU_IDLE" | bc 2>/dev/null || echo "0")
CPU_INT=\${CPU_USED%.*}
if [[ "\${CPU_INT:-0}" -ge "\$THRESHOLD_CPU" ]]; then
    send_alert "aviso" "CPU al \${CPU_USED}% (umbral: \${THRESHOLD_CPU}%)"
fi

# memoria
MEM_INFO=\$(free | grep Mem)
MEM_TOTAL=\$(echo "\$MEM_INFO" | awk '{print \$2}')
MEM_USED=\$(echo "\$MEM_INFO" | awk '{print \$3}')
MEM_PCT=\$(( MEM_USED * 100 / MEM_TOTAL ))
if [[ "\$MEM_PCT" -ge "\$THRESHOLD_MEM" ]]; then
    send_alert "aviso" "Memoria al \${MEM_PCT}% (umbral: \${THRESHOLD_MEM}%)"
fi

# Discos de verdad nada más: Docker monta una capa por cada contenedor en marcha, que df lista con
# el mismo porcentaje que el disco raíz, y un disco lleno saldría repetido una vez por contenedor.
while IFS= read -r line; do
    PCT=\$(echo "\$line" | awk '{print \$5}' | tr -d '%')
    MOUNT=\$(echo "\$line" | awk '{print \$6}')
    if [[ "\${PCT:-0}" -ge "\$THRESHOLD_DISK" ]]; then
        send_alert "aviso" "Disco \${MOUNT} al \${PCT}% (umbral: \${THRESHOLD_DISK}%)"
    fi
done < <(df -hP -x tmpfs -x devtmpfs -x overlay -x squashfs | tail -n +2)

# Con el demonio de Docker parado, cada consulta de abajo falla igual que la de un contenedor que no
# existe, y el chequeo los saltearía a todos en silencio.
if ! docker info >/dev/null 2>&1; then
    send_alert "critico" "Docker no contesta: los sensores y el análisis pueden estar caídos"
fi

# Contenedores de las dos zonas. Se pregunta por los que existen y no por los que corren: con
# 'docker ps' un contenedor frenado no figura en la lista, y la comprobación se saltearía justo en
# el caso que tiene que avisar. Uno que no existe se omite, para que el mismo chequeo sirva en un
# anfitrión que solo tiene los sensores y en uno que además corre el análisis.
for container in cowrie dionaea elasticsearch logstash filebeat valkey motor api; do
    STATUS=\$(docker inspect --format='{{.State.Status}}' "\$container" 2>/dev/null || echo "")
    if [[ -z "\$STATUS" ]]; then
        continue
    fi
    if [[ "\$STATUS" != "running" ]]; then
        send_alert "critico" "Contenedor '\${container}' en estado \${STATUS}"
    fi
done

# Elasticsearch en rojo: hay fragmentos sin asignar, y ahí el índice deja de contestar parte de las
# consultas. El amarillo no se avisa, porque con un solo nodo las réplicas quedan sin asignar por
# diseño. El || true va porque con set -e y pipefail una tubería que falla corta el script entero:
# sin él, cuando Elasticsearch no contesta o rechaza la consulta, el chequeo terminaría acá mismo y
# no llegaría a escribir el aviso de abajo, que es justo el que hace falta.
if docker inspect --format='{{.State.Status}}' elasticsearch >/dev/null 2>&1; then
    ES_ESTADO=\$(curl -s --max-time 10 http://localhost:9200/_cluster/health 2>/dev/null \
        | grep -o '"status":"[a-z]*"' | cut -d'"' -f4 || true)
    if [[ "\$ES_ESTADO" == "red" ]]; then
        send_alert "critico" "Elasticsearch en rojo"
    elif [[ -z "\$ES_ESTADO" ]]; then
        send_alert "aviso" "Elasticsearch no contesta el estado del clúster"
    fi
fi

# Atraso del bus. Que el motor esté corriendo no alcanza: si deja de consumir, el contenedor sigue
# en pie y lo único que lo delata es el atraso creciendo sin techo. La consulta se autentica igual
# que el healthcheck del compose, solo si hay clave. Va entre comillas simples para que la expanda
# el shell del contenedor con su propio BUS_PASSWORD: así este script no necesita conocer la clave.
# Sin autenticarse, valkey-cli contesta NOAUTH, sale con cero y el aviso no salta nunca. El || true
# cumple el mismo papel que en Elasticsearch: con el bus caído, el chequeo sigue hasta el de sshd.
if docker inspect --format='{{.State.Status}}' valkey >/dev/null 2>&1; then
    ATRASO=\$(docker exec valkey sh -c \
        'valkey-cli \${BUS_PASSWORD:+-a "\$BUS_PASSWORD"} --no-auth-warning --raw XINFO GROUPS honeyml:events' \
        2>/dev/null | awk '/^lag\$/{getline; print; exit}' || true)
    if [[ "\$ATRASO" =~ ^[0-9]+\$ ]] && [[ "\$ATRASO" -ge $THRESHOLD_ATRASO ]]; then
        send_alert "aviso" "El motor no consume: \${ATRASO} eventos de atraso en el bus"
    fi
fi

# el servicio SSH de administración
if ! ss -tlnp | grep -q ":2200 "; then
    send_alert "critico" "sshd no escucha en el puerto 2200: se pierde el acceso de administración"
fi

log_entry "Chequeo de salud completo: CPU al \${CPU_USED}%, memoria al \${MEM_PCT}%"
HEALTH_SCRIPT

chmod +x "$HEALTHCHECK_SCRIPT"
log "  Script creado."

log "[2/4] Instalando el reporte diario y el envío de avisos..."
install -m 755 "$REPO_VPS/honeyml_aviso.sh" "$AVISO_SCRIPT"
install -m 755 "$REPO_VPS/honeyml_daily_report.sh" "$DAILY_REPORT_SCRIPT"

log "[3/4] Instalando el watchdog, el respaldo y la purga..."
install -m 755 "$REPO_VPS/honeyml_watchdog.sh" "$WATCHDOG_SCRIPT"
install -m 755 "$REPO_VPS/honeyml_backup.sh" "$BACKUP_SCRIPT"
install -m 755 "$REPO_VPS/honeyml_purga_muestras.sh" "$PURGA_SCRIPT"
if command -v docker >/dev/null 2>&1; then
    docker build -q -t honeyml-pyspy "$REPO_VPS/pyspy" >/dev/null
    log "  Imagen honeyml-pyspy construida."
else
    log "  AVISO: sin Docker el watchdog no puede leer la pila de un sensor colgado."
fi

log "[4/4] Registrando tareas en cron..."

CRON_FILE="/etc/cron.d/honeyml-monitoring"
cat > "$CRON_FILE" << CRONEOF
# HoneyML: monitoreo de salud del VPS
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin

# chequeo de salud cada 5 minutos
*/5 * * * * root $HEALTHCHECK_SCRIPT >> $HEALTHCHECK_LOG 2>&1

# reporte diario a las 10:00 de Argentina, que son las 13:00 UTC todo el año porque Argentina no
# cambia la hora en verano
0 13 * * * root $DAILY_REPORT_SCRIPT >> $HEALTHCHECK_LOG 2>&1

# watchdog de los sensores cada 5 minutos
*/5 * * * * root $WATCHDOG_SCRIPT >> $WATCHDOG_LOG 2>&1

# respaldo diario de la telemetría y de las decisiones, a las 03:00 UTC
0 3 * * * root $BACKUP_SCRIPT >> $BACKUP_LOG 2>&1

# purga diaria de las muestras de malware de más de siete días, a las 05:00 UTC
0 5 * * * root $PURGA_SCRIPT >> $PURGA_LOG 2>&1

# rotación semanal de los registros del monitoreo. El de las muestras borradas queda afuera: en
# Dionaea es la única copia del hash de cada muestra
0 3 * * 0 root find /var/log -name "honeyml_*.log" ! -name "honeyml_muestras_borradas.log" -mtime +30 -delete 2>/dev/null || true

# retención semanal de los flujos grabados por Dionaea, que si no llenan el disco
0 4 * * 0 root find $BISTREAMS -type f -mtime +$RETENCION_BISTREAMS_DIAS -delete 2>/dev/null; find $BISTREAMS -mindepth 1 -type d -empty -delete 2>/dev/null || true
CRONEOF

chmod 644 "$CRON_FILE"
systemctl restart cron 2>/dev/null || systemctl restart crond 2>/dev/null || true

log ""
log "Monitoreo configurado."
log ""
log "Scripts instalados:"
log "  Chequeo de salud, cada 5 min:   $HEALTHCHECK_SCRIPT"
log "  Reporte diario, 10:00 (UTC-3):  $DAILY_REPORT_SCRIPT"
log "  Watchdog, cada 5 min:           $WATCHDOG_SCRIPT"
log "  Respaldo, 03:00 UTC:            $BACKUP_SCRIPT"
log "  Purga, 05:00 UTC:               $PURGA_SCRIPT"
log "  Registro del monitoreo:         $HEALTHCHECK_LOG"
log ""
log "Para probar a mano: sudo $HEALTHCHECK_SCRIPT, o sudo $DAILY_REPORT_SCRIPT para el reporte."
log ""
# El mensaje de prueba recorre el camino entero desde este servidor: que lea el archivo con la
# dirección, que resuelva el nombre del servicio y que pueda conectarse hacia afuera por HTTPS.
# Probar la dirección desde otra máquina no comprueba nada de eso.
salida=0
respuesta=$("$AVISO_SCRIPT" "HoneyML: monitoreo instalado en $(hostname -f)." \
    "Las alertas y el reporte diario de las 10 llegan a este canal.") || salida=$?
case "$salida" in
    0) log "Webhook: el canal aceptó el mensaje de prueba." ;;
    1) log "Sin webhook: las alertas quedan solo en el registro. Para configurarlo, correr este script con --webhook." ;;
    *) log "AVISO: el canal no aceptó el mensaje de prueba (${respuesta}). Revisar la dirección con --webhook." ;;
esac
