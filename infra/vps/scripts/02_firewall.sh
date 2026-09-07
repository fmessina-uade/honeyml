#!/bin/bash
# 02_firewall.sh
# Firewall UFW y reglas de aislamiento con iptables para HoneyML.
# Se corre DESPUÉS de 01_hardening.sh y de confirmar el acceso SSH por el puerto 2200.
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

log "=== HoneyML - Configuración de Firewall y Aislamiento de Red ==="

# chequeo previo: asegurarse de que el SSH del 2200 se alcance
log "Verificando que sshd escucha en puerto $SSH_ADMIN_PORT..."
if ! ss -tlnp | grep -q ":$SSH_ADMIN_PORT "; then
    die "sshd no escucha en puerto $SSH_ADMIN_PORT. Configurar sshd_config primero."
fi
log "  OK - sshd escucha en $SSH_ADMIN_PORT"

# 1. resetear UFW y fijar las políticas base
log "[1/5] Reseteando UFW y aplicando políticas base..."
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw default deny routed

# 2. reglas de acceso administrativo
log "[2/5] Configurando acceso administrativo..."
ufw limit "${SSH_ADMIN_PORT}/tcp" comment 'SSH Admin - rate limited'

# 3. puertos de los honeypots (tráfico de atacantes)
log "[3/5] Habilitando puertos de honeypots..."

# honeypot Cowrie de SSH y Telnet
ufw allow 22/tcp   comment 'Cowrie SSH honeypot'
ufw allow 23/tcp   comment 'Cowrie Telnet honeypot'

# captura multiprotocolo de Dionaea
ufw allow 21/tcp   comment 'Dionaea FTP'
ufw allow 80/tcp   comment 'Dionaea HTTP'
ufw allow 443/tcp  comment 'Dionaea HTTPS'
ufw allow 445/tcp  comment 'Dionaea SMB'
ufw allow 135/tcp  comment 'Dionaea MSRPC'
ufw allow 3306/tcp comment 'Dionaea MySQL honeypot'
ufw allow 5060/tcp comment 'Dionaea SIP TCP'
ufw allow 5060/udp comment 'Dionaea SIP UDP'
ufw allow 1433/tcp comment 'Dionaea MSSQL honeypot'

# 4. habilitar UFW con registro
log "[4/5] Activando UFW..."
ufw logging on
ufw --force enable

log "Estado del firewall:"
ufw status verbose | tee -a "$LOG_FILE"

# 5. reglas de iptables para aislar los contenedores de los honeypots
log "[5/5] Aplicando reglas de aislamiento Docker..."

# DOCKER-USER se evalúa antes que las reglas propias de Docker y sobrevive a un reinicio del
# demonio. Se bloquea la salida de la red de honeypots, así un atacante no puede usar el contenedor
# como pivote.
if ! iptables -C DOCKER-USER -s "$HONEYPOT_NET" -o eth0 -j DROP 2>/dev/null; then
    iptables -I DOCKER-USER 3 -s "$HONEYPOT_NET" -o eth0 -j DROP
    log "  Regla de egress honeypot aplicada."
fi

# excepción: se permite el tráfico dentro de la red (honeypot <-> sidecar de filebeat en fase 2)
if ! iptables -C DOCKER-USER -s "$HONEYPOT_NET" -d "$HONEYPOT_NET" -j ACCEPT 2>/dev/null; then
    iptables -I DOCKER-USER 1 -s "$HONEYPOT_NET" -d "$HONEYPOT_NET" -j ACCEPT
    log "  Tráfico intra-honeypot habilitado."
fi

# se permite el tráfico de VUELTA (ESTABLISHED/RELATED) hacia internet.
# sin esto se descartan los SYN-ACK de respuesta y el handshake TCP nunca se completa.
if ! iptables -C DOCKER-USER -s "$HONEYPOT_NET" -o eth0 -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT 2>/dev/null; then
    iptables -I DOCKER-USER 2 -s "$HONEYPOT_NET" -o eth0 -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
    log "  Tráfico de retorno ESTABLISHED/RELATED habilitado."
fi

# script propio: aplica solo nuestras reglas de DOCKER-USER y no toca las de Docker.
# un iptables-save/restore completo entra en conflicto al reiniciar, porque Docker regenera sus
# propias reglas y terminan duplicadas o en el orden equivocado respecto de las restauradas.
cat > /usr/local/bin/honeyml-docker-rules.sh << RULES_EOF
#!/bin/bash
HONEYPOT_NET="${HONEYPOT_NET}"

# esperar a que Docker cree la cadena DOCKER-USER (30 s como máximo)
for i in \$(seq 1 15); do
    iptables -L DOCKER-USER -n &>/dev/null && break
    sleep 2
done

if ! iptables -L DOCKER-USER -n &>/dev/null; then
    echo "ERROR: DOCKER-USER chain no disponible tras 30s" >&2
    exit 1
fi

# se permite el tráfico entre honeypots, que lo necesita el sidecar de la fase 2
if ! iptables -C DOCKER-USER -s "\$HONEYPOT_NET" -d "\$HONEYPOT_NET" -j ACCEPT 2>/dev/null; then
    iptables -I DOCKER-USER 1 -s "\$HONEYPOT_NET" -d "\$HONEYPOT_NET" -j ACCEPT
fi

# se permite el tráfico de VUELTA (ESTABLISHED/RELATED) de la red de honeypots hacia internet.
# sin eso se descartan los SYN-ACK de respuesta a las conexiones entrantes, el handshake TCP nunca
# se completa y Cowrie y Dionaea no registran la conexión.
if ! iptables -C DOCKER-USER -s "\$HONEYPOT_NET" -o eth0 -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT 2>/dev/null; then
    iptables -I DOCKER-USER 2 -s "\$HONEYPOT_NET" -o eth0 -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
fi

# se bloquea la salida NUEVA de la red de honeypots hacia internet, para que no sirva de pivote
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
