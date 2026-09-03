"""Qué puede consultar el motor de triaje mientras razona sobre un evento.

El mensaje del bus trae el disparador y nada más: una línea que dice que una dirección ejecutó un
comando. Para saber si eso importa hacen falta las circunstancias, y estas son las consultas que las
responden: si esa dirección ya estuvo antes, qué más hizo en la misma sesión, si la secuencia es una
que el corpus ya vio mil veces.

Hay tres propiedades y las tres sostienen algo.

Son de solo lectura. Nada de acá escribe, borra ni sale de los datos del propio proyecto. No es
prolijidad: la entrada es texto controlado por el atacante. Un comando capturado por el señuelo
puede decir cualquier cosa, incluidas instrucciones dirigidas a lo que sea que lo lea, y entra al
contexto del modelo por diseño. Un motor cuya caja de herramientas son puras consultas no puede ser
convencido de hacer daño, porque no hay daño disponible. Lo que actúe sobre el mundo va afuera de
este módulo y detrás de una persona.

Son acotadas. Cada consulta tiene tope. Una sesión del corpus corrió 1.400 comandos, y entregada
entera desplazaría al resto del contexto y se paga por token. Los topes son las constantes de abajo.

Y están cortadas en la marca temporal del propio evento. Historial significa lo que se sabía antes
de este evento, no todo lo que hay en el índice hoy. Sin el corte, el motor juzga un evento temprano
con evidencia posterior, puntúa mejor de lo que jamás podría en vivo, y la campaña de validación
adversaria termina midiendo un sistema que no puede existir. El horizonte es parámetro obligatorio
de toda consulta histórica.
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
# con una ventana de un día el conteo se llena del tráfico de fondo (unos treinta mil eventos
# diarios) y deja de distinguir nada. Con una hora, una campaña lenta pasa desapercibida.
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
    """Qué había hecho ya esta dirección antes de `hasta`.

    `hasta` es el horizonte y es obligatorio por lo que dice el encabezado del módulo: una dirección
    cuya primera aparición es el evento que se está juzgando no se parece en nada a una que viene
    intentando hace tres semanas, y solo la segunda es un hecho que el motor podía saber entonces.
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
    """Los comandos de esta sesión, en orden, hasta el horizonte.

    Si viene `hasta`, también corta ahí: lo que interesa de la secuencia es lo que llevó al evento,
    e incluir lo que pasó después dejaría al motor razonando desde el final hacia atrás.
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
    """A qué familia de huellas publicada pertenece esta secuencia exacta de comandos, si a alguna.

    La coincidencia es byte a byte, el mismo criterio estricto con el que se armaron las familias.
    Que algo se parezca mucho no cuenta como coincidencia, y es a propósito: el valor de esta
    consulta es que un acierto significa "otras 5.514 sesiones hicieron exactamente esto", y una
    coincidencia difusa no significaría eso.
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
    """País y red que opera una dirección, tal como los dejó el enriquecimiento del pipeline.

    La red dice más que el país, y la sección del panel explica por qué: una dirección alquilada en
    un centro de datos y una conexión hogareña son cosas distintas que comparten bandera. Se
    informan las dos para que el motor las pese, y ninguna de las dos es atribución.
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
    """Hasta dónde había llegado esta dirección en la escala, antes de este evento.

    `historial_de_direccion` cuenta qué hizo; esto dice hasta dónde llegó. Es la diferencia sobre la
    que está construida la escala de severidad: una dirección con nueve mil eventos previos que
    nunca pasó de una pantalla de credenciales es otra cosa que una que ejecutó comandos el martes
    pasado, y el conteo crudo no las distingue.

    Devuelve los pares (categoría, resultado) que produjo antes del horizonte, cada uno pasado por
    la misma regla de piso con la que se juzga al motor, así que "ya alcanzó ALTO" significa lo
    mismo que en el resto del motor y no algo que esta función se inventó.
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
    """Cuántas otras direcciones estaban haciendo lo mismo en las horas previas a este evento.

    Es la única señal que no aporta ninguna otra parte del motor. Las familias de huellas ya dicen
    cuántas direcciones corrieron alguna vez una secuencia, pero sobre todo el corpus: cuarenta
    direcciones repartidas en tres meses son el ruido de fondo de internet, y esas mismas cuarenta
    dentro de una hora son un empuje coordinado. Solo lo segundo amerita mirar más de cerca, y solo
    un conteo acotado en el tiempo las distingue.

    Van dos conteos porque contestan preguntas distintas. El de acción y protocolo está siempre
    disponible y dice si ese tipo de tráfico está en pico. El de comando existe solo para los
    eventos que traen uno, y es mucho más específico: el mismo comando byte a byte desde treinta
    direcciones en una hora no es casualidad.
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
    """La línea base de la población: cómo se reparten por conducta las direcciones observadas.

    No habla de este evento sino de todos, que es justamente lo que lo hace útil. "Ejecutó comandos
    y entró" se lee como algo común hasta que uno sabe que solo el 1,5 % de las direcciones llega
    ahí. Es el denominador el que convierte una observación en una severidad.
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
