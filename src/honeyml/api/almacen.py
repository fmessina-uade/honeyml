"""Los pedidos a Elasticsearch de los índices propios de la API: usuarios y auditoría.

Van aparte de los de `decisiones.py` para que las pruebas de cada módulo reemplacen un solo punto de
acceso sin pisarse.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from . import queries

NO_EXISTE = 404
YA_EXISTE = 409


def pedir(
    metodo: str, ruta: str, cuerpo: dict[str, Any] | None = None, es_url: str = queries.ES_URL
) -> dict[str, Any]:
    pedido = urllib.request.Request(
        f"{es_url}{ruta}",
        data=json.dumps(cuerpo, ensure_ascii=False).encode() if cuerpo is not None else None,
        headers={"Content-Type": "application/json"},
        method=metodo,
    )
    with urllib.request.urlopen(pedido, timeout=30) as resp:
        resultado: dict[str, Any] = json.load(resp)
        return resultado


def ruta_doc(indice: str, doc_id: str) -> str:
    return f"/{indice}/_doc/{urllib.parse.quote(doc_id, safe='')}"


def documento(indice: str, doc_id: str, es_url: str = queries.ES_URL) -> dict[str, Any] | None:
    try:
        r = pedir("GET", ruta_doc(indice, doc_id), es_url=es_url)
    except urllib.error.HTTPError as exc:
        if exc.code == NO_EXISTE:
            return None
        raise
    fuente: dict[str, Any] = r["_source"]
    return fuente


def buscar(indice: str, cuerpo: dict[str, Any], es_url: str = queries.ES_URL) -> dict[str, Any]:
    """Una búsqueda que, si el índice todavía no existe, contesta vacía en lugar de fallar: en una
    instalación nueva los dos índices aparecen recién con el primer documento."""
    try:
        return pedir("POST", f"/{indice}/_search", cuerpo, es_url)
    except urllib.error.HTTPError as exc:
        if exc.code == NO_EXISTE:
            return {"hits": {"total": {"value": 0}, "hits": []}}
        raise
