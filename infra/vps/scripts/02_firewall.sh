#!/bin/bash
# Firewall UFW y reglas de aislamiento con iptables para HoneyML. Se corre con sudo, después de
# 01_hardening.sh y de confirmar que el acceso SSH por el puerto 2200 anda: si se corre antes, la
# sesión de administración puede quedar afuera.

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

log "HoneyML: firewall y aislamiento de red"

# si sshd no escucha en el 2200, activar UFW deja afuera a la sesión de administración
log "Verificando que sshd escucha en puerto $SSH_ADMIN_PORT..."
if ! ss -tlnp | grep -q ":$SSH_ADMIN_PORT "; then
    die "sshd no escucha en puerto $SSH_ADMIN_PORT. Configurar sshd_config primero."
fi
log "  OK: sshd escucha en el $SSH_ADMIN_PORT"

log "[1/5] Reseteando UFW y aplicando políticas base..."
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw default deny routed

log "[2/5] Configurando acceso administrativo..."
# Lo que entra al anfitrión desde la red de honeypots se descarta antes que cualquier otra regla. Sin
# esto, un atacante con ejecución en un sensor alcanza el sshd de administración por la puerta de
# enlace del bridge. Las respuestas a conexiones que abre el anfitrión pasan igual, porque UFW acepta
# el tráfico establecido antes de mirar las reglas de usuario.
ufw deny in on br-honeypot comment 'Sensores hacia el anfitrion'
ufw limit "${SSH_ADMIN_PORT}/tcp" comment 'SSH de administracion, con limite de tasa'

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
ufw allow 1433/tcp comment 'Dionaea MSSQL honeypot'

log "[4/5] Activando UFW..."
ufw logging on
ufw --force enable

log "Estado del firewall:"
ufw status verbose | tee -a "$LOG_FILE"

log "[5/5] Aplicando reglas de aislamiento Docker..."

# DOCKER-USER se evalúa antes que las reglas propias de Docker y sobrevive a un reinicio del demonio.
# Las reglas viven en un script propio, que se corre al instalar y en cada arranque, y aplica solo
# lo nuestro sin tocar lo de Docker. Un iptables-save/restore completo entra en conflicto al
# reiniciar, porque Docker regenera sus propias reglas y terminan duplicadas o en el orden
# equivocado respecto de las restauradas.
cat > /usr/local/bin/honeyml-docker-rules.sh << RULES_EOF
#!/bin/bash
HONEYPOT_NET="${HONEYPOT_NET}"

# esperar a que Docker cree la cadena DOCKER-USER (30 s como máximo)
for i in \$(seq 1 15); do
    iptables -L DOCKER-USER -n &>/dev/null && break
    sleep 2
done

if ! iptables -L DOCKER-USER -n &>/dev/null; then
    echo "ERROR: la cadena DOCKER-USER no está disponible después de 30 s" >&2
    exit 1
fi

# Los sensores no se hablan entre sí: uno comprometido no puede usar al otro de trampolín. Es lo
# mismo que enable_icc: false en el compose, repetido acá porque esta cadena se evalúa antes que las
# reglas con que Docker lo implementa, y un ACCEPT en ella lo anularía.
if ! iptables -C DOCKER-USER -i br-honeypot -o br-honeypot -j DROP 2>/dev/null; then
    iptables -I DOCKER-USER 1 -i br-honeypot -o br-honeypot -j DROP
fi

# Se permite el tráfico de vuelta (ESTABLISHED y RELATED) de la red de honeypots hacia internet.
# Sin esta regla se descartan los SYN-ACK de respuesta a las conexiones entrantes, el handshake
# TCP nunca se completa y Cowrie y Dionaea no registran la conexión.
if ! iptables -C DOCKER-USER -s "\$HONEYPOT_NET" -o eth0 -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT 2>/dev/null; then
    iptables -I DOCKER-USER 2 -s "\$HONEYPOT_NET" -o eth0 -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
fi

# se bloquea toda conexión nueva de la red de honeypots hacia internet, para que no sirva de pivote
if ! iptables -C DOCKER-USER -s "\$HONEYPOT_NET" -o eth0 -j DROP 2>/dev/null; then
    iptables -I DOCKER-USER 3 -s "\$HONEYPOT_NET" -o eth0 -j DROP
fi

echo "Reglas DOCKER-USER de HoneyML aplicadas"
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
log "Firewall configurado."
log ""
log "Resumen de configuración:"
log "  Puerto SSH de administración: $SSH_ADMIN_PORT (con límite de tasa)"
log "  Red de los honeypots:         $HONEYPOT_NET (salida y tráfico entre sensores bloqueados)"
log "  Puertos de los honeypots:     22, 23, 21, 80, 443, 445, 135, 3306, 1433"
log ""
log "Después, correr 03_monitoring.sh."
