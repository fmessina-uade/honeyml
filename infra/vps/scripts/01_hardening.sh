#!/bin/bash
# 01_hardening.sh
# Hardening inicial del VPS Ubuntu 22.04 LTS para el proyecto HoneyML.
# Ejecutar como root inmediatamente después de aprovisionar el Droplet en DigitalOcean.
#
# Uso: sudo bash 01_hardening.sh <usuario_admin>
# Ejemplo: sudo bash 01_hardening.sh honeyml

set -euo pipefail

ADMIN_USER="${1:-honeyml}"
LOG_FILE="/var/log/honeyml_setup.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

die() {
    log "ERROR: $*" >&2
    exit 1
}

[[ $EUID -eq 0 ]] || die "Este script debe ejecutarse como root."

log "=== HoneyML — Hardening del Sistema Operativo ==="
log "Usuario administrador: $ADMIN_USER"
log "SO detectado: $(lsb_release -ds 2>/dev/null || uname -r)"

# ---------------------------------------------------------------------------
# 1. Actualización del sistema
# ---------------------------------------------------------------------------
log "[1/12] Actualizando paquetes del sistema..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get dist-upgrade -y -qq
apt-get -f install -y -qq
apt-get autoremove -y -qq
apt-get autoclean -qq

# ---------------------------------------------------------------------------
# 2. Herramientas de seguridad y utilidades
# ---------------------------------------------------------------------------
log "[2/12] Instalando herramientas de seguridad..."
echo "postfix postfix/main_mailer_type select No configuration" | debconf-set-selections
echo "postfix postfix/mailname string $(hostname -f)" | debconf-set-selections
apt-get install -y -qq \
    fail2ban \
    ufw \
    unattended-upgrades \
    apt-listchanges \
    libpam-pwquality \
    auditd \
    aide \
    logwatch \
    chrony \
    curl \
    wget \
    jq \
    htop \
    vim \
    net-tools \
    tcpdump

# ---------------------------------------------------------------------------
# 3. Crear usuario administrador no-root
# ---------------------------------------------------------------------------
log "[3/12] Configurando usuario administrador..."
if ! id "$ADMIN_USER" &>/dev/null; then
    useradd -m -s /bin/bash -G sudo "$ADMIN_USER"
    passwd -l "$ADMIN_USER"
    log "  Usuario '$ADMIN_USER' creado con login por contraseña deshabilitado."
else
    log "  Usuario '$ADMIN_USER' ya existe, verificando grupos..."
    usermod -aG sudo "$ADMIN_USER"
fi

mkdir -p "/home/$ADMIN_USER/.ssh"
chmod 700 "/home/$ADMIN_USER/.ssh"
chown "$ADMIN_USER:$ADMIN_USER" "/home/$ADMIN_USER/.ssh"

# DigitalOcean añade las claves SSH del proyecto a root en el rebuild — las copiamos al admin
if [[ -f /root/.ssh/authorized_keys ]]; then
    cp /root/.ssh/authorized_keys "/home/$ADMIN_USER/.ssh/authorized_keys"
    chmod 600 "/home/$ADMIN_USER/.ssh/authorized_keys"
    chown "$ADMIN_USER:$ADMIN_USER" "/home/$ADMIN_USER/.ssh/authorized_keys"
    log "  Clave pública copiada de root a '$ADMIN_USER'."
else
    log "  ADVERTENCIA: /root/.ssh/authorized_keys no encontrado. Copiar clave manualmente."
fi

echo "$ADMIN_USER ALL=(ALL) NOPASSWD:ALL" > "/etc/sudoers.d/$ADMIN_USER"
chmod 440 "/etc/sudoers.d/$ADMIN_USER"
log "  Sudo NOPASSWD configurado para '$ADMIN_USER'."

# ---------------------------------------------------------------------------
# 4. Actualizaciones automáticas de seguridad
# ---------------------------------------------------------------------------
log "[4/12] Configurando actualizaciones automáticas..."
cat > /etc/apt/apt.conf.d/20auto-upgrades << 'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Download-Upgradeable-Packages "1";
APT::Periodic::AutocleanInterval "7";
APT::Periodic::Unattended-Upgrade "1";
EOF

# ---------------------------------------------------------------------------
# 5. Política de contraseñas (complementa autenticación por clave)
# ---------------------------------------------------------------------------
log "[5/12] Configurando política de contraseñas..."
cat > /etc/security/pwquality.conf << 'EOF'
minlen = 16
dcredit = -1
ucredit = -1
ocredit = -1
lcredit = -1
maxrepeat = 3
reject_username = 1
gecoscheck = 1
EOF

# ---------------------------------------------------------------------------
# 6. Parámetros de seguridad del kernel (sysctl)
# ---------------------------------------------------------------------------
log "[6/12] Aplicando parámetros de hardening del kernel..."
cat > /etc/sysctl.d/99-honeyml.conf << 'EOF'
# Protección contra IP spoofing / source routing
net.ipv4.conf.all.rp_filter = 1
net.ipv4.conf.default.rp_filter = 1
net.ipv4.conf.all.accept_source_route = 0
net.ipv4.conf.default.accept_source_route = 0

# Deshabilitar ICMP redirects
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.default.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0
net.ipv6.conf.all.accept_redirects = 0
net.ipv6.conf.default.accept_redirects = 0

# Ignorar broadcasts ICMP
net.ipv4.icmp_echo_ignore_broadcasts = 1

# Protección SYN flood
net.ipv4.tcp_syncookies = 1
net.ipv4.tcp_max_syn_backlog = 2048
net.ipv4.tcp_synack_retries = 2

# Protección TIME_WAIT
net.ipv4.tcp_rfc1337 = 1

# Logging de paquetes sospechosos
net.ipv4.conf.all.log_martians = 1
net.ipv4.conf.default.log_martians = 1

# IP forwarding habilitado para Docker (requerido para contenedores)
net.ipv4.ip_forward = 1

# Deshabilitar IPv6 (no necesario para el proyecto)
net.ipv6.conf.all.disable_ipv6 = 1
net.ipv6.conf.default.disable_ipv6 = 1
EOF
sysctl -p /etc/sysctl.d/99-honeyml.conf

# ---------------------------------------------------------------------------
# 7. Límites del sistema
# ---------------------------------------------------------------------------
log "[7/12] Configurando límites del sistema..."
cat >> /etc/security/limits.conf << 'EOF'
# HoneyML — limits
* soft nofile 65536
* hard nofile 65536
* soft nproc  4096
* hard nproc  4096
EOF

# ---------------------------------------------------------------------------
# 8. Deshabilitar servicios innecesarios
# ---------------------------------------------------------------------------
log "[8/12] Deshabilitando servicios no requeridos..."
UNWANTED_SERVICES=(avahi-daemon cups bluetooth rpcbind snapd)
for svc in "${UNWANTED_SERVICES[@]}"; do
    if systemctl list-unit-files "$svc.service" &>/dev/null 2>&1; then
        systemctl disable --now "$svc" 2>/dev/null || true
        log "  Deshabilitado: $svc"
    fi
done

# ---------------------------------------------------------------------------
# 9. Sincronización de tiempo (crítica para correlación de logs)
# ---------------------------------------------------------------------------
log "[9/12] Configurando sincronización NTP con chrony..."
systemctl enable --now chrony
chronyc makestep || true

# ---------------------------------------------------------------------------
# 10. fail2ban — protección SSH
# ---------------------------------------------------------------------------
log "[10/12] Configurando fail2ban..."
cat > /etc/fail2ban/jail.local << 'EOF'
[DEFAULT]
bantime  = 86400
findtime = 600
maxretry = 3
backend  = systemd
loglevel = INFO

[sshd]
enabled  = true
port     = 2200
logpath  = %(sshd_log)s
maxretry = 3
bantime  = 604800
EOF
systemctl enable --now fail2ban

# ---------------------------------------------------------------------------
# 11. Instalar Docker Engine
# ---------------------------------------------------------------------------
log "[11/12] Instalando Docker Engine..."
if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | bash
    usermod -aG docker "$ADMIN_USER"
    log "  Docker instalado. Usuario '$ADMIN_USER' agregado al grupo docker."
else
    log "  Docker ya está instalado: $(docker --version)"
    usermod -aG docker "$ADMIN_USER" 2>/dev/null || true
fi

# Configurar Docker daemon con opciones de seguridad
mkdir -p /etc/docker
cat > /etc/docker/daemon.json << 'EOF'
{
    "log-driver": "json-file",
    "log-opts": {
        "max-size": "10m",
        "max-file": "5"
    },
    "no-new-privileges": true,
    "icc": false,
    "live-restore": true
}
EOF
systemctl restart docker || true

# Instalar Docker Compose plugin
if ! docker compose version &>/dev/null 2>&1; then
    apt-get install -y -qq docker-compose-plugin
fi

# ---------------------------------------------------------------------------
# 12. SSH — config hardened y sin socket activation (estable en Ubuntu 24.04)
# ---------------------------------------------------------------------------
log "[12/13] Configurando SSH en puerto 2200..."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SSHD_CONFIG_SRC="$SCRIPT_DIR/../configs/sshd_config"

# El banner debe existir antes de que sshd -t lo valide
cat > /etc/ssh/banner_honeyml << 'EOF'

  Acceso restringido — sistema de investigacion de seguridad.
  Toda actividad es monitoreada y registrada.

EOF

if [[ -f "$SSHD_CONFIG_SRC" ]]; then
    cp "$SSHD_CONFIG_SRC" /etc/ssh/sshd_config
    # Actualizar AllowUsers para que coincida con el usuario admin real
    sed -i "s/^AllowUsers.*/AllowUsers $ADMIN_USER/" /etc/ssh/sshd_config
    mkdir -p /run/sshd  # requerido por sshd -t en sistemas recién instalados
    sshd -t || die "sshd_config inválido — verificar $SSHD_CONFIG_SRC"
    log "  sshd_config hardened aplicado (Port 2200, AllowUsers $ADMIN_USER)."
else
    log "  ADVERTENCIA: $SSHD_CONFIG_SRC no encontrado. Aplicar sshd_config manualmente."
fi

# Ubuntu 24.04 usa socket activation para SSH por defecto, lo cual es frágil al reboot
# cuando Docker también modifica iptables. Usamos el servicio directo para mayor estabilidad.
systemctl stop ssh.socket 2>/dev/null || true
systemctl disable ssh.socket 2>/dev/null || true
systemctl unmask ssh 2>/dev/null || true
systemctl enable ssh
systemctl restart ssh
sleep 2
if ss -tlnp | grep -q ':2200 '; then
    log "  OK — sshd escucha en puerto 2200 (servicio directo, sin socket activation)."
else
    log "  ADVERTENCIA — sshd no detectado en puerto 2200. Verificar manualmente antes de continuar."
fi

# ---------------------------------------------------------------------------
# 13. Inicializar AIDE (sistema de detección de intrusiones basado en archivos)
# ---------------------------------------------------------------------------
log "[13/13] Inicializando base de datos AIDE..."
aideinit -y -f 2>/dev/null || aide --init 2>/dev/null || log "  AIDE: completar manualmente con 'aideinit'"

# ---------------------------------------------------------------------------
# Resumen
# ---------------------------------------------------------------------------
log ""
log "=== Hardening completado (13/13 pasos) ==="
log ""
log "SSH listo en puerto 2200. Verificar acceso con otra terminal antes de continuar:"
log "  ssh -p 2200 -i ~/.ssh/honeyml_ed25519 $ADMIN_USER@<IP>"
log "Siguiente: ejecutar 02_firewall.sh"
