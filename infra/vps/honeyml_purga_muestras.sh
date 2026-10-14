#!/usr/bin/env bash
# honeyml_purga_muestras.sh: borra las muestras de malware que los sensores guardaron hace más de
# siete días. Lo corre cron una vez por día; con SECO=1 solo cuenta lo que borraría.
#
# Cowrie guarda en su volumen de descargas el archivo que un atacante sube o intenta bajar, y Dionaea
# guarda en su carpeta de binarios lo que le ofrecen sus servicios. Son el único dato del corpus que
# pesa frente a la política del proveedor de la nube, y para el análisis no hace falta el binario: lo
# que identifica a una muestra es su hash. Los dos sensores nombran cada archivo por su hash (SHA-256
# en Cowrie, MD5 en Dionaea), y antes de borrarlo el nombre queda anotado en un registro aparte. En
# Cowrie el hash además está en el evento; en Dionaea el pipeline no indexa las descargas, y ese
# registro es lo que lo conserva.
#
# No toca los eventos ni el índice: solo los archivos en disco.
set -euo pipefail

# Las carpetas de muestras en el disco del anfitrión. Los volúmenes los nombra el compose de los
# sensores; la ruta dentro del de Dionaea sale de su `download.dir`.
COWRIE="${COWRIE_DOWNLOADS:-/var/lib/docker/volumes/honeypots_cowrie_downloads/_data}"
DIONAEA="${DIONAEA_BINARIOS:-/var/lib/docker/volumes/honeypots_dionaea_var/_data/lib/dionaea/binaries}"
DIAS="${RETENCION_MUESTRAS_DIAS:-7}"
# Un renglón por muestra borrada: momento, sensor y nombre del archivo, que es su hash.
BORRADAS="${REGISTRO_BORRADAS:-/var/log/honeyml_muestras_borradas.log}"

trabajo=$(mktemp -d)
trap 'rm -rf "$trabajo"' EXIT

# Cuántas muestras tenía la última carpeta purgada. Va en una variable y no por la salida de la
# función porque dentro de `$(...)` no rige `set -e`, y un registro que no se pudo escribir dejaría
# seguir el borrado.
contadas=0

purgar() {
    local sensor="$1" carpeta="$2" lista="$trabajo/$1"
    contadas=0
    # Sin la carpeta no hay nada que borrar, pero se avisa: una ruta mal escrita dejaría la purga
    # contando cero para siempre sin que nadie lo note.
    if [ ! -d "$carpeta" ]; then
        echo "No está la carpeta de muestras de $sensor: $carpeta" >&2
        return
    fi
    find "$carpeta" -type f -mtime "+$DIAS" -print0 > "$lista"
    contadas=$(tr -cd '\0' < "$lista" | wc -c | tr -d ' ')
    if [ -n "${SECO:-}" ]; then
        return
    fi
    # Primero se anota y después se borra: si el registro no se puede escribir, el script corta
    # antes de borrar nada.
    tr '\0' '\n' < "$lista" \
        | awk -v momento="$(date -u +%FT%TZ)" -v sensor="$sensor" \
            '{ n = split($0, partes, "/"); print momento, sensor, partes[n] }' >> "$BORRADAS"
    xargs -0 -r rm -f < "$lista"
}

purgar cowrie "$COWRIE"
cowrie=$contadas
purgar dionaea "$DIONAEA"
dionaea=$contadas
accion="borradas"
if [ -n "${SECO:-}" ]; then
    accion="a borrar, sin borrar nada"
fi
echo "$(date -u +%FT%TZ) muestras $accion (más de $DIAS días): cowrie $cowrie, dionaea $dionaea"
