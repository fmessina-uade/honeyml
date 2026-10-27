#!/bin/bash
# Prueba desde adentro de cada sensor las tres capas que contienen a quien logre tomar uno: no sale
# a internet, no llega al otro sensor y no llega al anfitrión. Antes muestra las reglas que lo
# hacen cumplir.
#
# Cada intento es una conexión TCP con tres segundos de espera. Quedarse sin respuesta quiere decir
# que el firewall descartó el paquete; un puerto alcanzable pero cerrado contestaría con un rechazo
# al instante. Por eso, para probar el anfitrión alcanza con un puerto donde no escucha nada, sin
# apuntar a ninguno de sus servicios.
#
# Se corre en el servidor con: sudo bash infra/vps/scripts/verificar_contencion.sh
# Sale con 1 si alguna conexión prospera.
#
# La sonda va escrita solo con caracteres ASCII porque el Python de la imagen de Dionaea corre con
# una configuración regional que no decodifica tildes en la línea de comandos.

set -euo pipefail

RED="honeypot_net"
PUERTO_DEL_ANFITRION=80

SONDA='import socket, sys
destinos = (
    ("internet", "1.1.1.1", 443),
    ("el otro sensor", sys.argv[1], int(sys.argv[2])),
    ("el anfitri\u00f3n", sys.argv[3], int(sys.argv[4])),
)
abiertas = 0
for nombre, ip, puerto in destinos:
    s = socket.socket()
    s.settimeout(3)
    try:
        s.connect((ip, puerto))
        resultado = "conecta"
        abiertas += 1
    except socket.timeout:
        resultado = "bloqueado, sin respuesta en 3 s"
    except ConnectionRefusedError:
        resultado = "llega: el puerto contesta con un rechazo"
        abiertas += 1
    except OSError as e:
        resultado = f"bloqueado, {e.strerror}"
    finally:
        s.close()
    destino = f"{ip}:{puerto}"
    print(f"  hacia {nombre:<15} {destino:<20} {resultado}")
sys.exit(1 if abiertas else 0)'

ip_de() {
    docker inspect -f "{{(index .NetworkSettings.Networks \"$RED\").IPAddress}}" "$1"
}

COWRIE=$(ip_de cowrie)
DIONAEA=$(ip_de dionaea)
PUERTA=$(docker network inspect -f '{{range .IPAM.Config}}{{.Gateway}}{{end}}' "$RED")

echo "Reglas de salida y entre sensores (cadena DOCKER-USER)"
iptables -S DOCKER-USER | sed 's/^/  /'
echo
echo "Regla hacia el anfitrión (UFW)"
ufw status | grep -i 'br-honeypot' | sed 's/^/  /'
echo

fallas=0
echo "Desde cowrie"
docker exec -e PYTHONIOENCODING=utf-8 cowrie python3 -c "$SONDA" "$DIONAEA" 445 "$PUERTA" "$PUERTO_DEL_ANFITRION" || fallas=1
echo
echo "Desde dionaea"
docker exec -e PYTHONIOENCODING=utf-8 dionaea python3 -c "$SONDA" "$COWRIE" 2222 "$PUERTA" "$PUERTO_DEL_ANFITRION" || fallas=1
echo

if [ "$fallas" -eq 0 ]; then
    echo "Contención verificada: ningún sensor sale a internet, alcanza al otro ni llega al anfitrión."
else
    echo "Hay conexiones que prosperan: revisar 02_firewall.sh y la red $RED."
fi
exit "$fallas"
