"""Los números del reporte general para un rango de fechas.

Una pasada por la telemetría y otra por las decisiones traen todo lo que el reporte dibuja: la
captura, el ritmo, los protocolos, el origen, las credenciales y el motor. Sin rango, el corpus
entero. Lo que sale de acá lo lee una persona y termina impreso o en un CSV, así que no lleva
direcciones: las credenciales con forma de dirección se descartan y los comandos van tapados.

Cada rango se recuerda unos minutos. El reporte se pide para la vista previa, para imprimirlo y
para cada CSV, y las tres cosas tienen que decir lo mismo.
"""

from __future__ import annotations

import re
import threading
import time
from datetime import date
from typing import Any

from . import queries
from .decisiones import DECISIONES, DEMORA_MS, REVISIONES, SIN_TACTICA, _buscar
from .privacidad import credenciales_frecuentes, sin_direcciones

FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
VIGENCIA_S = 300.0
TOPE = 10

_recordados: dict[tuple[str | None, str | None], tuple[float, dict[str, Any]]] = {}
_candado = threading.Lock()


class RangoInvalidoError(ValueError):
    pass


def validar(desde: str | None, hasta: str | None) -> tuple[str | None, str | None]:
    """Fechas `AAAA-MM-DD`, reales y en orden. Llegan del navegador y terminan en la consulta."""
    for fecha in (desde, hasta):
        if fecha is None:
            continue
        if not FECHA.match(fecha):
            raise RangoInvalidoError("Las fechas van como AAAA-MM-DD.")
        try:
            date.fromisoformat(fecha)
        except ValueError as exc:
            raise RangoInvalidoError(f"{fecha} no es una fecha.") from exc
    if desde and hasta and desde > hasta:
        raise RangoInvalidoError("El rango empieza después de terminar.")
    return desde, hasta


def _cubos(agg: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"key": b["key"], "count": b["doc_count"]} for b in agg["buckets"]]


def _credenciales(agg: dict[str, Any]) -> list[dict[str, Any]]:
    return credenciales_frecuentes(queries.cubos_de_credenciales(agg["buckets"]), TOPE)


def _con_direcciones_distintas(agg: dict[str, Any], clave: str) -> list[dict[str, Any]]:
    return [
        {clave: b["key"], "count": b["doc_count"], "sources": b["ips"]["value"]}
        for b in agg["buckets"]
    ]


def _captura(consulta: dict[str, Any], es_url: str) -> dict[str, Any]:
    login = {"term": {"event.action": "login"}}
    cuerpo = {
        "size": 0,
        "track_total_hits": True,
        "query": consulta,
        "aggs": {
            "sensores": {"terms": {"field": "honeypot"}},
            "logins": {"filter": login},
            "logins_ok": {
                "filter": {"bool": {"must": [login, {"term": {"event.outcome": "success"}}]}}
            },
            "comandos": {"filter": {"exists": {"field": "process.command_line"}}},
            "ventana": {"stats": {"field": "@timestamp"}},
            "por_dia": {
                "date_histogram": {"field": "@timestamp", "calendar_interval": "day"},
                "aggs": {"logins": {"filter": login}},
            },
            "por_hora": {"date_histogram": {"field": "@timestamp", "calendar_interval": "hour"}},
            "protocolos": queries._ranking("network.protocol", 12)
            | {"aggs": {"ips": queries._distintas("source.ip")}},
            "categorias": queries._ranking("event.category", 8),
            "paises": queries._ranking("source.geo.country_name", 15)
            | {
                "aggs": {
                    "ips": queries._distintas("source.ip"),
                    "iso": {"terms": {"field": "source.geo.country_iso_code", "size": 1}},
                    "centro": {"geo_centroid": {"field": "source.geo.location"}},
                }
            },
            "con_geo": {"filter": {"exists": {"field": "source.geo.country_name"}}},
            "sistemas": queries._ranking("source.as.organization.name", 10)
            | {"aggs": {"ips": queries._distintas("source.ip")}},
            # Se piden de más: después se descartan las poco probadas y las que parecen direcciones.
            "usuarios": queries._ranking_de_credenciales("user.name", TOPE * 3 + 10),
            "contrasenas": queries._ranking_de_credenciales("cowrie.password", TOPE * 3 + 10),
            "comandos_top": queries._ranking("process.command_line", 8),
        },
    }
    r = queries._search(cuerpo, es_url)
    a = r["aggregations"]

    por_hora = [0] * 24
    for b in a["por_hora"]["buckets"]:
        por_hora[int(b["key_as_string"][11:13])] += b["doc_count"]

    paises = []
    for b in a["paises"]["buckets"]:
        iso = b["iso"]["buckets"]
        centro = b["centro"].get("location") or {}
        paises.append(
            {
                "country": b["key"],
                "iso": iso[0]["key"] if iso else "",
                "count": b["doc_count"],
                "sources": b["ips"]["value"],
                "lat": centro.get("lat"),
                "lon": centro.get("lon"),
            }
        )

    return {
        "events": r["hits"]["total"]["value"],
        "unique_ips": queries._direcciones_exactas(consulta, es_url),
        "logins": a["logins"]["doc_count"],
        "logins_success": a["logins_ok"]["doc_count"],
        "commands": a["comandos"]["doc_count"],
        "by_sensor": {b["key"]: b["doc_count"] for b in a["sensores"]["buckets"]},
        "first_event": a["ventana"].get("min_as_string"),
        "last_event": a["ventana"].get("max_as_string"),
        "por_dia": [
            {
                "date": b["key_as_string"][:10],
                "count": b["doc_count"],
                "logins": b["logins"]["doc_count"],
            }
            for b in a["por_dia"]["buckets"]
        ],
        "por_hora": por_hora,
        "protocolos": _con_direcciones_distintas(a["protocolos"], "protocol"),
        "categorias": _cubos(a["categorias"]),
        "paises": paises,
        "con_geo": a["con_geo"]["doc_count"],
        "sistemas": _con_direcciones_distintas(a["sistemas"], "organization"),
        "usuarios": _credenciales(a["usuarios"]),
        "contrasenas": _credenciales(a["contrasenas"]),
        "comandos": sin_direcciones(_cubos(a["comandos_top"])),
    }


def _motor(desde: str | None, hasta: str | None, es_url: str) -> dict[str, Any] | None:
    """Lo que decidió el motor sobre los eventos del rango. El rango va sobre el momento del evento
    y no sobre el de la decisión: un evento viejo vuelto a triar sigue siendo de su día."""
    rango = {k: v for k, v in (("gte", desde), ("lte", hasta)) if v}
    filtro = [{"range": {"evento.momento": rango}}] if rango else []
    cuerpo = {
        "size": 0,
        "track_total_hits": True,
        "runtime_mappings": DEMORA_MS,
        "query": {"bool": {"filter": filtro}},
        "aggs": {
            "severidad": {"terms": {"field": "decision.severidad", "size": 10}},
            "tactica": {
                "terms": {"field": "decision.tactica_mitre", "size": 20, "missing": SIN_TACTICA}
            },
            "copiadas": {"filter": {"exists": {"field": "ciclo.reutilizada_de"}}},
            "costo": {"sum": {"field": "modelo.costo_usd"}},
            "requieren": {"filter": {"term": {"ciclo.requiere_revision": True}}},
            "conclusion": {
                "filter": {"bool": {"must_not": [{"term": {"ciclo.retriaje": True}}]}},
                "aggs": {
                    "percentiles": {"percentiles": {"field": "demora_ms", "percents": [50, 90]}}
                },
            },
        },
    }
    r = _buscar(DECISIONES, cuerpo, es_url)
    if r is None:
        return None
    a = r["aggregations"]
    pct = a["conclusion"]["percentiles"]["values"]

    veredictos: dict[str, int] = {}
    a_ciegas = 0
    filtro_v = [{"range": {"@timestamp": rango}}] if rango else []
    v = _buscar(
        REVISIONES,
        {
            "size": 0,
            "query": {"bool": {"filter": filtro_v}},
            "aggs": {
                "v": {"terms": {"field": "veredicto"}},
                "ciegas": {"filter": {"term": {"a_ciegas": True}}},
            },
        },
        es_url,
    )
    if v is not None:
        veredictos = {c["key"]: c["count"] for c in _cubos(v["aggregations"]["v"])}
        a_ciegas = v["aggregations"]["ciegas"]["doc_count"]

    def segundos(ms: float | None) -> float | None:
        return round(ms / 1000, 1) if ms is not None else None

    return {
        "total": r["hits"]["total"]["value"],
        "copiadas": a["copiadas"]["doc_count"],
        "costo_usd": round(a["costo"]["value"], 4),
        "requieren": a["requieren"]["doc_count"],
        "por_severidad": _cubos(a["severidad"]),
        "por_tactica": _cubos(a["tactica"]),
        "mediana_s": segundos(pct.get("50.0")),
        "p90_s": segundos(pct.get("90.0")),
        "confirmadas": veredictos.get("confirma", 0),
        "corregidas": veredictos.get("corrige", 0),
        "a_ciegas": a_ciegas,
    }


def general(
    desde: str | None = None, hasta: str | None = None, es_url: str = queries.ES_URL
) -> dict[str, Any]:
    desde, hasta = validar(desde, hasta)
    clave = (desde, hasta)
    with _candado:
        recordado = _recordados.get(clave)
        if recordado and time.monotonic() - recordado[0] < VIGENCIA_S:
            return recordado[1]

    # El fin del día, no su comienzo: con la fecha pelada el último día quedaría afuera.
    fin = f"{hasta}T23:59:59.999Z" if hasta else None
    inicio = f"{desde}T00:00:00Z" if desde else None
    datos = {
        "desde": desde,
        "hasta": hasta,
        "captura": _captura(queries._filtrado(None, inicio, fin), es_url),
        "motor": _motor(inicio, fin, es_url),
    }
    with _candado:
        if len(_recordados) > 16:
            _recordados.clear()
        _recordados[clave] = (time.monotonic(), datos)
    return datos
