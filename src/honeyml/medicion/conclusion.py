"""El tiempo de conclusión del motor: del evento capturado a la decisión guardada.

Es la misma definición que muestra el panel, con la ventana elegible y con el desglose que el panel
no da. Se separan las decisiones copiadas de una conducta ya resuelta, que solo leen el bus, de las
razonadas, que esperan al servicio de inferencia: mezcladas, la media dice poco de cualquiera de los
dos caminos. De las razonadas se informa además cuánto de la demora fue la llamada al modelo.

Quedan afuera las decisiones vueltas a triar, que llevan la marca temporal del retriaje sobre un
evento que pudo ocurrir semanas antes, y las de origen interno, que son pruebas propias. Los
percentiles los estima Elasticsearch, con un error chico frente a la media.

Solo lee. Se corre en el servidor con `make conclusion`; con `--json` imprime el resultado crudo.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .. import redes
from ..api import queries
from ..api.decisiones import DECISIONES, DEMORA_MS

# Origen interno: las pruebas propias no son tiempo de conclusión sobre tráfico de terceros. En el
# documento de la decisión la dirección va en `evento.origen`.
_INTERNAS = [{"term": {"evento.origen": r}} for r in redes.INTERNAS]


def _base(desde: str) -> dict[str, Any]:
    """El filtro común: la ventana, sin retriaje y sin origen interno."""
    return {
        "bool": {
            "filter": [{"range": {"@timestamp": {"gte": desde}}}],
            "must_not": [{"term": {"ciclo.retriaje": True}}, *_INTERNAS],
        }
    }


def _metricas() -> dict[str, Any]:
    return {
        "percentiles": {"percentiles": {"field": "demora_ms", "percents": [50, 90]}},
        "media": {"avg": {"field": "demora_ms"}},
    }


def calcular(desde: str = "now-7d", es_url: str = queries.ES_URL) -> dict[str, Any]:
    """El tiempo de conclusión en la ventana, en total y partido entre copiadas y razonadas."""
    cuerpo = {
        "size": 0,
        # Sin esto el total queda topado en 10.000 y la resta de las copiadas daría negativo.
        "track_total_hits": True,
        "runtime_mappings": DEMORA_MS,
        "query": _base(desde),
        "aggs": {
            # Las tres van envueltas en un filtro: así `percentiles` y `media` quedan como
            # sub-agregados con nombre. Sueltas en el mismo nivel serían dos tipos en un agregado,
            # que no se permite. El total no filtra nada, pero mantiene la misma forma.
            "total": {"filter": {"match_all": {}}, "aggs": _metricas()},
            "copiadas": {
                "filter": {"exists": {"field": "ciclo.reutilizada_de"}},
                "aggs": _metricas(),
            },
            "razonadas": {
                "filter": {"bool": {"must_not": [{"exists": {"field": "ciclo.reutilizada_de"}}]}},
                "aggs": {**_metricas(), "modelo_s": {"avg": {"field": "modelo.segundos"}}},
            },
        },
    }
    r = queries._search(cuerpo, es_url, index=DECISIONES)
    a = r["aggregations"]
    total = r["hits"]["total"]["value"]
    copiadas = a["copiadas"]["doc_count"]
    return {
        "desde": desde,
        "decisiones": total,
        "copiadas": copiadas,
        "razonadas": total - copiadas,
        "total": _tramo(a["total"], total),
        "copiadas_detalle": _tramo(a["copiadas"], copiadas),
        "razonadas_detalle": {
            **_tramo(a["razonadas"], total - copiadas),
            # `modelo.segundos` ya viene en segundos, a diferencia de la demora, que está en
            # milisegundos: no se divide.
            "modelo_s": _redondear(a["razonadas"].get("modelo_s", {}).get("value")),
        },
    }


def _tramo(agg: dict[str, Any], n: int) -> dict[str, Any]:
    pct = agg.get("percentiles", {}).get("values", {})
    return {
        "decisiones": n,
        "media_s": _seg(agg.get("media", {}).get("value")),
        "mediana_s": _seg(pct.get("50.0")),
        "p90_s": _seg(pct.get("90.0")),
    }


def _seg(ms: float | None) -> float | None:
    return round(ms / 1000, 1) if ms is not None else None


def _redondear(s: float | None) -> float | None:
    return round(s, 1) if s is not None else None


def _num(v: float | None) -> str:
    return "sin datos" if v is None else f"{v:.1f} s".replace(".", ",")


def informe(r: dict[str, Any]) -> list[str]:
    lineas = [
        f"Tiempo de conclusión desde {r['desde']}, sobre {r['decisiones']} decisiones "
        f"({r['copiadas']} copiadas, {r['razonadas']} razonadas).",
        "Del evento capturado a la decisión guardada, sin retriaje ni pruebas propias.",
        "",
    ]
    for titulo, clave in (
        ("Todas", "total"),
        ("Copiadas del repertorio", "copiadas_detalle"),
        ("Razonadas con el modelo", "razonadas_detalle"),
    ):
        t = r[clave]
        linea = (
            f"  {titulo:<26} media {_num(t['media_s'])}, mediana {_num(t['mediana_s'])}, "
            f"percentil 90 {_num(t['p90_s'])}"
        )
        if clave == "razonadas_detalle":
            linea += f"  (la llamada al modelo, {_num(t['modelo_s'])})"
        lineas.append(linea)
    return lineas


def main() -> int:
    ap = argparse.ArgumentParser(description="Tiempo de conclusión del motor.")
    ap.add_argument(
        "--desde", default="now-7d", help="inicio de la ventana, por ejemplo now-7d o now-30d"
    )
    ap.add_argument("--json", action="store_true", help="el resultado sin formato")
    args = ap.parse_args()
    r = calcular(args.desde)
    if args.json:
        json.dump(r, sys.stdout, ensure_ascii=False, indent=2)
    else:
        print("\n".join(informe(r)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
