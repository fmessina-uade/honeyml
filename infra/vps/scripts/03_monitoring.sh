#!/bin/bash
# 03_monitoring.sh
# Monitoreo básico de salud del VPS, para la fase 1 de HoneyML.
# Instala un script de chequeo con alertas por webhook (Slack, Discord o el que sea).
# En la fase 2 esto lo absorbe el Elastic Stack (Metricbeat).
#
# Uso: sudo bash 03_monitoring.sh <url_del_webhook>
# Ejemplo: sudo bash 03_monitoring.sh "https://hooks.slack.com/services/..."

set -euo pipefail

WEBHOOK_URL="${1:-}"
LOG_FILE="/var/log/honeyml_setup.log"
HEALTHCHECK_SCRIPT="/usr/local/bin/honeyml_health.sh"
HEALTHCHECK_LOG="/var/log/honeyml_health.log"
THRESHOLD_CPU=85
THRESHOLD_MEM=90
THRESHOLD_DISK=80
# el watchdog y su imagen viven en el repositorio, un nivel arriba de este script
REPO_VPS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WATCHDOG_SCRIPT="/usr/local/bin/honeyml_watchdog.sh"
WATCHDOG_LOG="/var/log/honeyml_watchdog.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

[[ $EUID -eq 0 ]] || { echo "Ejecutar como root." >&2; exit 1; }

log "=== HoneyML - Configuración de Monitoreo de Salud ==="

# 1. el script principal de chequeo de salud
log "[1/4] Creando script de health check en $HEALTHCHECK_SCRIPT..."
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
    log_entry "ALERT [\$severity]: \$message"

    if [[ -n "\$WEBHOOK_URL" ]]; then
        local emoji
        case "\$severity" in
            CRITICAL) emoji="🚨" ;;
            WARNING)  emoji="⚠️" ;;
            INFO)     emoji="ℹ️" ;;
            *)        emoji="📋" ;;
        esac
        curl -s -X POST "\$WEBHOOK_URL" \
            -H 'Content-Type: application/json' \
            -d "{\"text\":\"\${emoji} *HoneyML VPS Alert* [\${severity}]\\n*Host:* \${HOSTNAME}\\n*Tiempo:* \${TIMESTAMP}\\n*Detalle:* \${message}\"}" \
            > /dev/null 2>&1 || true
    fi
}

# CPU
CPU_IDLE=\$(top -bn1 | grep 'Cpu(s)' | awk '{print \$8}' | tr -d '%id,' 2>/dev/null || echo "0")
CPU_USED=\$(echo "100 - \$CPU_IDLE" | bc 2>/dev/null || echo "0")
CPU_INT=\${CPU_USED%.*}
if [[ "\${CPU_INT:-0}" -ge "\$THRESHOLD_CPU" ]]; then
    send_alert "WARNING" "CPU al \${CPU_USED}% (umbral: \${THRESHOLD_CPU}%)"
fi

# memory
MEM_INFO=\$(free | grep Mem)
MEM_TOTAL=\$(echo "\$MEM_INFO" | awk '{print \$2}')
MEM_USED=\$(echo "\$MEM_INFO" | awk '{print \$3}')
MEM_PCT=\$(( MEM_USED * 100 / MEM_TOTAL ))
if [[ "\$MEM_PCT" -ge "\$THRESHOLD_MEM" ]]; then
    send_alert "WARNING" "Memoria al \${MEM_PCT}% (umbral: \${THRESHOLD_MEM}%)"
fi

# disk
while IFS= read -r line; do
    PCT=\$(echo "\$line" | awk '{print \$5}' | tr -d '%')
    MOUNT=\$(echo "\$line" | awk '{print \$6}')
    if [[ "\${PCT:-0}" -ge "\$THRESHOLD_DISK" ]]; then
        send_alert "WARNING" "Disco \${MOUNT} al \${PCT}% (umbral: \${THRESHOLD_DISK}%)"
    fi
done < <(df -h | tail -n +2 | grep -v tmpfs)

# honeypot containers
for container in cowrie dionaea; do
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^\${container}\$"; then
        STATUS=\$(docker inspect --format='{{.State.Status}}' "\$container" 2>/dev/null || echo "unknown")
        if [[ "\$STATUS" != "running" ]]; then
            send_alert "CRITICAL" "Contenedor '\${container}' no está corriendo (estado: \${STATUS})"
        fi
    fi
done

# el servicio SSH de administración
if ! ss -tlnp | grep -q ":2200 "; then
    send_alert "CRITICAL" "sshd no escucha en puerto 2200 - pérdida de acceso administrativo"
fi

log_entry "Health check completado - CPU:\${CPU_USED}% MEM:\${MEM_PCT}% OK"
HEALTH_SCRIPT

chmod +x "$HEALTHCHECK_SCRIPT"
log "  Script creado."

# 2. el script del reporte diario
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

REPORT="📊 *HoneyML Reporte Diario - ${DATE}*
*Sistema:* Uptime: ${UPTIME} | RAM libre: ${MEM_FREE} | Disco libre: ${DISK_FREE}
*Cowrie (SSH):* Intentos fallidos: ${SSH_ATTEMPTS} | Logins exitosos: ${SUCCESSFUL_LOGINS} | IPs únicas: ${UNIQUE_IPS}"

echo "$REPORT"

if [[ -n "$WEBHOOK_URL" ]]; then
    curl -s -X POST "$WEBHOOK_URL" \
        -H 'Content-Type: application/json' \
        -d "{\"text\":\"$REPORT\"}" > /dev/null 2>&1 || true
fi
DAILY_SCRIPT

chmod +x "$DAILY_REPORT_SCRIPT"

# 3. el watchdog de los sensores, y la imagen con la que lee la pila de un proceso colgado
log "[3/4] Instalando el watchdog de los sensores..."
install -m 755 "$REPO_VPS/honeyml_watchdog.sh" "$WATCHDOG_SCRIPT"
if command -v docker >/dev/null 2>&1; then
    docker build -q -t honeyml-pyspy "$REPO_VPS/pyspy" >/dev/null
    log "  Imagen honeyml-pyspy construida."
else
    log "  AVISO: sin Docker el watchdog no puede leer la pila de un sensor colgado."
fi

# 4. se registran las tareas de cron
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

# rotación semanal del registro de actividad de los honeypots
0 3 * * 0 root find /var/log -name "honeyml_*.log" -mtime +30 -delete 2>/dev/null || true
CRONEOF

chmod 644 "$CRON_FILE"
systemctl restart cron 2>/dev/null || systemctl restart crond 2>/dev/null || true

log ""
log "=== Monitoreo configurado exitosamente ==="
log ""
log "Scripts instalados:"
log "  Health check (c/5 min) : $HEALTHCHECK_SCRIPT"
log "  Reporte diario (07:00) : $DAILY_REPORT_SCRIPT"
log "  Watchdog (c/5 min)     : $WATCHDOG_SCRIPT"
log "  Log de monitoreo       : $HEALTHCHECK_LOG"
log ""
log "Para probar manualmente: bash $HEALTHCHECK_SCRIPT"
if [[ -z "$WEBHOOK_URL" ]]; then
    log ""
    log "NOTA: No se configuró WEBHOOK_URL. Las alertas solo se registrarán en log."
    log "Para habilitar alertas, editar $HEALTHCHECK_SCRIPT y actualizar WEBHOOK_URL."
fi
