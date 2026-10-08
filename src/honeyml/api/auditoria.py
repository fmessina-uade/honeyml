"""El registro de lo que hace cada cuenta en el panel, para quien vela por la seguridad del sitio.

Va a su propio índice, `honeyml-auditoria`, y solo se agrega: nada de la API lo modifica ni lo
borra. Quedan los ingresos (también los fallidos y los trabados), el alta y cada cambio de una
cuenta, los veredictos y las exportaciones. Lo que pasa en el servidor (despliegues, reinicios del
vigilante, respaldos) no se copia acá: se lee de sus propios registros, en `registros.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from . import almacen, queries

AUDITORIA = "honeyml-auditoria"
MAX_TAMANO = 200


def registrar(
    usuario: str,
    rol: str | None,
    accion: str,
    objetivo: str | None = None,
    detalle: dict[str, Any] | None = None,
    es_url: str = queries.ES_URL,
) -> None:
    documento = {
        "@timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
        "usuario": usuario,
        "rol": rol,
        "accion": accion,
        "objetivo": objetivo,
        "detalle": detalle or {},
    }
    almacen.pedir("POST", f"/{AUDITORIA}/_doc", documento, es_url)


def listar(
    desde: int = 0,
    tamano: int = 50,
    accion: str | None = None,
    usuario: str | None = None,
    es_url: str = queries.ES_URL,
) -> dict[str, Any]:
    """Lo registrado, de lo más nuevo a lo más viejo, con cuántas veces pasó cada acción.

    La acción va como filtro posterior: así la cuenta por acción sale sobre todo lo registrado y el
    panel puede ofrecer las demás aunque haya una elegida.
    """
    filtro = [{"term": {"usuario": usuario}}] if usuario else []
    cuerpo: dict[str, Any] = {
        "from": max(desde, 0),
        "size": min(max(tamano, 1), MAX_TAMANO),
        "track_total_hits": True,
        "query": {"bool": {"filter": filtro}},
        "sort": [{"@timestamp": {"order": "desc"}}],
        "aggs": {"acciones": {"terms": {"field": "accion", "size": 20}}},
    }
    if accion:
        cuerpo["post_filter"] = {"term": {"accion": accion}}
    r = almacen.buscar(AUDITORIA, cuerpo, es_url)
    cubos = r.get("aggregations", {}).get("acciones", {}).get("buckets", [])
    return {
        "total": r["hits"]["total"]["value"],
        "items": [h["_source"] for h in r["hits"]["hits"]],
        "acciones": {c["key"]: c["doc_count"] for c in cubos},
    }
