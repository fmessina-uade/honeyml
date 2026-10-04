#!/usr/bin/env python3
"""Muestra un documento normalizado del índice, con las direcciones públicas enmascaradas.

Sirve para inspeccionar el esquema común por SSH y para capturarlo: imprime cada campo en notación
con puntos, ordenado, y enmascara los dos últimos octetos de toda dirección IPv4 pública que
aparezca, esté en el campo que esté. Las direcciones privadas de las redes de Docker quedan como
están. Sin dependencias externas, solo biblioteca estándar.

Se corre en el servidor, por ejemplo, con
`python3 ver_documento.py --sensor cowrie --accion login --resultado success --usuario root`.
Filtrar por un usuario conocido evita que salga uno que no se puede mostrar.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import re
import sys
import urllib.error
import urllib.request
from typing import Any

IPV4 = re.compile(r"(?<![\w.])(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})(?![\w.])")

# El texto crudo repite lo que ya está en los campos normalizados y alarga la salida sin agregar
# nada a lo que se quiere mostrar, que es el esquema.
OMITIDOS = ("event.original", "message", "log.", "agent.", "ecs.", "input.", "host.")


def enmascarar(texto: str) -> str:
    def reemplazo(m: re.Match[str]) -> str:
        try:
            ip = ipaddress.IPv4Address(m.group(0))
        except ipaddress.AddressValueError:
            return m.group(0)
        if ip.is_private or ip.is_loopback:
            return m.group(0)
        return f"{m.group(1)}.{m.group(2)}.x.x"

    return IPV4.sub(reemplazo, texto)


def aplanar(doc: Any, prefijo: str = "") -> dict[str, Any]:
    if isinstance(doc, dict):
        plano: dict[str, Any] = {}
        for clave, valor in doc.items():
            plano.update(aplanar(valor, f"{prefijo}{clave}."))
        return plano
    return {prefijo[:-1]: doc}


def main() -> int:
    ap = argparse.ArgumentParser(description="Un documento normalizado, enmascarado.")
    ap.add_argument("--es-url", default="http://localhost:9200")
    ap.add_argument("--sensor", choices=("cowrie", "dionaea"), required=True)
    ap.add_argument("--accion", required=True, help="event.action, por ejemplo login")
    ap.add_argument("--resultado", help="event.outcome, por ejemplo success")
    ap.add_argument("--usuario", help="user.name")
    ap.add_argument("--hasta", help="el más reciente hasta este instante ISO 8601")
    args = ap.parse_args()

    filtros: list[dict[str, Any]] = [{"term": {"event.action": args.accion}}]
    if args.resultado:
        filtros.append({"term": {"event.outcome": args.resultado}})
    if args.usuario:
        filtros.append({"term": {"user.name": args.usuario}})
    if args.hasta:
        filtros.append({"range": {"@timestamp": {"lte": args.hasta}}})
    body = {
        "size": 1,
        "sort": [{"@timestamp": "desc"}],
        "query": {
            "bool": {
                "filter": filtros,
                "must_not": [{"term": {"source.ip": "127.0.0.1"}}],
            }
        },
    }
    req = urllib.request.Request(
        f"{args.es_url.rstrip('/')}/honeypot-{args.sensor}-*/_search",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            hits = json.load(resp)["hits"]["hits"]
    except (urllib.error.URLError, OSError) as exc:
        print(f"No se pudo consultar Elasticsearch: {exc}")
        return 1
    if not hits:
        print("Ningún documento cumple esos filtros.")
        return 1

    print(f"Índice: {hits[0]['_index']}\n")
    plano = aplanar(hits[0]["_source"])
    ancho = max(len(c) for c in plano)
    for campo in sorted(plano):
        if campo.startswith(OMITIDOS):
            continue
        valor = plano[campo]
        texto = valor if isinstance(valor, str) else json.dumps(valor, ensure_ascii=False)
        print(f"  {campo:<{ancho}}  {enmascarar(texto)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
