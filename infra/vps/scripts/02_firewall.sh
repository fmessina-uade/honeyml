#!/bin/bash
# 02_firewall.sh
# Configuración del firewall UFW y reglas iptables de aislamiento para HoneyML.
# Debe ejecutarse DESPUÉS de 01_hardening.sh y de verificar acceso SSH en puerto 2200.
#
# Uso: sudo bash 02_firewall.sh

set -euo pipefail

LOG_FILE="/var/log/honeyml_setup.log"
SSH_ADMIN_PORT="2200"
HONEYPOT_NET="172.20.0.0/16"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

die() {
    log "ERROR: $*" >&2
    exit 1
}

[[ $EUID -eq 0 ]] || die "Este script debe ejecutarse como root."

log "=== HoneyML — Configuración de Firewall y Aislamiento de Red ==="

# ---------------------------------------------------------------------------
# Verificación previa: confirmar que SSH en 2200 es accesible
# ---------------------------------------------------------------------------
log "Verificando que sshd escucha en puerto $SSH_ADMIN_PORT..."
if ! ss -tlnp | grep -q ":$SSH_ADMIN_PORT "; then
    die "sshd no escucha en puerto $SSH_ADMIN_PORT. Configurar sshd_config primero."
fi
log "  OK — sshd escucha en $SSH_ADMIN_PORT"

# ---------------------------------------------------------------------------
# 1. Reset y políticas base de UFW
# ---------------------------------------------------------------------------
log "[1/5] Reseteando UFW y aplicando políticas base..."
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw default deny routed

# ---------------------------------------------------------------------------
# 2. Reglas de acceso administrativo
# ---------------------------------------------------------------------------
log "[2/5] Configurando acceso administrativo..."
ufw limit "${SSH_ADMIN_PORT}/tcp" comment 'SSH Admin — rate limited'

# ---------------------------------------------------------------------------
# 3. Puertos de honeypots (tráfico de atacantes)
# ---------------------------------------------------------------------------
log "[3/5] Habilitando puertos de honeypots..."

# Cowrie — SSH y Telnet honeypot
ufw allow 22/tcp   comment 'Cowrie SSH honeypot'
ufw allow 23/tcp   comment 'Cowrie Telnet honeypot'

# Dionaea — captura multiprotocolo
ufw allow 21/tcp   comment 'Dionaea FTP'
ufw allow 80/tcp   comment 'Dionaea HTTP'
ufw allow 443/tcp  comment 'Dionaea HTTPS'
ufw allow 445/tcp  comment 'Dionaea SMB'
ufw allow 135/tcp  comment 'Dionaea MSRPC'
ufw allow 3306/tcp comment 'Dionaea MySQL honeypot'
ufw allow 5060/tcp comment 'Dionaea SIP TCP'
ufw allow 5060/udp comment 'Dionaea SIP UDP'
ufw allow 1433/tcp comment 'Dionaea MSSQL honeypot'

# ---------------------------------------------------------------------------
# 4. Activar UFW con logging
# ---------------------------------------------------------------------------
log "[4/5] Activando UFW..."
ufw logging on
ufw --force enable

log "Estado del firewall:"
ufw status verbose | tee -a "$LOG_FILE"

# ---------------------------------------------------------------------------
# 5. Reglas iptables para aislamiento de contenedores honeypot
# ---------------------------------------------------------------------------
log "[5/5] Aplicando reglas de aislamiento Docker..."

# DOCKER-USER se evalúa antes que las reglas de Docker y no se sobreescribe al reiniciar el daemon
# Bloquear egress de la red honeypot (evita que un atacante use el contenedor como pivot)
if ! iptables -C DOCKER-USER -s "$HONEYPOT_NET" -o eth0 -j DROP 2>/dev/null; then
    iptables -I DOCKER-USER 1 -s "$HONEYPOT_NET" -o eth0 -j DROP
    log "  Regla de egress honeypot aplicada."
fi

# Excepción: permitir tráfico intra-red (honeypot <-> filebeat sidecar en Fase 2)
if ! iptables -C DOCKER-USER -s "$HONEYPOT_NET" -d "$HONEYPOT_NET" -j ACCEPT 2>/dev/null; then
    iptables -I DOCKER-USER 1 -s "$HONEYPOT_NET" -d "$HONEYPOT_NET" -j ACCEPT
    log "  Tráfico intra-honeypot habilitado."
fi

# Script dedicado: solo aplica las reglas custom de DOCKER-USER, sin tocar las de Docker.
# iptables-save/restore completo genera conflictos al reboot porque Docker regenera sus
# propias reglas y quedan duplicadas o en orden incorrecto con las restauradas.
cat > /usr/local/bin/honeyml-docker-rules.sh << RULES_EOF
#!/bin/bash
HONEYPOT_NET="${HONEYPOT_NET}"

# Esperar hasta que Docker cree la cadena DOCKER-USER (máx 30s)
for i in \$(seq 1 15); do
    iptables -L DOCKER-USER -n &>/dev/null && break
    sleep 2
done

if ! iptables -L DOCKER-USER -n &>/dev/null; then
    echo "ERROR: DOCKER-USER chain no disponible tras 30s" >&2
    exit 1
fi

# Permitir tráfico intra-honeypot (requerido para sidecar de Fase 2)
if ! iptables -C DOCKER-USER -s "\$HONEYPOT_NET" -d "\$HONEYPOT_NET" -j ACCEPT 2>/dev/null; then
    iptables -I DOCKER-USER 1 -s "\$HONEYPOT_NET" -d "\$HONEYPOT_NET" -j ACCEPT
fi

# Bloquear egress de la red honeypot hacia internet (evita uso como pivot)
if ! iptables -C DOCKER-USER -s "\$HONEYPOT_NET" -o eth0 -j DROP 2>/dev/null; then
    iptables -I DOCKER-USER 2 -s "\$HONEYPOT_NET" -o eth0 -j DROP
fi

echo "HoneyML DOCKER-USER rules applied OK"
RULES_EOF

chmod +x /usr/local/bin/honeyml-docker-rules.sh
/usr/local/bin/honeyml-docker-rules.sh

cat > /etc/systemd/system/honeyml-iptables.service << 'SYSTEMD_EOF'
[Unit]
Description=HoneyML - Reglas de aislamiento DOCKER-USER
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/honeyml-docker-rules.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
SYSTEMD_EOF

systemctl daemon-reload
systemctl enable honeyml-iptables.service
log "  Reglas DOCKER-USER aplicadas y servicio de persistencia configurado."

log ""
log "=== Configuración de firewall completada ==="
log ""
log "Resumen de configuración:"
log "  Puerto SSH admin : $SSH_ADMIN_PORT (rate limited)"
log "  Red honeypots    : $HONEYPOT_NET (egress bloqueado)"
log "  Honeypots expuestos en: 22, 23, 21, 80, 443, 445, 135, 3306, 5060, 1433"
log ""
log "Próximo paso: bash 03_monitoring.sh"
