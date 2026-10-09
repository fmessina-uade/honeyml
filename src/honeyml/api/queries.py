"""Las agregaciones sobre los índices ECS que alimentan el panel.

urllib pelado, así el módulo no depende de nada fuera de la biblioteca estándar: las mismas
funciones sirven la API en vivo y el respaldo estático que se usa para las capturas.
"""

from __future__ import annotations

import datetime
import json
import os
import urllib.request
from typing import Any

from .. import redes

# En desarrollo Elasticsearch escucha en loopback. En el servidor, la API y el motor corren en
# contenedores y lo alcanzan por el nombre del servicio dentro de la red de análisis.
ES_URL = os.environ.get("ES_URL", "http://localhost:9200")
INDEX = "honeypot-*"

# todas las consultas dejan afuera lo que no viene de terceros: los healthcheck de los contenedores
# y las pruebas propias desde redes privadas
NOT_LOCAL: dict[str, Any] = redes.EXTERNA


def _search(body: dict[str, Any], es_url: str = ES_URL, index: str = INDEX) -> dict[str, Any]:
    req = urllib.request.Request(
        f"{es_url}/{index}/_search",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        result: dict[str, Any] = json.load(resp)
        return result


# Cada índice diario contesta solo sus primeros valores, y Elasticsearch suma esas respuestas. Un
# país o un usuario que un día queda afuera de ese recorte pierde los eventos de ese día en el
# total, y con un índice por día el error se acumula: con el recorte por defecto, el ranking de
# usuarios cambia de orden en los últimos puestos y a los países chicos les faltan direcciones. Con
# dos mil valores por índice, las sumas coinciden con el conteo exacto.
def _ranking(field: str, size: int) -> dict[str, Any]:
    return {"terms": {"field": field, "size": size, "shard_size": max(2_000, size)}}


def _terms(
    field: str, size: int, es_url: str = ES_URL, extra: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    query = extra or NOT_LOCAL
    body = {"size": 0, "query": query, "aggs": {"t": _ranking(field, size)}}
    buckets = _search(body, es_url)["aggregations"]["t"]["buckets"]
    return [{"key": b["key"], "count": b["doc_count"]} for b in buckets]


# Elasticsearch cuenta valores distintos con un estimador, y con su umbral por defecto (tres mil) se
# equivoca cerca de un uno por ciento por encima de ese número. Los países y protocolos con más
# tráfico lo pasan, así que se le pide el umbral máximo que admite: por debajo de él, el conteo por
# grupo coincide con el exacto.
def _distintas(campo: str) -> dict[str, Any]:
    return {"cardinality": {"field": campo, "precision_threshold": 40_000}}


def _direcciones_exactas(query: dict[str, Any], es_url: str = ES_URL) -> int:
    """Direcciones distintas del corpus entero, contadas una por una y no estimadas.

    El total ya anda cerca del umbral del estimador, y es la cifra que se compara con los artefactos
    derivados, que cuentan sobre la tabla consolidada. De a diez mil por pedido alcanzan unos pocos.
    """
    total, despues = 0, None
    while True:
        compuesta: dict[str, Any] = {
            "size": 10_000,
            "sources": [{"ip": {"terms": {"field": "source.ip"}}}],
        }
        if despues:
            compuesta["after"] = despues
        body = {"size": 0, "query": query, "aggs": {"c": {"composite": compuesta}}}
        agg = _search(body, es_url)["aggregations"]["c"]
        total += len(agg["buckets"])
        despues = agg.get("after_key")
        if len(agg["buckets"]) < compuesta["size"] or not despues:
            return total


def overview(es_url: str = ES_URL) -> dict[str, Any]:
    """Los contadores de portada, los números con los que abre el panel."""
    body = {
        "size": 0,
        # sin esto, Elasticsearch informa como mucho 10.000 y corta ahí
        "track_total_hits": True,
        "query": NOT_LOCAL,
        "aggs": {
            "sensors": {"terms": {"field": "honeypot"}},
            "logins": {"filter": {"term": {"event.action": "login"}}},
            "logins_ok": {
                "filter": {
                    "bool": {
                        "must": [
                            {"term": {"event.action": "login"}},
                            {"term": {"event.outcome": "success"}},
                        ]
                    }
                }
            },
            "commands": {"filter": {"exists": {"field": "process.command_line"}}},
            "window": {"stats": {"field": "@timestamp"}},
        },
    }
    res = _search(body, es_url)
    agg = res["aggregations"]
    return {
        "events": res["hits"]["total"]["value"],
        "unique_ips": _direcciones_exactas(NOT_LOCAL, es_url),
        "logins": agg["logins"]["doc_count"],
        "logins_success": agg["logins_ok"]["doc_count"],
        "commands": agg["commands"]["doc_count"],
        "by_sensor": {b["key"]: b["doc_count"] for b in agg["sensors"]["buckets"]},
        "first_event": agg["window"]["min_as_string"],
        "last_event": agg["window"]["max_as_string"],
    }


def _filtrado(
    sensor: str | None = None, desde: str | None = None, hasta: str | None = None
) -> dict[str, Any]:
    """La consulta base más los filtros que haya pasado quien llama.

    Se arma acá y no en cada consulta para que todas las vistas filtradas dejen afuera los orígenes
    internos de la misma forma. Sin filtros devuelve exactamente la consulta sin
    filtrar, así que sumarle filtros a una vista no puede cambiar lo que devuelve por defecto.
    """
    must: list[dict[str, Any]] = []
    if sensor:
        must.append({"term": {"honeypot": sensor}})
    if desde or hasta:
        rango: dict[str, str] = {}
        if desde:
            rango["gte"] = desde
        if hasta:
            rango["lte"] = hasta
        must.append({"range": {"@timestamp": rango}})

    if not must:
        return NOT_LOCAL
    return {"bool": {"must": must, "must_not": redes.TERMINOS}}


# Intervalos aceptados. Se validan contra esta lista y no se pasan tal cual a Elasticsearch: el
# parámetro llega desde el navegador y termina dentro del cuerpo de la consulta.
INTERVALOS = {"hour", "day", "week", "month"}


def timeline(
    es_url: str = ES_URL,
    interval: str = "day",
    sensor: str | None = None,
    desde: str | None = None,
    hasta: str | None = None,
) -> list[dict[str, Any]]:
    """Eventos en el tiempo: muestra que el tráfico no afloja, y también los cortes de captura."""
    if interval not in INTERVALOS:
        interval = "day"
    body = {
        "size": 0,
        "query": _filtrado(sensor, desde, hasta),
        "aggs": {
            "t": {
                "date_histogram": {"field": "@timestamp", "calendar_interval": interval},
                "aggs": {"sensors": {"terms": {"field": "honeypot"}}},
            }
        },
    }
    # Con intervalo horario la fecha sola no alcanza: dos puntos del mismo día quedarían con la
    # misma etiqueta y el eje mostraría repetidos.
    corte = 13 if interval == "hour" else 10
    out = []
    for b in _search(body, es_url)["aggregations"]["t"]["buckets"]:
        by_sensor = {s["key"]: s["doc_count"] for s in b["sensors"]["buckets"]}
        etiqueta = b["key_as_string"][:corte].replace("T", " ")
        out.append({"date": etiqueta, "count": b["doc_count"], **by_sensor})
    return out


def top_credentials(es_url: str = ES_URL, size: int = 10) -> dict[str, list[dict[str, Any]]]:
    """Lo que los atacantes prueban de verdad: la evidencia detrás de "usá contraseñas fuertes"."""
    return {
        "users": _terms("user.name", size, es_url),
        "passwords": _terms("cowrie.password", size, es_url),
    }


def top_commands(es_url: str = ES_URL, size: int = 12) -> list[dict[str, Any]]:
    return _terms("process.command_line", size, es_url)


def protocols(es_url: str = ES_URL) -> list[dict[str, Any]]:
    """Superficie de ataque por protocolo: qué suma el sensor multiprotocolo sobre SSH solo."""
    return _terms("network.protocol", 15, es_url)


def attack_stages(es_url: str = ES_URL) -> list[dict[str, Any]]:
    """Eventos agrupados por etapa de la intrusión."""
    return _terms("event.category", 10, es_url)


def protocol_detail(es_url: str = ES_URL) -> list[dict[str, Any]]:
    """Tráfico por protocolo en el sensor multiprotocolo, con las direcciones distintas de cada uno.

    Contar solo eventos acá engaña: SMB domina porque un solo gusano reintenta sin parar, mientras
    que HTTP lo tocan muchos más escáneres distintos. Los dos números juntos distinguen una cosa de
    la otra.
    """
    body = {
        "size": 0,
        "query": {
            "bool": {
                "must": [{"term": {"honeypot": "dionaea"}}],
                "must_not": redes.TERMINOS,
            }
        },
        "aggs": {
            "p": {
                **_ranking("network.protocol", 12),
                "aggs": {
                    "ips": _distintas("source.ip"),
                    "port": {"terms": {"field": "destination.port", "size": 1}},
                },
            }
        },
    }
    out = []
    for b in _search(body, es_url)["aggregations"]["p"]["buckets"]:
        ports = b["port"]["buckets"]
        out.append(
            {
                "protocol": b["key"],
                "count": b["doc_count"],
                "sources": b["ips"]["value"],
                "port": ports[0]["key"] if ports else None,
            }
        )
    return out


def geography(es_url: str = ES_URL) -> dict[str, Any]:
    """De dónde vienen los ataques, por país y por sistema autónomo.

    Se informan los dos, y ahí está la gracia. El país solo dice poco: un ataque lanzado desde una
    nube alquilada y uno desde una conexión hogareña pueden compartir bandera y ser cosas
    completamente distintas. El sistema autónomo los separa, porque nombra la red que efectivamente
    opera la dirección.

    Las direcciones distintas van al lado del conteo de eventos por lo mismo que en protocol_detail:
    un solo equipo insistente infla el total de un país sin que haya tantos atacantes ahí.

    La cobertura se informa en vez de darse por sentada. Las bases que vienen con el plugin son las
    gratuitas de MaxMind y no conocen todas las direcciones; taparlo haría que los porcentajes
    parezcan completos cuando en realidad se calculan sobre un subconjunto.
    """
    body = {
        "size": 0,
        "track_total_hits": True,
        "query": NOT_LOCAL,
        "aggs": {
            "con_geo": {
                "filter": {"exists": {"field": "source.geo.country_name"}},
                "aggs": {"ips": _distintas("source.ip")},
            },
            "con_asn": {"filter": {"exists": {"field": "source.as.organization.name"}}},
            "paises": {
                **_ranking("source.geo.country_name", 12),
                "aggs": {
                    "ips": _distintas("source.ip"),
                    "iso": {"terms": {"field": "source.geo.country_iso_code", "size": 1}},
                    # Centroide de las direcciones observadas, no del país. Se usa para ubicar el
                    # marcador en el globo, y sale de los datos en vez de una tabla fija de
                    # coordenadas que habría que mantener aparte y que envejecería sola.
                    "centro": {"geo_centroid": {"field": "source.geo.location"}},
                },
            },
            "sistemas": {
                **_ranking("source.as.organization.name", 10),
                "aggs": {"ips": _distintas("source.ip")},
            },
        },
    }
    res = _search(body, es_url)
    agg = res["aggregations"]

    paises = []
    for b in agg["paises"]["buckets"]:
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

    sistemas = [
        {"organization": b["key"], "count": b["doc_count"], "sources": b["ips"]["value"]}
        for b in agg["sistemas"]["buckets"]
    ]

    total = res["hits"]["total"]["value"]
    return {
        "events": total,
        "with_geo": agg["con_geo"]["doc_count"],
        "with_asn": agg["con_asn"]["doc_count"],
        "countries": paises,
        "autonomous_systems": sistemas,
    }


def hourly(es_url: str = ES_URL) -> list[dict[str, Any]]:
    """Ataques por hora del día, en UTC.

    Lo interesante es que esta distribución es plana. La actividad humana tiene horario de
    oficina; una curva chata es la firma de la automatización, y se muestra más fácil de lo que se
    argumenta.
    """
    body = {
        "size": 0,
        "query": NOT_LOCAL,
        "aggs": {
            "h": {
                "date_histogram": {"field": "@timestamp", "calendar_interval": "hour"},
                "aggs": {"logins": {"filter": {"term": {"event.action": "login"}}}},
            }
        },
    }
    per_hour = [0] * 24
    logins_per_hour = [0] * 24
    for b in _search(body, es_url)["aggregations"]["h"]["buckets"]:
        hour = int(b["key_as_string"][11:13])
        per_hour[hour] += b["doc_count"]
        logins_per_hour[hour] += b["logins"]["doc_count"]
    return [{"hour": h, "count": per_hour[h], "logins": logins_per_hour[h]} for h in range(24)]


def weekly_rhythm(es_url: str = ES_URL) -> dict[str, Any]:
    """Eventos dispuestos como día de la semana por hora del día: 168 celdas, en UTC.

    La curva horaria plana ya dice que el tráfico es automático, pero en veinticuatro barras se lee
    como un gráfico que casualmente quedó parejo. Desplegado sobre una semana entera deja de ser una
    afirmación y pasa a ser algo que el lector comprueba solo: un sistema con gente detrás se
    enciende de lunes a viernes entre las nueve y las seis, y se apaga de noche y los fines de
    semana. El patrón que tenga o no tenga esta grilla se ve de un vistazo, sin una estadística en
    el medio.

    El agrupado se hace acá y no en Elasticsearch porque el histograma horario ya se está leyendo:
    sumar una agregación con script sería pedirle al clúster que rehaga trabajo para dos mil cubos
    que entran en memoria.
    """
    body = {
        "size": 0,
        "query": NOT_LOCAL,
        "aggs": {
            "h": {
                "date_histogram": {"field": "@timestamp", "calendar_interval": "hour"},
            }
        },
    }

    # [día][hora], con lunes en 0 para que el fin de semana quede junto al final de la fila.
    matriz = [[0] * 24 for _ in range(7)]
    horas_observadas = [[0] * 24 for _ in range(7)]

    for b in _search(body, es_url)["aggregations"]["h"]["buckets"]:
        marca = b["key_as_string"]
        fecha = datetime.datetime.strptime(marca[:13], "%Y-%m-%dT%H").replace(tzinfo=datetime.UTC)
        matriz[fecha.weekday()][fecha.hour] += b["doc_count"]
        horas_observadas[fecha.weekday()][fecha.hour] += 1

    # El promedio por hora observada y no el total: la captura no cubre la misma cantidad de lunes
    # que de martes, así que los totales crudos harían parecer más activo al día que más veces
    # apareció en la ventana de captura.
    promedio = [
        [
            round(matriz[d][h] / horas_observadas[d][h], 1) if horas_observadas[d][h] else 0.0
            for h in range(24)
        ]
        for d in range(7)
    ]

    return {
        "total": [[matriz[d][h] for h in range(24)] for d in range(7)],
        "average": promedio,
        "observed": horas_observadas,
    }


def snapshot(es_url: str = ES_URL) -> dict[str, Any]:
    """Todo lo que necesita el panel, en un solo objeto. También lo usa el respaldo congelado."""
    return {
        "overview": overview(es_url),
        "timeline": timeline(es_url),
        "credentials": top_credentials(es_url),
        "commands": top_commands(es_url),
        "protocols": protocols(es_url),
        "stages": attack_stages(es_url),
        "protocol_detail": protocol_detail(es_url),
        "hourly": hourly(es_url),
        "geography": geography(es_url),
        "weekly_rhythm": weekly_rhythm(es_url),
    }
