"""La edición del corpus que se le puede entregar a alguien de afuera para reproducir el trabajo.

Sale de la telemetría normalizada, sin los orígenes internos, y con tres reglas. La dirección de
origen se reemplaza por un seudónimo hecho con HMAC y una clave privada del proyecto: un hash sin
clave no alcanza, porque las direcciones IPv4 son pocas y se pueden probar todas. Un usuario o una
contraseña solo queda si lo probaron al menos cinco direcciones distintas, con la misma regla que
el panel. Y en cualquier texto se tapan las direcciones, el host de las URL y los dominios con ruta,
y también las direcciones escondidas en base64 o en escapes hexadecimales.

Los campos salen de una lista blanca y no de una lista de lo que se saca: un campo nuevo en el
índice no puede aparecer en la edición sin que alguien lo agregue a propósito. Quedan afuera, entre
otros, la dirección del propio servidor, el mensaje crudo (trae la contraseña de cada intento), las
coordenadas y la ciudad.

Se corre en el servidor con `make corpus-publico`. Escribe un NDJSON comprimido y un manifiesto con
las reglas aplicadas, la licencia y la huella del archivo; con `--seco` solo cuenta.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import hmac
import json
import os
import sys
import urllib.request
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import redes
from .api import privacidad, queries

# Los campos de la edición. La dirección de origen entra para convertirse en seudónimo y sale con
# otro nombre, así nadie la confunde con una dirección.
CAMPOS = (
    "@timestamp",
    "honeypot",
    "event.dataset",
    "event.kind",
    "event.category",
    "event.type",
    "event.action",
    "event.outcome",
    "event.duration",
    "network.protocol",
    "network.transport",
    "source.ip",
    "source.port",
    "source.geo.continent_code",
    "source.geo.country_iso_code",
    "source.geo.country_name",
    "source.as.number",
    "source.as.organization.name",
    "destination.port",
    "user.name",
    "cowrie.password",
    "cowrie.session",
    "cowrie.client_version",
    "cowrie.hassh",
    "cowrie.duration_seconds",
    "process.command_line",
    "url.original",
    "file.name",
    "file.hash.sha256",
)
SEUDONIMO = "source.seudonimo"

# Continente, país y sistema autónomo salen de las bases GeoLite2 de MaxMind, que tienen licencia
# CC BY-SA 4.0: la edición que los lleva hereda la licencia y la obligación de atribuir. El
# manifiesto viaja con el archivo, así que las dos van ahí.
LICENCIA = {
    "nombre": "CC BY-SA 4.0",
    "texto": "https://creativecommons.org/licenses/by-sa/4.0/",
    "atribucion": (
        "Incluye datos de GeoLite2 creados por MaxMind, disponibles en https://www.maxmind.com"
    ),
}

VARIABLE_DE_CLAVE = "CORPUS_CLAVE"
# Una clave corta se adivina tan fácil como un hash sin clave.
LARGO_MINIMO_DE_CLAVE = 32
SALIDA = Path("data/processed/corpus_publico")
PAGINA = 5000


class ClaveAusenteError(RuntimeError):
    pass


def clave_del_entorno() -> bytes:
    clave = os.getenv(VARIABLE_DE_CLAVE) or ""
    if len(clave) < LARGO_MINIMO_DE_CLAVE:
        raise ClaveAusenteError(
            f"Falta {VARIABLE_DE_CLAVE} en el entorno, o es más corta que "
            f"{LARGO_MINIMO_DE_CLAVE} caracteres. Se genera con `openssl rand -hex 32` y va en el "
            ".env del servidor; no se publica nunca."
        )
    return clave.encode()


def seudonimo(ip: str, clave: bytes) -> str:
    """El mismo apodo para la misma dirección dentro de una edición, sin forma de volver atrás."""
    return "origen-" + hmac.new(clave, ip.encode(), hashlib.sha256).hexdigest()[:16]


def consulta(desde: str | None, hasta: str | None) -> dict[str, Any]:
    rango = {k: v for k, v in (("gte", desde), ("lte", hasta)) if v}
    filtro = [{"range": {"@timestamp": rango}}] if rango else []
    return {"bool": {"must_not": redes.TERMINOS, "filter": filtro}}


def _plano(fuente: dict[str, Any], prefijo: str = "") -> dict[str, Any]:
    plano: dict[str, Any] = {}
    for clave, valor in fuente.items():
        nombre = f"{prefijo}{clave}"
        if isinstance(valor, dict):
            plano |= _plano(valor, f"{nombre}.")
        else:
            plano[nombre] = valor
    return plano


def credenciales_que_quedan(campo: str, cuerpo_consulta: dict[str, Any]) -> set[str]:
    """Todos los valores del campo que pasan la regla de `privacidad`, recorridos de a páginas.

    No alcanza con las más probadas: un evento con una credencial poco común tiene que poder
    decirse si la conserva o la tapa, así que se recorren todas.
    """
    quedan: set[str] = set()
    despues: dict[str, Any] | None = None
    while True:
        compuesta: dict[str, Any] = {
            "size": PAGINA,
            "sources": [{"v": {"terms": {"field": campo}}}],
        }
        if despues:
            compuesta["after"] = despues
        cuerpo = {
            "size": 0,
            "query": cuerpo_consulta,
            "aggs": {"c": {"composite": compuesta, "aggs": {"origenes": queries._ORIGENES}}},
        }
        r = queries._search(cuerpo)["aggregations"]["c"]
        cubos = [
            {"key": b["key"]["v"], "count": b["doc_count"], "origenes": b["origenes"]["value"]}
            for b in r["buckets"]
        ]
        quedan |= {c["key"] for c in privacidad.credenciales_frecuentes(cubos)}
        despues = r.get("after_key")
        if not r["buckets"] or not despues:
            return quedan


def documento_publico(
    fuente: dict[str, Any], clave: bytes, usuarios: set[str], contrasenas: set[str]
) -> dict[str, Any]:
    """Un evento tal como sale en la edición: lista blanca, seudónimo, credenciales y tapado."""
    plano = _plano(fuente)
    salida = {campo: plano[campo] for campo in CAMPOS if plano.get(campo) is not None}
    ip = salida.pop("source.ip", None)
    if ip:
        salida[SEUDONIMO] = seudonimo(str(ip), clave)
    if "user.name" in salida and salida["user.name"] not in usuarios:
        salida["user.name"] = privacidad.CREDENCIAL_TAPADA
    if "cowrie.password" in salida and salida["cowrie.password"] not in contrasenas:
        salida["cowrie.password"] = privacidad.CREDENCIAL_TAPADA
    publico: dict[str, Any] = privacidad.sin_direcciones(salida)
    return publico


def _pedir(ruta: str, cuerpo: dict[str, Any], metodo: str = "POST") -> dict[str, Any]:
    pedido = urllib.request.Request(
        f"{queries.ES_URL}{ruta}",
        data=json.dumps(cuerpo).encode(),
        headers={"Content-Type": "application/json"},
        method=metodo,
    )
    with urllib.request.urlopen(pedido, timeout=120) as resp:
        resultado: dict[str, Any] = json.load(resp)
        return resultado


def eventos(cuerpo_consulta: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Los eventos de la ventana, en orden de llegada, de a páginas."""
    cuerpo = {
        "size": PAGINA,
        "query": cuerpo_consulta,
        "_source": list(CAMPOS),
        "sort": [{"@timestamp": "asc"}, "_doc"],
    }
    r = _pedir(f"/{queries.INDEX}/_search?scroll=5m", cuerpo)
    scroll = r.get("_scroll_id")
    try:
        while r["hits"]["hits"]:
            for h in r["hits"]["hits"]:
                yield h["_source"]
            r = _pedir("/_search/scroll", {"scroll": "5m", "scroll_id": scroll})
            scroll = r.get("_scroll_id")
    finally:
        if scroll:
            try:
                _pedir("/_search/scroll", {"scroll_id": scroll}, metodo="DELETE")
            except OSError:
                pass


def _huella(archivo: Path) -> str:
    h = hashlib.sha256()
    with archivo.open("rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description="Edición del corpus para entregar afuera.")
    ap.add_argument("--desde", default=None, help="momento inicial, ISO; por defecto, el primero")
    ap.add_argument("--hasta", default=None, help="momento final, ISO; por defecto, el último")
    ap.add_argument("--seco", action="store_true", help="solo cuenta, sin escribir nada")
    args = ap.parse_args()

    try:
        clave = clave_del_entorno()
    except ClaveAusenteError as exc:
        print(f"  {exc}")
        return 1

    filtro = consulta(args.desde, args.hasta)
    total = queries._search({"size": 0, "track_total_hits": True, "query": filtro})["hits"][
        "total"
    ]["value"]
    usuarios = credenciales_que_quedan("user.name", filtro)
    contrasenas = credenciales_que_quedan("cowrie.password", filtro)
    print(f"  eventos de la ventana: {total:,}".replace(",", "."))
    print(f"  usuarios que quedan: {len(usuarios)}   contraseñas que quedan: {len(contrasenas)}")
    if args.seco:
        return 0

    SALIDA.mkdir(parents=True, exist_ok=True)
    nombre = f"honeyml_corpus_{(args.desde or 'inicio')[:10]}_{(args.hasta or 'fin')[:10]}"
    archivo = SALIDA / f"{nombre}.ndjson.gz"
    escritos = 0
    with gzip.open(archivo, "wt", encoding="utf-8") as salida:
        for fuente in eventos(filtro):
            publico = documento_publico(fuente, clave, usuarios, contrasenas)
            salida.write(json.dumps(publico, ensure_ascii=False) + "\n")
            escritos += 1
            if escritos % 500_000 == 0:
                print(f"  {escritos:,}".replace(",", "."))

    manifiesto = {
        "generado": datetime.now(UTC).isoformat(timespec="seconds"),
        "ventana": {"desde": args.desde, "hasta": args.hasta},
        "eventos": escritos,
        "archivo": archivo.name,
        "sha256": _huella(archivo),
        "campos": [SEUDONIMO if c == "source.ip" else c for c in CAMPOS],
        "licencia": LICENCIA,
        "reglas": {
            "seudonimo": (
                "HMAC-SHA256 de la dirección de origen con una clave privada del proyecto, "
                "16 hexadecimales: la misma dirección da el mismo seudónimo dentro de la edición"
            ),
            "credenciales": (
                f"un usuario o una contraseña queda solo si lo probaron al menos "
                f"{privacidad.MINIMO_DE_ORIGENES} direcciones distintas; si no, "
                f"'{privacidad.CREDENCIAL_TAPADA}'"
            ),
            "textos": (
                "direcciones IPv4, host de las URL y dominios con ruta, tapados; las direcciones "
                "también dentro de bloques en base64 o en escapes hexadecimales"
            ),
            "afuera": "orígenes internos, la dirección del servidor, el mensaje crudo, ciudad, "
            "región y coordenadas",
        },
    }
    (SALIDA / f"{nombre}.manifiesto.json").write_text(
        json.dumps(manifiesto, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  {escritos:,} eventos en {archivo}".replace(",", "."))
    if escritos != total:
        print(f"  La ventana tenía {total} eventos y se escribieron {escritos}.")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
