#!/usr/bin/env bash
# honeyml_aviso.sh: manda un mensaje al canal de avisos. Lo usan el chequeo de salud, el reporte
# diario, el vigilante y el instalador.
#
#     honeyml_aviso.sh --titulo "Reporte diario" --color "#00B894" --resumen "Todo en orden" \
#         --item "Contenedores" "8 de 8 en marcha" --linea "texto suelto"
#
# --item y --linea se repiten las veces que haga falta. El mensaje lleva un encabezado, una franja
# con la escala de severidad del panel (teal cuando todo anda, ámbar para revisar, coral para lo
# crítico) y una lista con el título de cada ítem en negrita y subrayado. Ese formato y las viñetas
# salen de los bloques de Slack, así que el texto no lleva marcas. La notificación del teléfono
# muestra solo el texto de respaldo, y por eso empieza por el resumen.
#
# --una-por-hora clave es para lo que persiste: el chequeo de salud corre cada cinco minutos y no
# recuerda lo que ya avisó. En la clave los dígitos no cuentan: "disco al 81%" y "disco al 82%" son
# el mismo aviso. La dirección del webhook vive en un archivo que solo root lee, y nunca va como
# argumento de un proceso ni sale por la salida de este script, que termina en registros del panel.
#
# Sale con 0 si el canal aceptó el mensaje o si se omitió por repetido, con 1 si no hay webhook
# configurado y con 2 si el envío falló; en ese caso imprime el código y la respuesta.

set -euo pipefail

WEBHOOK_FILE="/etc/honeyml/webhook"
ENVIADOS="/var/lib/honeyml/avisos"
# el mismo patrón con que el instalador valida la dirección antes de guardarla
PATRON='^https://[A-Za-z0-9._~:/?#@!$&+,;=%-]+$'

archivo_clave="" titulo="" color="" resumen=""
partes=()
while (( $# > 0 )); do
    case "$1" in
        --una-por-hora)
            clave=$(printf '%s' "${2:-}" | tr '0-9' 'N' | sha256sum | cut -c1-16)
            archivo_clave="$ENVIADOS/$clave"
            shift 2 ;;
        --titulo) titulo="$2"; shift 2 ;;
        --color) color="$2"; shift 2 ;;
        --resumen) resumen="$2"; shift 2 ;;
        --item) partes+=("item" "$2" "$3"); shift 3 ;;
        --linea) partes+=("linea" "$2" ""); shift 2 ;;
        *) partes+=("linea" "$1" ""); shift ;;
    esac
done

if [[ -n "$archivo_clave" && -n "$(find "$archivo_clave" -mmin -60 2>/dev/null)" ]]; then
    exit 0
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
command -v jq >/dev/null || { echo "falta jq para armar el mensaje"; exit 2; }

# jq arma el JSON y escapa cada valor, así que ningún texto rompe la carga. Las partes llegan en
# tríos (tipo, texto, valor): un ítem es una viñeta con el título destacado, y una línea es un
# párrafo suelto, que es lo que usan las alertas. Cada valor termina en punto. Cada ítem va en su
# propio bloque porque Slack separa los bloques con aire y no tiene una opción de espaciado dentro
# de una lista: un salto al final del valor lo descarta, y un ítem vacío dibujaría otra viñeta.
carga=$(jq -n --arg titulo "$titulo" --arg color "${color:-#94A3B8}" --arg resumen "$resumen" '
    def punto: if test("[.!?]$") then . else . + "." end;
    $ARGS.positional as $p
    | [range(0; $p | length; 3) as $i | {tipo: $p[$i], a: $p[$i + 1], b: $p[$i + 2]}] as $partes
    | [$partes[] | select(.tipo == "item") | {type: "rich_text", elements: [
        {type: "rich_text_list", style: "bullet", elements: [{type: "rich_text_section", elements: [
            {type: "text", text: (.a + ":"), style: {bold: true, underline: true}},
            {type: "text", text: (" " + (.b | punto))}]}]}]}] as $items
    | [$partes[] | select(.tipo == "linea") | {type: "rich_text_section", elements: [
        {type: "text", text: (.a | punto)}]}] as $lineas
    | ([($resumen | if . == "" then . else punto end), $titulo] | map(select(. != "")) | first // "") as $primera
    | ([$partes[] | if .tipo == "item" then .a + ": " + (.b | punto) else (.a | punto) end]
        | map(select(. != $primera)) | join("\n")) as $cuerpo
    | {text: ([$primera, $cuerpo] | map(select(. != "")) | join("\n")),
       blocks: (if $titulo == "" then [] else [{type: "header", text: {type: "plain_text", text: $titulo}}] end),
       attachments: [{color: $color, blocks: (
           (if ($lineas | length) > 0 then [{type: "rich_text", elements: $lineas}] else [] end) + $items
       )}]}' --args "${partes[@]}")

respuesta=$(printf '%s' "$carga" | curl -s --proto =https --max-time 15 \
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
