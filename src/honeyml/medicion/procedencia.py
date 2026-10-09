"""De dónde viene cada evento del corpus capturado, sin mostrar ninguna dirección.

Separa lo que mandaron terceros desde internet de lo que no: los chequeos de salud del propio
servidor (loopback), las conexiones desde redes privadas, que solo pueden salir del anfitrión o de
otro contenedor, y los eventos sin dirección de origen, que registra el sensor por su cuenta. De
cada grupo da el conjunto de datos y los días, para poder explicarlo. También cuenta las marcas de
falla del pipeline: una fecha que no se pudo leer deja el evento con la hora de ingesta.

Solo lee. Se corre en el servidor con `make procedencia`.
"""

from __future__ import annotations

import json
import urllib.request
from typing import Any

from ..api import queries

PRIVADAS = [
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "100.64.0.0/10",
    "169.254.0.0/16",
    "fc00::/7",
    "fe80::/10",
]
LOOPBACK = ["127.0.0.0/8", "::1/128"]

GRUPOS: dict[str, dict[str, Any]] = {
    "loopback": {"bool": {"should": [{"term": {"source.ip": r}} for r in LOOPBACK]}},
    "privada": {"bool": {"should": [{"term": {"source.ip": r}} for r in PRIVADAS]}},
    "sin_direccion": {"bool": {"must_not": [{"exists": {"field": "source.ip"}}]}},
}


def _es(path: str, body: dict[str, Any]) -> Any:
    req = urllib.request.Request(
        f"{queries.ES_URL}{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def consulta() -> dict[str, Any]:
    detalle = {
        "conjuntos": {"terms": {"field": "event.dataset", "size": 20}},
        "dias": {
            "date_histogram": {
                "field": "@timestamp",
                "calendar_interval": "day",
                "min_doc_count": 1,
            }
        },
        "direcciones": {"cardinality": {"field": "source.ip"}},
    }
    publica = {
        "bool": {
            "filter": [{"exists": {"field": "source.ip"}}],
            "must_not": list(GRUPOS.values()),
        }
    }
    return {
        "size": 0,
        "track_total_hits": True,
        "aggs": {
            "primero": {"min": {"field": "@timestamp"}},
            "ultimo": {"max": {"field": "@timestamp"}},
            "grupos": {"filters": {"filters": GRUPOS}, "aggs": detalle},
            "publica": {
                "filter": publica,
                "aggs": {"primero": {"min": {"field": "@timestamp"}}},
            },
            "marcas": {"terms": {"field": "tags", "size": 20}},
        },
    }


def _dias(buckets: list[dict[str, Any]]) -> str:
    dias = [b["key_as_string"][:10] for b in buckets]
    if len(dias) <= 6:
        return ", ".join(dias)
    return f"{len(dias)} días, del {dias[0]} al {dias[-1]}"


def _momento(agregacion: dict[str, Any]) -> str:
    # un mínimo o un máximo sobre un grupo vacío no trae fecha
    return str(agregacion.get("value_as_string", "sin eventos"))


def informe(r: dict[str, Any]) -> list[str]:
    a = r["aggregations"]
    total = r["hits"]["total"]["value"]
    lineas = [
        f"Eventos: {total:,}",
        f"Primero: {_momento(a['primero'])}   último: {_momento(a['ultimo'])}",
        f"Primer evento desde una dirección pública: {_momento(a['publica']['primero'])}",
        f"Desde direcciones públicas: {a['publica']['doc_count']:,}",
    ]
    for nombre, g in a["grupos"]["buckets"].items():
        lineas.append(f"\n{nombre}: {g['doc_count']:,} eventos")
        if not g["doc_count"]:
            continue
        if nombre != "sin_direccion":
            lineas.append(f"  direcciones distintas: {g['direcciones']['value']}")
        lineas.append(f"  días: {_dias(g['dias']['buckets'])}")
        for b in g["conjuntos"]["buckets"]:
            lineas.append(f"  {b['key']}: {b['doc_count']:,}")
        resto = g["doc_count"] - sum(b["doc_count"] for b in g["conjuntos"]["buckets"])
        if resto:
            lineas.append(f"  sin conjunto de datos: {resto:,}")
    lineas.append("\nMarcas del pipeline:")
    marcas = a["marcas"]["buckets"]
    lineas += [f"  {b['key']}: {b['doc_count']:,}" for b in marcas] or ["  ninguna"]
    return lineas


def main() -> None:
    print("\n".join(informe(_es(f"/{queries.INDEX}/_search", consulta()))))


if __name__ == "__main__":
    main()
