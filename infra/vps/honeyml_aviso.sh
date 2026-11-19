#!/usr/bin/env bash
# honeyml_aviso.sh: manda un mensaje al canal de avisos. Lo usan el chequeo de salud, el reporte
# diario y el vigilante, y cada argumento es una línea del mensaje.
#
#     honeyml_aviso.sh "línea" "otra línea"                   lo manda siempre
#     honeyml_aviso.sh --una-por-hora clave "línea"           no repite la clave antes de una hora
#
# La segunda forma es para las condiciones que persisten. El chequeo de salud corre cada cinco
# minutos y no guarda nada entre una corrida y otra, así que un contenedor frenado llegaría al canal
# doce veces por hora. En la clave los dígitos no cuentan: "disco al 81%" y "disco al 82%" son el
# mismo aviso.
#
# La dirección del webhook vive en un archivo que solo root puede leer, y no adentro de los scripts:
# con la dirección cualquiera publica en el canal, y lo que está en /usr/local/bin lo lee cualquier
# usuario del servidor. Por lo mismo, a curl le llega por un descriptor y no como argumento, que
# aparece en la lista de procesos. Este script nunca la imprime, porque quien lo llama escribe su
# salida en registros que el panel muestra.
#
# Sale con 0 si el canal aceptó el mensaje o si se omitió por repetido, con 1 si no hay webhook
# configurado y con 2 si el envío falló. En el último caso imprime el código y la respuesta del canal.

set -euo pipefail

WEBHOOK_FILE="/etc/honeyml/webhook"
ENVIADOS="/var/lib/honeyml/avisos"
# el mismo patrón con que el instalador valida la dirección antes de guardarla
PATRON='^https://[A-Za-z0-9._~:/?#@!$&+,;=%-]+$'

archivo_clave=""
if [[ "${1:-}" == "--una-por-hora" ]]; then
    clave=$(printf '%s' "${2:-}" | tr '0-9' 'N' | sha256sum | cut -c1-16)
    archivo_clave="$ENVIADOS/$clave"
    shift 2
    if [[ -n "$(find "$archivo_clave" -mmin -60 2>/dev/null)" ]]; then
        exit 0
    fi
fi

[[ -r "$WEBHOOK_FILE" ]] || exit 1
url=""
read -r url < "$WEBHOOK_FILE" || true
[[ -n "$url" ]] || exit 1
# Un archivo editado a mano no pasó por la validación del instalador. Una comilla rompería la línea
# de configuración que recibe curl, y otro esquema mandaría el aviso sin cifrar.
if [[ ! "$url" =~ $PATRON ]]; then
    echo "la dirección guardada en $WEBHOOK_FILE no es una dirección https válida"
    exit 2
fi

texto=$(printf '%s\n' "$@")
# Dentro de una cadena JSON no pueden ir tal cual la barra invertida, la comilla ni los caracteres
# de control. Los mensajes los arma el propio servidor, pero llevan nombres de contenedores, de
# discos y respuestas de otros servicios que este script no controla.
texto=${texto//\\/\\\\}
texto=${texto//\"/\\\"}
texto=${texto//$'\n'/\\n}
texto=${texto//$'\r'/}
texto=${texto//$'\t'/ }

respuesta=$(printf '{"text":"%s"}' "$texto" | curl -s --proto =https --max-time 15 \
    -w '\n%{http_code}' -X POST -H 'Content-Type: application/json' --data-binary @- \
    -K <(printf 'url = "%s"\n' "$url") 2>/dev/null) || true
codigo=${respuesta##*$'\n'}
cuerpo=${respuesta%$'\n'*}
cuerpo=${cuerpo//$'\n'/ }

# Slack contesta 200 y Discord 204: cualquier 2xx es un mensaje aceptado.
if [[ "$codigo" =~ ^2[0-9][0-9]$ ]]; then
    # se anota solo lo que llegó, para que un envío fallido se reintente en la corrida siguiente
    if [[ -n "$archivo_clave" ]]; then
        { mkdir -p "$ENVIADOS" && chmod 700 "$ENVIADOS" && touch "$archivo_clave"; } 2>/dev/null || true
    fi
    exit 0
fi
echo "código ${codigo:-sin respuesta}${cuerpo:+, ${cuerpo:0:120}}"
exit 2
