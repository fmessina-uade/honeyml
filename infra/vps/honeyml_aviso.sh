#!/usr/bin/env bash
# honeyml_aviso.sh: manda un mensaje al canal de Slack. Lo usan el chequeo de salud, el reporte
# diario, el vigilante y el instalador.
#
#     honeyml_aviso.sh --titulo "Reporte diario" --color "#00B894" --item "Contenedores" "8 de 8"
#
# La dirección del webhook se lee de un archivo que solo root puede leer, así no queda en los
# scripts ni en la lista de procesos. Con --una-por-hora el mismo aviso no se repite antes de una
# hora, porque el chequeo de salud corre cada cinco minutos.
#
# Sale con 0 si el mensaje llegó o se omitió por repetido, con 1 si no hay webhook y con 2 si el
# envío falló.

set -euo pipefail

WEBHOOK_FILE="/etc/honeyml/webhook"
ENVIADOS="/var/lib/honeyml/avisos"
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
# por si el archivo se editó a mano: una comilla rompería la configuración que lee curl
if [[ ! "$url" =~ $PATRON ]]; then
    echo "la dirección guardada en $WEBHOOK_FILE no es una dirección https válida"
    exit 2
fi
command -v jq >/dev/null || { echo "falta jq para armar el mensaje"; exit 2; }

# Cada ítem va en un bloque aparte para que Slack deje espacio entre las viñetas.
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
