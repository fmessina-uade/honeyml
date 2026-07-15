#!/bin/bash
# 02_firewall.sh
# UFW firewall + iptables isolation rules for HoneyML.
# Run AFTER 01_hardening.sh and after confirming SSH access on port 2200.
#
# Usage: sudo bash 02_firewall.sh

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

log "=== HoneyML - Configuración de Firewall y Aislamiento de Red ==="

# pre-check: make sure SSH on 2200 is reachable
log "Verificando que sshd escucha en puerto $SSH_ADMIN_PORT..."
if ! ss -tlnp | grep -q ":$SSH_ADMIN_PORT "; then
    die "sshd no escucha en puerto $SSH_ADMIN_PORT. Configurar sshd_config primero."
fi
log "  OK - sshd escucha en $SSH_ADMIN_PORT"

# 1. reset UFW and set base policies
log "[1/5] Reseteando UFW y aplicando políticas base..."
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw default deny routed

# 2. admin access rules
log "[2/5] Configurando acceso administrativo..."
ufw limit "${SSH_ADMIN_PORT}/tcp" comment 'SSH Admin - rate limited'

# 3. honeypot ports (attacker traffic)
log "[3/5] Habilitando puertos de honeypots..."

# Cowrie SSH and Telnet honeypot
ufw allow 22/tcp   comment 'Cowrie SSH honeypot'
ufw allow 23/tcp   comment 'Cowrie Telnet honeypot'

# Dionaea multiprotocol capture
ufw allow 21/tcp   comment 'Dionaea FTP'
ufw allow 80/tcp   comment 'Dionaea HTTP'
ufw allow 443/tcp  comment 'Dionaea HTTPS'
ufw allow 445/tcp  comment 'Dionaea SMB'
ufw allow 135/tcp  comment 'Dionaea MSRPC'
ufw allow 3306/tcp comment 'Dionaea MySQL honeypot'
ufw allow 5060/tcp comment 'Dionaea SIP TCP'
ufw allow 5060/udp comment 'Dionaea SIP UDP'
ufw allow 1433/tcp comment 'Dionaea MSSQL honeypot'

# 4. enable UFW with logging
log "[4/5] Activando UFW..."
ufw logging on
ufw --force enable

log "Estado del firewall:"
ufw status verbose | tee -a "$LOG_FILE"

# 5. iptables rules to isolate the honeypot containers
log "[5/5] Aplicando reglas de aislamiento Docker..."

# DOCKER-USER is evaluated before Docker's own rules and survives a daemon restart.
# Block the honeypot network's egress (stops an attacker using the container as a pivot).
if ! iptables -C DOCKER-USER -s "$HONEYPOT_NET" -o eth0 -j DROP 2>/dev/null; then
    iptables -I DOCKER-USER 3 -s "$HONEYPOT_NET" -o eth0 -j DROP
    log "  Regla de egress honeypot aplicada."
fi

# exception: allow intra-network traffic (honeypot <-> filebeat sidecar in phase 2)
if ! iptables -C DOCKER-USER -s "$HONEYPOT_NET" -d "$HONEYPOT_NET" -j ACCEPT 2>/dev/null; then
    iptables -I DOCKER-USER 1 -s "$HONEYPOT_NET" -d "$HONEYPOT_NET" -j ACCEPT
    log "  Tráfico intra-honeypot habilitado."
fi

# allow RETURN traffic (ESTABLISHED/RELATED) out to the internet.
# without this the reply SYN-ACKs get dropped and the TCP handshake never completes.
if ! iptables -C DOCKER-USER -s "$HONEYPOT_NET" -o eth0 -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT 2>/dev/null; then
    iptables -I DOCKER-USER 2 -s "$HONEYPOT_NET" -o eth0 -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
    log "  Tráfico de retorno ESTABLISHED/RELATED habilitado."
fi

# dedicated script: applies only our custom DOCKER-USER rules, leaving Docker's alone.
# a full iptables-save/restore conflicts on reboot because Docker regenerates its own rules and
# they end up duplicated or in the wrong order relative to the restored ones.
cat > /usr/local/bin/honeyml-docker-rules.sh << RULES_EOF
#!/bin/bash
HONEYPOT_NET="${HONEYPOT_NET}"

# wait until Docker creates the DOCKER-USER chain (max 30s)
for i in \$(seq 1 15); do
    iptables -L DOCKER-USER -n &>/dev/null && break
    sleep 2
done

if ! iptables -L DOCKER-USER -n &>/dev/null; then
    echo "ERROR: DOCKER-USER chain no disponible tras 30s" >&2
    exit 1
fi

# allow intra-honeypot traffic (needed for the phase 2 sidecar)
if ! iptables -C DOCKER-USER -s "\$HONEYPOT_NET" -d "\$HONEYPOT_NET" -j ACCEPT 2>/dev/null; then
    iptables -I DOCKER-USER 1 -s "\$HONEYPOT_NET" -d "\$HONEYPOT_NET" -j ACCEPT
fi

# allow RETURN traffic (ESTABLISHED/RELATED) from the honeypot network out to the internet.
# without it the reply SYN-ACKs to inbound connections get dropped, so the TCP handshake never
# completes and Cowrie/Dionaea never record the connection.
if ! iptables -C DOCKER-USER -s "\$HONEYPOT_NET" -o eth0 -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT 2>/dev/null; then
    iptables -I DOCKER-USER 2 -s "\$HONEYPOT_NET" -o eth0 -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
fi

# block NEW egress from the honeypot network to the internet (no pivoting)
if ! iptables -C DOCKER-USER -s "\$HONEYPOT_NET" -o eth0 -j DROP 2>/dev/null; then
    iptables -I DOCKER-USER 3 -s "\$HONEYPOT_NET" -o eth0 -j DROP
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
