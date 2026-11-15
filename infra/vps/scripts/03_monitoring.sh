#!/bin/bash
# 03_monitoring.sh
# Monitoreo básico de salud del VPS. Instala el chequeo periódico con alertas por webhook (Slack,
# Discord o el que sea), el reporte diario, el watchdog de los sensores, el respaldo y la purga de
# muestras, y los deja programados en cron. Sin webhook, las alertas quedan solo en el registro.
#
# Uso: sudo bash 03_monitoring.sh [url_del_webhook]
# Ejemplo: sudo bash 03_monitoring.sh "https://hooks.slack.com/services/..."

set -euo pipefail

WEBHOOK_URL="${1:-}"
LOG_FILE="/var/log/honeyml_setup.log"
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

log "HoneyML: monitoreo de salud"

log "[1/4] Creando el chequeo de salud en $HEALTHCHECK_SCRIPT..."
cat > "$HEALTHCHECK_SCRIPT" << HEALTH_SCRIPT
#!/usr/bin/env bash
# honeyml_health.sh: chequeo periódico de métricas del VPS, lo corre cron cada 5 minutos.

set -euo pipefail

WEBHOOK_URL="${WEBHOOK_URL}"
LOG="${HEALTHCHECK_LOG}"
THRESHOLD_CPU=${THRESHOLD_CPU}
THRESHOLD_MEM=${THRESHOLD_MEM}
THRESHOLD_DISK=${THRESHOLD_DISK}
HOSTNAME=\$(hostname -f)
TIMESTAMP=\$(date '+%Y-%m-%d %H:%M:%S')

log_entry() {
    echo "[\$TIMESTAMP] \$*" >> "\$LOG"
}

send_alert() {
    local severity="\$1"
    local message="\$2"
    log_entry "ALERTA [\$severity]: \$message"

    if [[ -n "\$WEBHOOK_URL" ]]; then
        curl -s -X POST "\$WEBHOOK_URL" \
            -H 'Content-Type: application/json' \
            -d "{\"text\":\"HoneyML [\${severity}] en \${HOSTNAME}, \${TIMESTAMP}\\n\${message}\"}" \
            > /dev/null 2>&1 || true
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

# disco
while IFS= read -r line; do
    PCT=\$(echo "\$line" | awk '{print \$5}' | tr -d '%')
    MOUNT=\$(echo "\$line" | awk '{print \$6}')
    if [[ "\${PCT:-0}" -ge "\$THRESHOLD_DISK" ]]; then
        send_alert "aviso" "Disco \${MOUNT} al \${PCT}% (umbral: \${THRESHOLD_DISK}%)"
    fi
done < <(df -h | tail -n +2 | grep -v tmpfs)

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
# diseño.
if docker inspect --format='{{.State.Status}}' elasticsearch >/dev/null 2>&1; then
    ES_ESTADO=\$(curl -s --max-time 10 http://localhost:9200/_cluster/health 2>/dev/null \
        | grep -o '"status":"[a-z]*"' | cut -d'"' -f4)
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
# Sin autenticarse, valkey-cli contesta NOAUTH, sale con cero y el aviso no salta nunca.
if docker inspect --format='{{.State.Status}}' valkey >/dev/null 2>&1; then
    ATRASO=\$(docker exec valkey sh -c \
        'valkey-cli \${BUS_PASSWORD:+-a "\$BUS_PASSWORD"} --no-auth-warning --raw XINFO GROUPS honeyml:events' \
        2>/dev/null | awk '/^lag\$/{getline; print; exit}')
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

log "[2/4] Creando el reporte diario..."
DAILY_REPORT_SCRIPT="/usr/local/bin/honeyml_daily_report.sh"
cat > "$DAILY_REPORT_SCRIPT" << 'DAILY_SCRIPT'
#!/usr/bin/env bash
# honeyml_daily_report.sh: resumen diario de actividad de los honeypots.
set -euo pipefail

WEBHOOK_URL="${WEBHOOK_URL:-}"
DATE=$(date '+%Y-%m-%d')
COWRIE_LOG="/var/lib/docker/volumes/honeypots_cowrie_logs/_data/cowrie.json"

# contadores de actividad de Cowrie
SSH_ATTEMPTS=0
SUCCESSFUL_LOGINS=0
UNIQUE_IPS=0

if [[ -f "$COWRIE_LOG" ]]; then
    SSH_ATTEMPTS=$(grep -c '"eventid":"cowrie.login.failed"' "$COWRIE_LOG" 2>/dev/null || echo 0)
    SUCCESSFUL_LOGINS=$(grep -c '"eventid":"cowrie.login.success"' "$COWRIE_LOG" 2>/dev/null || echo 0)
    UNIQUE_IPS=$(grep '"src_ip"' "$COWRIE_LOG" 2>/dev/null | grep -oP '"src_ip":"[^"]*"' | sort -u | wc -l || echo 0)
fi

UPTIME=$(uptime -p 2>/dev/null || uptime)
MEM_FREE=$(free -h | grep Mem | awk '{print $4}')
DISK_FREE=$(df -h / | tail -1 | awk '{print $4}')

REPORT="HoneyML, reporte del ${DATE}
Sistema: en marcha ${UPTIME}, memoria libre ${MEM_FREE}, disco libre ${DISK_FREE}
Cowrie: ${SSH_ATTEMPTS} ingresos fallidos, ${SUCCESSFUL_LOGINS} exitosos, ${UNIQUE_IPS} direcciones distintas"

echo "$REPORT"

if [[ -n "$WEBHOOK_URL" ]]; then
    curl -s -X POST "$WEBHOOK_URL" \
        -H 'Content-Type: application/json' \
        -d "{\"text\":\"$REPORT\"}" > /dev/null 2>&1 || true
fi
DAILY_SCRIPT

chmod +x "$DAILY_REPORT_SCRIPT"

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

# reporte diario a las 07:00 de Argentina (UTC-3, o 10:00 UTC)
0 10 * * * root $DAILY_REPORT_SCRIPT >> $HEALTHCHECK_LOG 2>&1

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
log "  Reporte diario, 07:00 (UTC-3):  $DAILY_REPORT_SCRIPT"
log "  Watchdog, cada 5 min:           $WATCHDOG_SCRIPT"
log "  Respaldo, 03:00 UTC:            $BACKUP_SCRIPT"
log "  Purga, 05:00 UTC:               $PURGA_SCRIPT"
log "  Registro del monitoreo:         $HEALTHCHECK_LOG"
log ""
log "Para probar manualmente: bash $HEALTHCHECK_SCRIPT"
if [[ -z "$WEBHOOK_URL" ]]; then
    log ""
    log "No se configuró WEBHOOK_URL: las alertas quedan solo en el registro."
    log "Para mandarlas afuera, cargar WEBHOOK_URL en $HEALTHCHECK_SCRIPT."
fi
