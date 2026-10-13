#!/usr/bin/env bash
# honeyml_purga_muestras.sh: borra las muestras de malware que Cowrie guardó hace más de siete días.
# Lo corre cron una vez por día.
#
# Cowrie guarda en su volumen de descargas el archivo que un atacante sube o intenta bajar. Es el
# único dato del corpus que pesa frente a la política del proveedor, y para el análisis no hace
# falta conservarlo: el SHA-256 del archivo ya queda en el evento, así que se puede seguir contando
# y correlacionando sin el binario. La decisión D2 de `docs/TRATAMIENTO_DE_DATOS.md` fija el plazo
# en siete días.
#
# No toca el evento ni el índice: solo el archivo en disco. Un borrado de más no pierde nada que no
# esté en el evento.
set -euo pipefail

# El volumen de descargas de Cowrie, en el disco del anfitrión. El nombre lo fija el compose de los
# sensores (`honeypots_cowrie_downloads`).
VOLUMEN="${COWRIE_DOWNLOADS:-/var/lib/docker/volumes/honeypots_cowrie_downloads/_data}"
DIAS="${RETENCION_MUESTRAS_DIAS:-7}"

if [ ! -d "$VOLUMEN" ]; then
    echo "No está el volumen de descargas: $VOLUMEN" >&2
    exit 0
fi

borradas=$(find "$VOLUMEN" -type f -mtime "+$DIAS" -print -delete 2>/dev/null | wc -l)
echo "$(date -u +%FT%TZ) muestras borradas (más de $DIAS días): $borradas"
