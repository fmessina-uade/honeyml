"""What the triage engine is allowed to look up while reasoning about an event.

The bus message carries the trigger and nothing else: one line saying an address ran a command.
Deciding whether that matters needs the surroundings — has this address been here before, what else
did it do in the same session, is the sequence one the corpus has already seen a thousand times.
These are the lookups that answer those questions.

THREE PROPERTIES, EACH LOAD-BEARING

*Read-only.* Nothing here writes, deletes, or reaches outside the project's own data. That is not
tidiness: the input is attacker-controlled text. A command captured by the honeypot can say anything
at all, including instructions addressed to whatever reads it, and it lands in the model's context
by design. An engine whose entire toolbox is queries cannot be talked into doing damage, because
there is no damage available to do. Anything that acts on the world belongs outside this module and
behind a human.

*Bounded.* Every lookup caps what it returns. One session in the corpus ran 1.400 commands; handed
over whole it would crowd out the rest of the context and be paid for by the token. The caps are
constants below, and each one is a declared limit rather than a surprise.

*Cut off at the event's own timestamp.* History means what was known *before* this event, not
everything in the index today. Without the cut, the engine judges an early event using evidence
from a later one, scores better than it could ever score live, and the adversarial validation
campaign ends up measuring a system that cannot exist. The horizon is a parameter of every
historical lookup, and it is not optional.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from ..api import queries
from ..education import fingerprints
from ..education.session_replay import anonymize
from ..features import arquetipos
from .consumer import EventoDelBus
from .severidad import Severidad, maxima, piso_de

# Cuántos comandos de una sesión se entregan. Doce es el mismo corte con que se publican las
# familias de huellas, así que una sesión y su familia se comparan término a término.
MAX_COMMANDS = 12
# Cuántas acciones distintas se resumen del historial de una dirección.
MAX_ACCIONES = 8

# Ventana hacia atrás para detectar una ráfaga coordinada.
#
# Seis horas. Una campaña de botnet reparte su objetivo entre nodos en minutos u horas, no en días;
# con una ventana de un día el conteo se llena del tráfico de fondo —unos treinta mil eventos
# diarios— y deja de distinguir nada. Con una hora, una campaña lenta pasa desapercibida.
VENTANA_RAFAGA_HORAS = 6


def _restar_horas(marca: str, horas: int) -> str:
    """`marca` menos `horas`, en el mismo formato ISO que usa el índice. Cadena vacía si no parsea.

    Devolver vacío en vez de levantar: una marca temporal rara es un evento que no se puede
    correlacionar, no una razón para tirar abajo el ciclo de razonamiento.
    """
    try:
        t = datetime.fromisoformat(marca.replace("Z", "+00:00"))
    except ValueError:
        return ""
    return (t - timedelta(hours=horas)).isoformat().replace("+00:00", "Z")


def _buscar(body: dict[str, Any], es_url: str = queries.ES_URL) -> dict[str, Any]:
    return queries._search(body, es_url)


def historial_de_direccion(ip: str, hasta: str, es_url: str = queries.ES_URL) -> dict[str, Any]:
    """What this address had already done before `hasta`.

    `hasta` is the horizon and is required for the reason in the module header: an address whose
    first appearance is the event being judged looks very different from one that has been trying
    for three weeks, and only the second is a fact the engine could have known at the time.
    """
    if not ip or not hasta:
        return {"conocida": False}

    body = {
        "size": 0,
        "query": {
            "bool": {
                "filter": [
                    {"term": {"source.ip": ip}},
                    {"range": {"@timestamp": {"lt": hasta}}},
                ]
            }
        },
        "aggs": {
            "acciones": {"terms": {"field": "event.action", "size": MAX_ACCIONES}},
            "categorias": {"terms": {"field": "event.category", "size": MAX_ACCIONES}},
            "sesiones": {"cardinality": {"field": "cowrie.session"}},
            "primera": {"min": {"field": "@timestamp"}},
            "accesos": {
                "filter": {
                    "bool": {
                        "filter": [
                            {"term": {"event.category": "authentication"}},
                            {"term": {"event.outcome": "success"}},
                        ]
                    }
                }
            },
        },
    }
    r = _buscar(body, es_url)
    agg = r["aggregations"]
    total = r["hits"]["total"]["value"]

    return {
        "conocida": total > 0,
        "eventos_previos": total,
        "sesiones_previas": int(agg["sesiones"]["value"]),
        "accesos_exitosos_previos": int(agg["accesos"]["doc_count"]),
        "primera_vez": (agg["primera"].get("value_as_string") or "")[:19],
        "acciones": {b["key"]: b["doc_count"] for b in agg["acciones"]["buckets"]},
        "categorias": {b["key"]: b["doc_count"] for b in agg["categorias"]["buckets"]},
    }


def comandos_de_la_sesion(
    session: str, hasta: str = "", es_url: str = queries.ES_URL
) -> dict[str, Any]:
    """The commands run in this session, in order, up to the horizon.

    Cut at `hasta` as well when given: the point of the sequence is what led up to the event, and
    including what came after would let the engine reason from the ending backwards.
    """
    if not session:
        return {"comandos": [], "total": 0}

    filtros: list[dict[str, Any]] = [
        {"term": {"cowrie.session": session}},
        {"term": {"event.category": "process"}},
    ]
    if hasta:
        filtros.append({"range": {"@timestamp": {"lte": hasta}}})

    body = {
        "size": MAX_COMMANDS,
        "query": {"bool": {"filter": filtros}},
        "sort": [{"@timestamp": "asc"}],
        "_source": ["process.command_line", "@timestamp"],
    }
    r = _buscar(body, es_url)
    total = r["hits"]["total"]["value"]
    comandos = [
        h["_source"].get("process", {}).get("command_line", "")
        for h in r["hits"]["hits"]
        if h["_source"].get("process", {}).get("command_line")
    ]
    return {
        "comandos": comandos,
        "total": total,
        # Que la lista esté recortada tiene que ser visible: un modelo que cree estar viendo la
        # sesión entera concluye distinto que uno que sabe que le mostraron los primeros doce.
        "truncado": total > len(comandos),
    }


def familia_de_la_sesion(comandos: list[str]) -> dict[str, Any] | None:
    """Which published fingerprint family this exact command sequence belongs to, if any.

    Matching is byte-identical, which is the same strict criterion the families were built with. A
    near miss is deliberately not a match: the value of this lookup is that a hit means "5.514 other
    sessions did precisely this", and a fuzzy hit would not mean that.
    """
    if not comandos:
        return None
    datos = fingerprints.load()
    if datos is None:
        return None

    etiqueta = anonymize("|".join(comandos)).replace("attacker-", "family-")
    for f in datos.get("families", []):
        if f.get("label") == etiqueta:
            return {
                "familia": f["label"],
                "sesiones": f["sessions"],
                "direcciones": f["sources"],
                "tacticas": f.get("tactics", []),
                "primera_vez": f.get("first_seen"),
            }
    return None


def origen_de_direccion(ip: str, es_url: str = queries.ES_URL) -> dict[str, Any]:
    """Country and operating network of an address, as the pipeline enriched them.

    The network matters more than the country and the section of the panel says why: a rented
    datacentre address and a home connection are different things that share a flag. Both are
    reported so the engine can weigh them, and neither is attribution.
    """
    if not ip:
        return {}
    body = {
        "size": 1,
        "query": {"bool": {"filter": [{"term": {"source.ip": ip}}]}},
        "_source": ["source.geo.country_name", "source.as.organization.name", "source.as.number"],
    }
    hits = _buscar(body, es_url)["hits"]["hits"]
    if not hits:
        return {}
    origen = hits[0]["_source"].get("source", {})
    return {
        "pais": origen.get("geo", {}).get("country_name"),
        "red": origen.get("as", {}).get("organization", {}).get("name"),
        "sistema_autonomo": origen.get("as", {}).get("number"),
    }


def trayectoria_de_direccion(ip: str, hasta: str, es_url: str = queries.ES_URL) -> dict[str, Any]:
    """How far up the scale this address had already got, before this event.

    `historial_de_direccion` counts what it did; this says how far it *reached*. The difference is
    the one the severity scale is built on: an address with nine thousand prior events that never
    got past a credential prompt is a different thing from one that ran commands last Tuesday, and
    the raw count cannot tell them apart.

    Returns the pairs of (category, outcome) it produced before the horizon, each mapped through the
    same floor rule the engine is judged by — so "already reached ALTO" means exactly what it means
    everywhere else, and not something this function invented.
    """
    if not ip or not hasta:
        return {"conocida": False}

    body = {
        "size": 0,
        "query": {
            "bool": {
                "filter": [
                    {"term": {"source.ip": ip}},
                    {"range": {"@timestamp": {"lt": hasta}}},
                ]
            }
        },
        "aggs": {
            "categorias": {
                "terms": {"field": "event.category", "size": MAX_ACCIONES},
                "aggs": {"resultados": {"terms": {"field": "event.outcome", "size": 4}}},
            }
        },
    }
    r = _buscar(body, es_url)
    if r["hits"]["total"]["value"] == 0:
        return {"conocida": False}

    alcanzados: list[Severidad] = []
    detalle: dict[str, int] = {}
    for cat in r["aggregations"]["categorias"]["buckets"]:
        for res in cat["resultados"]["buckets"]:
            nivel = piso_de(cat["key"], res["key"])
            alcanzados.append(nivel)
            detalle[nivel.value] = detalle.get(nivel.value, 0) + res["doc_count"]

    tope = maxima(alcanzados)
    return {
        "conocida": True,
        "maximo_alcanzado": tope.value if tope else None,
        "eventos_por_nivel": detalle,
    }


def rafaga_en_la_ventana(
    evento: EventoDelBus, ventana_horas: int = VENTANA_RAFAGA_HORAS, es_url: str = queries.ES_URL
) -> dict[str, Any]:
    """How many *other* addresses were doing the same thing in the hours before this event.

    This is the one signal nothing else in the engine carries. The fingerprint families already say
    how many addresses ever ran a sequence, but over the whole corpus: forty addresses spread across
    three months is the background noise of the internet, and the same forty inside one hour is a
    coordinated push. Only the second is a reason to look harder, and only a time-boxed count can
    tell them apart.

    Two counts, because they answer different questions. The action-and-protocol count is always
    available and says whether this *kind* of traffic is spiking. The command count only exists for
    events that carry one, and is far more specific: the same byte-identical command from thirty
    addresses in an hour is not a coincidence.
    """
    desde = _restar_horas(evento.timestamp, ventana_horas)
    if not desde:
        return {"disponible": False, "motivo": "el evento no trae marca temporal utilizable"}

    # La ventana termina en el evento, no en ahora: ver el encabezado del módulo. Contar lo que pasó
    # después sería preguntarle al futuro si esto era una campaña.
    ventana: list[dict[str, Any]] = [
        {"range": {"@timestamp": {"gte": desde, "lt": evento.timestamp}}}
    ]

    aggs: dict[str, Any] = {
        "por_accion": {
            "filter": {
                "bool": {
                    "filter": [
                        {"term": {"event.action": evento.action}},
                        {"term": {"network.protocol": evento.protocol}},
                    ]
                }
            },
            "aggs": {"direcciones": {"cardinality": {"field": "source.ip"}}},
        }
    }
    if evento.command:
        # `process.command_line` está mapeado como `wildcard`, que admite `term` exacto.
        aggs["por_comando"] = {
            "filter": {"term": {"process.command_line": evento.command}},
            "aggs": {"direcciones": {"cardinality": {"field": "source.ip"}}},
        }

    r = _buscar({"size": 0, "query": {"bool": {"filter": ventana}}, "aggs": aggs}, es_url)
    agg = r["aggregations"]

    salida: dict[str, Any] = {
        "disponible": True,
        "ventana_horas": ventana_horas,
        "misma_accion": {
            "eventos": agg["por_accion"]["doc_count"],
            "direcciones": int(agg["por_accion"]["direcciones"]["value"]),
        },
    }
    if "por_comando" in agg:
        salida["mismo_comando"] = {
            "eventos": agg["por_comando"]["doc_count"],
            "direcciones": int(agg["por_comando"]["direcciones"]["value"]),
        }
    return salida


def arquetipos_del_corpus() -> dict[str, Any] | None:
    """The population baseline: how the observed addresses divide by behaviour.

    Not about this event — about everything, which is exactly what makes it useful. "Ran commands
    and got in" reads as ordinary until you know that only 1,5 % of addresses ever get there. It is
    the denominator that turns an observation into a severity.
    """
    datos = arquetipos.load()
    if datos is None:
        return None
    return {
        "direcciones_analizadas": datos["direcciones_analizadas"],
        "grupos": [
            {
                "nombre": p["nombre"],
                "porcentaje": p["porcentaje"],
                "pct_ejecuto_comandos": p["pct_ejecuto_comandos"],
                "pct_logro_acceso": p["pct_logro_acceso"],
                "pct_descargo_archivo": p["pct_descargo_archivo"],
            }
            for p in datos.get("perfiles", [])
        ],
    }


# El catálogo, para que el nodo de inferencia lo publique al proveedor sin repetir la lista. El
# orden es el de uso: primero lo del evento, después lo del corpus.
CATALOGO: dict[str, Any] = {
    "historial_de_direccion": historial_de_direccion,
    "comandos_de_la_sesion": comandos_de_la_sesion,
    "familia_de_la_sesion": familia_de_la_sesion,
    "origen_de_direccion": origen_de_direccion,
    "arquetipos_del_corpus": arquetipos_del_corpus,
}
