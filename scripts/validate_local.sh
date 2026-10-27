#!/bin/bash
# validate_local.sh: chequeo local del stack de HoneyML antes de desplegar.
# Se corre antes de subir al VPS, para agarrar lo que se rompe de forma obvia.
#
# Uso: bash scripts/validate_local.sh

set -euo pipefail

COMPOSE_FILE="infra/honeypots/docker-compose.yml"
COMPOSE_DEV="infra/honeypots/docker-compose.dev.yml"
PASS=0
FAIL=0

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

ok()   { echo -e "${GREEN}  bien ${NC} $*"; ((PASS++)) || true; }
fail() { echo -e "${RED}  falla${NC} $*"; ((FAIL++)) || true; }
info() { echo -e "${YELLOW}  aviso${NC} $*"; }

cd "$(git rev-parse --show-toplevel 2>/dev/null || echo '.')"

echo ""
echo "HoneyML, validación local antes de desplegar"
echo ""

echo "[ 1 ] Dependencias del sistema"

if command -v docker &>/dev/null; then
    ok "Docker instalado: $(docker --version | cut -d' ' -f3 | tr -d ',')"
else
    fail "Docker no encontrado. Instalar Docker Desktop."
fi

if docker compose version &>/dev/null 2>&1; then
    ok "Docker Compose V2 disponible"
else
    fail "Docker Compose V2 no disponible. Usar Docker Desktop >= 3.6"
fi

command -v python3 &>/dev/null && ok "python3: $(python3 --version)" || info "python3 no encontrado (lo necesita el pipeline de datos)"
command -v shellcheck &>/dev/null && ok "shellcheck disponible" || info "shellcheck no encontrado. Se instala con: brew install shellcheck"

echo ""
echo "[ 2 ] Linting de scripts de shell"

if command -v shellcheck &>/dev/null; then
    for script in infra/vps/scripts/*.sh scripts/validate_local.sh; do
        if bash -n "$script" 2>/dev/null; then
            ok "Sintaxis bash OK: $script"
        else
            fail "Error de sintaxis: $script"
        fi
    done
else
    info "shellcheck no disponible: solo se valida la sintaxis de bash"
    for script in infra/vps/scripts/*.sh; do
        if bash -n "$script" 2>/dev/null; then
            ok "Sintaxis bash OK: $script"
        else
            fail "Error de sintaxis: $script"
        fi
    done
fi

echo ""
echo "[ 3 ] Validación de Docker Compose"

if docker compose -f "$COMPOSE_FILE" config --quiet 2>/dev/null; then
    ok "docker-compose.yml: YAML válido"
else
    fail "docker-compose.yml inválido:"
    docker compose -f "$COMPOSE_FILE" config 2>&1 | sed 's/^/     /'
fi

if docker compose -f "$COMPOSE_FILE" -f "$COMPOSE_DEV" config --quiet 2>/dev/null; then
    ok "docker-compose.dev.yml: merge con base válido"
else
    fail "docker-compose.dev.yml: merge inválido"
fi

echo ""
echo "[ 4 ] Archivos de configuración de honeypots"

REQUIRED_FILES=(
    "infra/honeypots/cowrie/cowrie.cfg"
    "infra/honeypots/cowrie/userdb.txt"
    "infra/honeypots/dionaea/Dockerfile"
    "infra/honeypots/dionaea/dionaea.cfg"
    "infra/vps/scripts/01_hardening.sh"
    "infra/vps/scripts/02_firewall.sh"
    "infra/vps/scripts/03_monitoring.sh"
    "infra/vps/configs/sshd_config"
    "docs/DECISIONES_TECNICAS.md"
)

for f in "${REQUIRED_FILES[@]}"; do
    [[ -f "$f" ]] && ok "Existe: $f" || fail "Falta: $f"
done

echo ""
echo "[ 5 ] Validación de cowrie.cfg (paths internos correctos)"

COWRIE_CFG="infra/honeypots/cowrie/cowrie.cfg"

# rutas que la imagen de Cowrie espera encontrar
if grep -q "^contents_path = honeyfs" "$COWRIE_CFG"; then
    ok "cowrie.cfg: contents_path = honeyfs (directorio real en la imagen)"
else
    fail "cowrie.cfg: contents_path incorrecto, tiene que ser 'honeyfs' (no share/cowrie/txtcmds)"
fi

if grep -q "^txtcmds_path = src/cowrie/data/txtcmds" "$COWRIE_CFG"; then
    ok "cowrie.cfg: txtcmds_path = src/cowrie/data/txtcmds"
else
    fail "cowrie.cfg: txtcmds_path incorrecto, tiene que ser 'src/cowrie/data/txtcmds'"
fi

if grep -q "^auth_class = UserDB" "$COWRIE_CFG"; then
    ok "cowrie.cfg: auth_class = UserDB"
else
    fail "cowrie.cfg: auth_class faltante o incorrecto"
fi

# los volúmenes del docker-compose.yml tienen que usar el CWD real del contenedor
if grep -q "/cowrie/cowrie-git/etc/cowrie.cfg" "$COMPOSE_FILE"; then
    ok "docker-compose.yml: volume cowrie.cfg apunta a /cowrie/cowrie-git/etc/"
else
    fail "docker-compose.yml: volume cowrie.cfg no usa /cowrie/cowrie-git/ (CWD real de la imagen)"
fi

if grep -q "/cowrie/cowrie-git/etc/userdb.txt" "$COMPOSE_FILE"; then
    ok "docker-compose.yml: volume userdb.txt apunta a /cowrie/cowrie-git/etc/"
else
    fail "docker-compose.yml: volume userdb.txt no usa /cowrie/cowrie-git/"
fi

echo ""
echo "[ 6 ] Validación de userdb.txt (formato y encoding)"

USERDB="infra/honeypots/cowrie/userdb.txt"

# solo ASCII: Cowrie abre el archivo sin encoding=, así que usa ascii por defecto
if python3 -c "
import sys
with open('$USERDB', 'rb') as f:
    data = f.read()
bad = [(i, b) for i, b in enumerate(data) if b > 127]
if bad:
    print(f'Byte no-ASCII 0x{bad[0][1]:02x} en posición {bad[0][0]}')
    sys.exit(1)
" 2>/dev/null; then
    ok "userdb.txt: encoding ASCII puro (sin ñ, tildes ni guiones tipográficos)"
else
    fail "userdb.txt: contiene bytes no-ASCII - Cowrie fallará con UnicodeDecodeError"
    info "  Causa probable: comentarios con ñ, tildes, em-dash u otros UTF-8"
fi

# formato usuario:x:contraseña (el campo 2 es 'x', no un UID numérico)
BAD_FORMAT=$(grep -v "^#" "$USERDB" | grep -v "^$" | grep -v "^[^:]*:x:" || true)
if [[ -z "$BAD_FORMAT" ]]; then
    ok "userdb.txt: formato usuario:x:password correcto"
else
    fail "userdb.txt: entradas con campo 2 incorrecto (debe ser 'x', no UID numérico):"
    echo "$BAD_FORMAT" | sed 's/^/     /'
fi

# sin contraseñas vacías, que provocan un IndexError en auth.py
EMPTY_PASS=$(grep -v "^#" "$USERDB" | grep -v "^$" | grep ":$" || true)
if [[ -z "$EMPTY_PASS" ]]; then
    ok "userdb.txt: sin contraseñas vacías (evita IndexError en auth.py)"
else
    fail "userdb.txt: entradas con contraseña vacía, que hacen fallar a Cowrie con IndexError:"
    echo "$EMPTY_PASS" | sed 's/^/     /'
fi

ENTRY_COUNT=$(grep -v "^#" "$USERDB" | grep -v "^$" | wc -l | tr -d ' ')
ok "userdb.txt: $ENTRY_COUNT entradas de credenciales"

echo ""
echo "[ 7 ] .gitignore: datos sensibles excluidos"

SENSITIVE_PATTERNS=("*.pkl" "*.pem" "*.key" "*.pcap" "*.malware" ".env" "id_rsa" "*.joblib")
for pattern in "${SENSITIVE_PATTERNS[@]}"; do
    grep -q "$pattern" .gitignore 2>/dev/null \
        && ok ".gitignore cubre: $pattern" \
        || fail ".gitignore no cubre: $pattern"
done

echo ""
echo "[ 8 ] Pruebas de humo: contenedores y conectividad"

info "Iniciando contenedores en modo de desarrollo..."
docker compose -f "$COMPOSE_FILE" -f "$COMPOSE_DEV" up -d 2>/dev/null
ok "docker compose up sin errores"
sleep 6

COWRIE_STATUS=$(docker inspect --format='{{.State.Status}}' cowrie 2>/dev/null || echo "no encontrado")
[[ "$COWRIE_STATUS" == "running" ]] \
    && ok "Cowrie: running" \
    || fail "Cowrie: $COWRIE_STATUS"

DIONAEA_STATUS=$(docker inspect --format='{{.State.Status}}' dionaea 2>/dev/null || echo "no encontrado")
[[ "$DIONAEA_STATUS" == "running" ]] \
    && ok "Dionaea: running" \
    || fail "Dionaea: $DIONAEA_STATUS"

SUBNET=$(docker network inspect honeypot_net --format='{{range .IPAM.Config}}{{.Subnet}}{{end}}' 2>/dev/null || echo "")
[[ -n "$SUBNET" ]] \
    && ok "Red honeypot_net: $SUBNET" \
    || fail "Red honeypot_net no encontrada"

sleep 4

# Cowrie SSH (puerto 2222 en desarrollo)
if nc -z -w5 127.0.0.1 2222 2>/dev/null; then
    ok "Cowrie SSH responde en localhost:2222"
else
    fail "Cowrie SSH no responde en localhost:2222"
fi

# Cowrie Telnet (puerto 2323 en desarrollo)
if nc -z -w5 127.0.0.1 2323 2>/dev/null; then
    ok "Cowrie Telnet responde en localhost:2323"
else
    fail "Cowrie Telnet no responde en localhost:2323"
fi

# Dionaea HTTP (puerto 8080 en desarrollo)
if nc -z -w5 127.0.0.1 8080 2>/dev/null; then
    ok "Dionaea HTTP responde en localhost:8080"
else
    fail "Dionaea HTTP no responde en localhost:8080"
fi

# Dionaea SMB (puerto 4445 en desarrollo)
if nc -z -w5 127.0.0.1 4445 2>/dev/null; then
    ok "Dionaea SMB responde en localhost:4445"
else
    fail "Dionaea SMB no responde en localhost:4445"
fi

# prueba real de autenticación SSH con credenciales débiles
if command -v sshpass &>/dev/null; then
    if sshpass -p 'root' ssh \
        -o StrictHostKeyChecking=no \
        -o PubkeyAuthentication=no \
        -o ConnectTimeout=5 \
        -p 2222 root@127.0.0.1 'exit 0' 2>/dev/null; then
        ok "Cowrie: autenticación SSH con root:root exitosa"
    else
        fail "Cowrie: autenticación SSH con root:root falló"
    fi
else
    info "sshpass no disponible: se saltea la prueba de autenticación SSH (brew install hudochenkov/sshpass/sshpass)"
fi

# contenido HTTP de Dionaea
HTTP_RESP=$(curl -s --connect-timeout 5 http://127.0.0.1:8080/ 2>/dev/null || echo "")
if echo "$HTTP_RESP" | grep -q "Directory listing"; then
    ok "Dionaea HTTP: responde con directory listing"
else
    fail "Dionaea HTTP: respuesta inesperada"
fi

# restart count = 0 (no crashes)
COWRIE_RESTARTS=$(docker inspect --format='{{.RestartCount}}' cowrie 2>/dev/null || echo "?")
DIONAEA_RESTARTS=$(docker inspect --format='{{.RestartCount}}' dionaea 2>/dev/null || echo "?")
[[ "$COWRIE_RESTARTS" == "0" ]] \
    && ok "Cowrie: 0 reinicios (estable)" \
    || fail "Cowrie: $COWRIE_RESTARTS reinicios detectados"
[[ "$DIONAEA_RESTARTS" == "0" ]] \
    && ok "Dionaea: 0 reinicios (estable)" \
    || fail "Dionaea: $DIONAEA_RESTARTS reinicios detectados"

info "Deteniendo contenedores de prueba..."
docker compose -f "$COMPOSE_FILE" -f "$COMPOSE_DEV" down --remove-orphans -v 2>/dev/null
ok "Contenedores detenidos y volúmenes de prueba eliminados"

echo ""
printf "Resultado: %s bien y %s con falla\n" "$PASS" "$FAIL"
echo ""

if [[ $FAIL -gt 0 ]]; then
    echo -e "${RED}Hay $FAIL error(es) que corregir antes de desplegar en el VPS.${NC}"
    exit 1
else
    echo -e "${GREEN}Todo en orden. El stack está listo para desplegar en el VPS.${NC}"
    exit 0
fi
