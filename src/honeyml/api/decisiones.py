"""Las decisiones del motor, y el veredicto de quien opera el panel sobre ellas.

Todo lo de este módulo lee, salvo una cosa. La telemetría y las decisiones del motor no se escriben
nunca desde la API. La única escritura es el veredicto del analista, y va a un índice propio,
`honeyml-revisiones`, bajo el mismo `doc_id` del evento. La decisión del motor queda intacta al
lado: para medir después en qué se equivocó el motor hacen falta las dos.

Pendiente de revisión es lo que el motor no pudo concluir, o concluyó con alguna consulta del
contexto fallida (`ciclo.requiere_revision`), y todavía no tiene veredicto. Sobre esas la decisión
final la toma el analista. Cualquier otra también se puede revisar, porque el analista puede no
estar de acuerdo con una que el motor dio por buena.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..agent.graph import CONTEXTO, HISTORIAL, INFERENCIA, MEMORIA, PERSISTENCIA, VALIDACION
from ..agent.severidad import ORDEN, Severidad
from ..education.annotations import TACTICAS_OBSERVABLES
from . import queries

DECISIONES = "honeyml-decisiones"
REVISIONES = "honeyml-revisiones"
NO_EXISTE = 404

# La muestra estratificada por conducta que se revisa a ciegas. La arma `make muestra` y la API
# solo la lee.
MUESTRA_FILE = Path("data/processed/muestra_de_revision.json")

# Cómo se nombra en los filtros una decisión sin táctica. Un valor que ninguna táctica real puede
# tener, así el panel filtra por "sin táctica" con el mismo parámetro que por cualquier otra.
SIN_TACTICA = "ninguna"

# Tope de una página del listado. El panel pide de a 25; esto evita que un pedido a mano traiga el
# índice entero de una vez.
MAX_TAMANO = 100

# Tope de una exportación: la ventana de resultados de Elasticsearch. Más allá de ese número una
# exportación deja de leerse como reporte, y el filtro es la forma de acotarla.
MAX_EXPORTACION = 10_000

# Ventana del tiempo de conclusión. Mide el motor en marcha continua: las decisiones de una tanda
# sobre el atraso tardan días por construcción, y mezcladas arruinarían la mediana.
VENTANA_CONCLUSION = "now-7d"

# Los atributos normalizados que se muestran del evento, en el orden en que se leen. Se eligen en
# lugar de devolver el documento entero porque la mitad son campos de servicio (versión de ECS,
# etiquetas del pipeline, coordenadas) que no ayudan a revisar una clasificación.
CAMPOS_DEL_EVENTO = (
    "@timestamp",
    "honeypot",
    "event.category",
    "event.action",
    "event.outcome",
    "event.dataset",
    "source.ip",
    "source.port",
    "source.geo.country_name",
    "source.geo.city_name",
    "source.as.organization.name",
    "source.as.number",
    "destination.port",
    "network.protocol",
    "network.transport",
    "user.name",
    "cowrie.password",
    "dionaea.password",
    "cowrie.session",
    "process.command_line",
    "url.original",
    "file.name",
    "file.hash.sha256",
    "message",
)


class Veredicto(BaseModel):
    """Lo que el analista decide sobre una decisión del motor.

    `confirma` da por buena la clasificación del motor y no lleva otra. `corrige` trae la
    clasificación completa que corresponde: la severidad es obligatoria, y una táctica nula quiere
    decir que no aplica ninguna. La táctica sale del mismo vocabulario que el motor, porque una
    corrección con un nombre que el motor no puede asignar no se podría comparar con nada.
    """

    model_config = ConfigDict(extra="forbid")

    veredicto: Literal["confirma", "corrige"]
    severidad: Severidad | None = None
    tactica_mitre: str | None = None
    nota: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def _coherente(self) -> Veredicto:
        if self.veredicto == "confirma" and (self.severidad or self.tactica_mitre):
            raise ValueError(
                "una confirmación no lleva clasificación propia: confirma la del motor"
            )
        if self.veredicto == "corrige" and self.severidad is None:
            raise ValueError("una corrección tiene que decir qué severidad corresponde")
        _exigir_vocabulario(self.tactica_mitre)
        return self


class ClasificacionACiegas(BaseModel):
    """Lo que el analista elige sin haber visto la clasificación del motor.

    Lleva siempre la clasificación completa, también cuando termina coincidiendo con la del motor:
    es la referencia contra la que se mide, y una coincidencia elegida a ciegas es un dato, no una
    confirmación. Una táctica nula quiere decir que no aplica ninguna.
    """

    model_config = ConfigDict(extra="forbid")

    severidad: Severidad
    tactica_mitre: str | None = None
    nota: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def _en_el_vocabulario(self) -> ClasificacionACiegas:
        _exigir_vocabulario(self.tactica_mitre)
        return self


def _exigir_vocabulario(tactica: str | None) -> None:
    if tactica and tactica not in TACTICAS_OBSERVABLES:
        admitidas = ", ".join(TACTICAS_OBSERVABLES)
        raise ValueError(f"táctica '{tactica}' fuera del vocabulario: {admitidas}")


class SinClasificacionError(ValueError):
    """Se quiso confirmar una decisión en la que el motor no llegó a clasificar nada."""


class RevisadaACiegasError(ValueError):
    """Se quiso reemplazar una revisión a ciegas con un veredicto común."""


class SinMuestraError(RuntimeError):
    """No hay muestra de revisión generada."""


def _pedir(
    metodo: str, ruta: str, cuerpo: dict[str, Any] | None = None, es_url: str = queries.ES_URL
) -> dict[str, Any]:
    pedido = urllib.request.Request(
        f"{es_url}{ruta}",
        data=json.dumps(cuerpo, ensure_ascii=False).encode() if cuerpo is not None else None,
        headers={"Content-Type": "application/json"},
        method=metodo,
    )
    with urllib.request.urlopen(pedido, timeout=60) as resp:
        resultado: dict[str, Any] = json.load(resp)
        return resultado


def _buscar(indice: str, cuerpo: dict[str, Any], es_url: str) -> dict[str, Any] | None:
    """Una búsqueda que devuelve None si el índice no existe, que en una instalación nueva es
    lo normal para las revisiones."""
    try:
        return queries._search(cuerpo, es_url, index=indice)
    except urllib.error.HTTPError as exc:
        if exc.code == NO_EXISTE:
            return None
        raise


def _documento(indice: str, doc_id: str, es_url: str) -> dict[str, Any] | None:
    try:
        r = _pedir("GET", f"/{indice}/_doc/{urllib.parse.quote(doc_id, safe='')}", es_url=es_url)
    except urllib.error.HTTPError as exc:
        if exc.code == NO_EXISTE:
            return None
        raise
    fuente: dict[str, Any] = r["_source"]
    return fuente


def ids_revisados(es_url: str = queries.ES_URL) -> list[str]:
    """Los `doc_id` que ya tienen veredicto. Son pocos: los escribe una persona, de a uno."""
    r = _buscar(REVISIONES, {"size": 10000, "_source": False}, es_url)
    return [h["_id"] for h in r["hits"]["hits"]] if r else []


def _cubos(agg: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"key": b["key"], "count": b["doc_count"]} for b in agg["buckets"]]


def resumen(es_url: str = queries.ES_URL) -> dict[str, Any]:
    """Los números del motor: cuánto decidió, cómo, a qué costo y cuánto espera revisión."""
    revisados = ids_revisados(es_url)
    cuerpo = {
        "size": 0,
        "track_total_hits": True,
        # Cuánto tardó en concluirse cada evento, desde que ocurrió hasta que se guardó la
        # decisión. Se calcula al consultar porque es la resta de dos campos que ya están.
        "runtime_mappings": {
            "demora_ms": {
                "type": "long",
                "script": {
                    "source": (
                        "if (doc['evento.momento'].size() == 0) return; "
                        "emit(doc['@timestamp'].value.toInstant().toEpochMilli() "
                        "- doc['evento.momento'].value.toInstant().toEpochMilli());"
                    )
                },
            }
        },
        "aggs": {
            "severidad": {"terms": {"field": "decision.severidad", "size": 10}},
            "tactica": {
                "terms": {"field": "decision.tactica_mitre", "size": 20, "missing": SIN_TACTICA}
            },
            "sensor": {"terms": {"field": "evento.sensor", "size": 5}},
            "modelo": {"terms": {"field": "modelo.nombre", "size": 10}},
            "copiadas": {"filter": {"exists": {"field": "ciclo.reutilizada_de"}}},
            "corregidas_por_el_motor": {"filter": {"range": {"ciclo.rechazos": {"gt": 0}}}},
            "no_concluyentes": {"filter": {"term": {"decision.concluyente": False}}},
            "costo": {"sum": {"field": "modelo.costo_usd"}},
            "requieren_revision": {
                "filter": {"term": {"ciclo.requiere_revision": True}},
                "aggs": {"ya_revisadas": {"filter": {"ids": {"values": revisados}}}},
            },
            # Si el motor está trabajando: cuándo decidió por última vez, cuánto en la última hora y
            # cómo se repartió minuto a minuto, sin contar lo vuelto a triar. Los minutos vacíos
            # vienen igual, así el gráfico del panel no junta dos ráfagas separadas por un silencio.
            "en_vivo": {
                "filter": {"bool": {"must_not": [{"term": {"ciclo.retriaje": True}}]}},
                "aggs": {
                    "ultima": {"max": {"field": "@timestamp"}},
                    "hora": {
                        "filter": {"range": {"@timestamp": {"gte": "now-1h"}}},
                        "aggs": {
                            "copiadas": {"filter": {"exists": {"field": "ciclo.reutilizada_de"}}},
                            "por_minuto": {
                                "date_histogram": {
                                    "field": "@timestamp",
                                    "fixed_interval": "1m",
                                    "min_doc_count": 0,
                                    "extended_bounds": {"min": "now-59m/m", "max": "now/m"},
                                },
                                "aggs": {
                                    "copiadas": {
                                        "filter": {"exists": {"field": "ciclo.reutilizada_de"}}
                                    }
                                },
                            },
                        },
                    },
                },
            },
            # Solo lo que decidió el motor al consumir el bus. Una decisión que se volvió a triar
            # tiene la marca temporal del retriaje sobre un evento que pudo ocurrir semanas antes,
            # y una sola tanda así lleva la mediana a días. La media va junto a la mediana porque la
            # métrica de conclusión se define como tiempo medio; la mediana dice lo típico y la
            # media deja ver si hay colas largas.
            "conclusion": {
                "filter": {
                    "bool": {
                        "filter": [{"range": {"@timestamp": {"gte": VENTANA_CONCLUSION}}}],
                        "must_not": [{"term": {"ciclo.retriaje": True}}],
                    }
                },
                "aggs": {
                    "percentiles": {"percentiles": {"field": "demora_ms", "percents": [50, 90]}},
                    "media": {"avg": {"field": "demora_ms"}},
                },
            },
        },
    }
    r = queries._search(cuerpo, es_url, index=DECISIONES)
    a = r["aggregations"]
    total = r["hits"]["total"]["value"]
    copiadas = a["copiadas"]["doc_count"]
    requieren = a["requieren_revision"]["doc_count"]

    orden = {nivel.value: i for i, nivel in enumerate(ORDEN)}
    severidad = sorted(_cubos(a["severidad"]), key=lambda c: orden.get(c["key"], -1))

    veredictos = _buscar(
        REVISIONES, {"size": 0, "aggs": {"v": {"terms": {"field": "veredicto"}}}}, es_url
    )
    por_veredicto: dict[str, int] = {}
    if veredictos is not None:
        por_veredicto = {c["key"]: c["count"] for c in _cubos(veredictos["aggregations"]["v"])}

    pct = a["conclusion"]["percentiles"]["values"]
    return {
        "total": total,
        "razonadas": total - copiadas,
        "copiadas": copiadas,
        "corregidas_por_el_motor": a["corregidas_por_el_motor"]["doc_count"],
        "no_concluyentes": a["no_concluyentes"]["doc_count"],
        "costo_usd": round(a["costo"]["value"], 4),
        "por_severidad": severidad,
        "por_tactica": _cubos(a["tactica"]),
        "por_sensor": _cubos(a["sensor"]),
        "por_modelo": _cubos(a["modelo"]),
        "revision": {
            "requieren": requieren,
            "pendientes": requieren - a["requieren_revision"]["ya_revisadas"]["doc_count"],
            "revisadas": len(revisados),
            "confirmadas": por_veredicto.get("confirma", 0),
            "corregidas": por_veredicto.get("corrige", 0),
        },
        "actividad": {
            "ultima": a["en_vivo"]["ultima"].get("value_as_string"),
            "ultima_hora": a["en_vivo"]["hora"]["doc_count"],
            "copiadas_ultima_hora": a["en_vivo"]["hora"]["copiadas"]["doc_count"],
            "por_minuto": [
                {
                    "minuto": c.get("key_as_string"),
                    "decisiones": c["doc_count"],
                    "copiadas": c["copiadas"]["doc_count"],
                }
                for c in a["en_vivo"]["hora"].get("por_minuto", {}).get("buckets", [])
            ],
        },
        "conclusion": {
            "ventana_dias": 7,
            "decisiones": a["conclusion"]["doc_count"],
            "mediana_s": _segundos(pct.get("50.0")),
            "p90_s": _segundos(pct.get("90.0")),
            "media_s": _segundos(a["conclusion"].get("media", {}).get("value")),
        },
    }


def _segundos(ms: float | None) -> float | None:
    return round(ms / 1000, 1) if ms is not None else None


def _filtros(
    severidad: str | None,
    tactica: str | None,
    sensor: str | None,
    estado: str,
    revisados: list[str],
) -> dict[str, Any]:
    filtro: list[dict[str, Any]] = []
    excluir: list[dict[str, Any]] = []
    if severidad:
        filtro.append({"term": {"decision.severidad": severidad}})
    if tactica == SIN_TACTICA:
        excluir.append({"exists": {"field": "decision.tactica_mitre"}})
    elif tactica:
        filtro.append({"term": {"decision.tactica_mitre": tactica}})
    if sensor:
        filtro.append({"term": {"evento.sensor": sensor}})
    if estado == "pendientes":
        filtro.append({"term": {"ciclo.requiere_revision": True}})
        excluir.append({"ids": {"values": revisados}})
    elif estado == "revisadas":
        filtro.append({"ids": {"values": revisados}})
    return {"bool": {"filter": filtro, "must_not": excluir}}


def camino(d: dict[str, Any]) -> list[str]:
    """Por qué nodos del grafo pasó esta decisión, en orden, con las vueltas incluidas.

    No se guarda: se deduce de lo que la persistencia ya escribe. Una copia del repertorio salió
    por el atajo de memoria; un corte por falta de contexto, por el de contexto; y el resto recorrió
    el ciclo completo, con un par inferencia y validación por cada intento. Es lo que el panel usa
    para dibujar el recorrido de cada decisión sobre el grafo.
    """
    ciclo = d.get("ciclo", {})
    if ciclo.get("reutilizada_de"):
        return [MEMORIA, PERSISTENCIA]
    if ciclo.get("motivo_de_corte") == "sin_contexto":
        return [MEMORIA, CONTEXTO, PERSISTENCIA]
    vueltas = max(int(ciclo.get("intentos") or 0), 1)
    return [MEMORIA, CONTEXTO, HISTORIAL, *[INFERENCIA, VALIDACION] * vueltas, PERSISTENCIA]


def _fila(doc_id: str, d: dict[str, Any], revision: dict[str, Any] | None) -> dict[str, Any]:
    """Una decisión como la muestra el listado: lo justo para decidir si abrirla."""
    evento, decision, ciclo = d.get("evento", {}), d.get("decision", {}), d.get("ciclo", {})
    modelo = d.get("modelo") or {}
    return {
        "doc_id": doc_id,
        "momento": evento.get("momento"),
        "decidida": d.get("@timestamp"),
        "sensor": evento.get("sensor"),
        "categoria": evento.get("categoria"),
        "resultado": evento.get("resultado"),
        "protocolo": evento.get("protocolo"),
        "origen": evento.get("origen"),
        "resumen": evento.get("resumen"),
        "severidad": decision.get("severidad"),
        "tactica_mitre": decision.get("tactica_mitre"),
        "confianza": decision.get("confianza"),
        "concluyente": decision.get("concluyente"),
        "copiada": bool(ciclo.get("reutilizada_de")),
        "requiere_revision": bool(ciclo.get("requiere_revision")),
        "consultas_fallidas": ciclo.get("consultas_fallidas") or [],
        "intentos": int(ciclo.get("intentos") or 0),
        "rechazos": int(ciclo.get("rechazos") or 0),
        "motivo_de_corte": ciclo.get("motivo_de_corte"),
        "retriaje": bool(ciclo.get("retriaje")),
        "modelo": modelo.get("nombre"),
        "segundos": modelo.get("segundos"),
        "costo_usd": modelo.get("costo_usd"),
        "camino": camino(d),
        "revision": revision,
    }


def listar(
    severidad: str | None = None,
    tactica: str | None = None,
    sensor: str | None = None,
    estado: str = "todas",
    desde: int = 0,
    tamano: int = 25,
    orden: str = "evento",
    razonadas: bool = False,
    es_url: str = queries.ES_URL,
) -> dict[str, Any]:
    """Las decisiones, de la más reciente a la más vieja.

    Por defecto el orden es el del momento del evento, que es como se revisa. Con `orden="decision"`
    es el de cuándo decidió el motor, que es lo que muestra el panel en vivo, y ahí se dejan afuera
    las decisiones vueltas a triar: no las tomó el motor al consumir el bus.

    Con `razonadas` quedan solo las que pasaron por el modelo. Son una de cada cien, y sin el filtro
    el panel casi nunca tendría una para mostrar el ciclo completo.
    """
    revisados = ids_revisados(es_url)
    consulta = _filtros(severidad, tactica, sensor, estado, revisados)
    campo = "evento.momento"
    if orden == "decision":
        campo = "@timestamp"
        consulta["bool"]["must_not"].append({"term": {"ciclo.retriaje": True}})
    if razonadas:
        consulta["bool"]["must_not"].append({"exists": {"field": "ciclo.reutilizada_de"}})
    cuerpo = {
        "from": max(desde, 0),
        "size": min(max(tamano, 1), MAX_TAMANO),
        "track_total_hits": True,
        "query": consulta,
        "sort": [{campo: {"order": "desc", "missing": "_last"}}],
    }
    r = queries._search(cuerpo, es_url, index=DECISIONES)
    hits = r["hits"]["hits"]

    revisiones: dict[str, dict[str, Any]] = {}
    con_veredicto = set(revisados)
    ids = [h["_id"] for h in hits if h["_id"] in con_veredicto]
    if ids:
        m = _pedir("POST", f"/{REVISIONES}/_mget", {"ids": ids}, es_url)
        revisiones = {d["_id"]: d["_source"] for d in m["docs"] if d.get("found")}

    return {
        "total": r["hits"]["total"]["value"],
        "items": [_fila(h["_id"], h["_source"], revisiones.get(h["_id"])) for h in hits],
    }


def para_exportar(
    severidad: str | None = None,
    tactica: str | None = None,
    sensor: str | None = None,
    estado: str = "todas",
    es_url: str = queries.ES_URL,
) -> dict[str, Any]:
    """Las decisiones de un filtro para un reporte, con el mismo orden y las mismas filas que el
    listado, hasta `MAX_EXPORTACION`. `total` dice cuántas había, por si quedó alguna afuera."""
    revisados = ids_revisados(es_url)
    cuerpo = {
        "size": MAX_EXPORTACION,
        "track_total_hits": True,
        "query": _filtros(severidad, tactica, sensor, estado, revisados),
        "sort": [{"evento.momento": {"order": "desc", "missing": "_last"}}],
    }
    r = queries._search(cuerpo, es_url, index=DECISIONES)
    hits = r["hits"]["hits"]
    con_veredicto = set(revisados)
    ids = [h["_id"] for h in hits if h["_id"] in con_veredicto]
    revisiones: dict[str, dict[str, Any]] = {}
    if ids:
        m = _pedir("POST", f"/{REVISIONES}/_mget", {"ids": ids}, es_url)
        revisiones = {d["_id"]: d["_source"] for d in m["docs"] if d.get("found")}
    return {
        "total": r["hits"]["total"]["value"],
        "items": [_fila(h["_id"], h["_source"], revisiones.get(h["_id"])) for h in hits],
    }


def revisiones(es_url: str = queries.ES_URL) -> list[dict[str, Any]]:
    """Todos los veredictos, del más nuevo al más viejo. Son pocos: los escribe una persona."""
    r = _buscar(REVISIONES, {"size": 10000, "sort": [{"@timestamp": {"order": "desc"}}]}, es_url)
    return [{"doc_id": h["_id"], **h["_source"]} for h in r["hits"]["hits"]] if r else []


def _aplanar(d: dict[str, Any], prefijo: str = "") -> dict[str, Any]:
    plano: dict[str, Any] = {}
    for clave, valor in d.items():
        if isinstance(valor, dict):
            plano.update(_aplanar(valor, f"{prefijo}{clave}."))
        else:
            plano[f"{prefijo}{clave}"] = valor
    return plano


def detalle(doc_id: str, es_url: str = queries.ES_URL) -> dict[str, Any] | None:
    """Todo lo que hace falta para revisar una decisión: ella, su evento y el veredicto, si hay.

    El evento se busca por identificador en los índices de telemetría. Puede no estar si esos
    índices se rotaron, y la decisión igual se lee sola: trae copiados los datos del evento.
    """
    decision = _documento(DECISIONES, doc_id, es_url)
    if decision is None:
        return None

    return {
        "doc_id": doc_id,
        "decision": decision,
        "camino": camino(decision),
        "evento": _atributos_del_evento(doc_id, es_url),
        "revision": _documento(REVISIONES, doc_id, es_url),
    }


def _atributos_del_evento(doc_id: str, es_url: str) -> dict[str, Any] | None:
    r = queries._search({"size": 1, "query": {"ids": {"values": [doc_id]}}}, es_url)
    if not r["hits"]["hits"]:
        return None
    plano = _aplanar(r["hits"]["hits"][0]["_source"])
    return {campo: plano[campo] for campo in CAMPOS_DEL_EVENTO if campo in plano}


def _lo_que_dijo_el_motor(decision: dict[str, Any]) -> dict[str, Any]:
    """La clasificación del motor tal como estaba, para guardarla al lado del veredicto."""
    del_motor = decision.get("decision", {})
    ciclo = decision.get("ciclo", {})
    return {
        "severidad": del_motor.get("severidad"),
        "tactica_mitre": del_motor.get("tactica_mitre"),
        "concluyente": del_motor.get("concluyente"),
        "requiere_revision": bool(ciclo.get("requiere_revision")),
        "consultas_fallidas": ciclo.get("consultas_fallidas") or [],
    }


def _guardar_revision(doc_id: str, documento: dict[str, Any], es_url: str) -> None:
    # `refresh=wait_for` para que el listado que el panel pide enseguida ya la cuente.
    _pedir(
        "PUT",
        f"/{REVISIONES}/_doc/{urllib.parse.quote(doc_id, safe='')}?refresh=wait_for",
        documento,
        es_url,
    )


def revisar(
    doc_id: str, veredicto: Veredicto, es_url: str = queries.ES_URL, usuario: str | None = None
) -> dict[str, Any] | None:
    """Guarda el veredicto del analista. None si el evento no tiene decisión del motor.

    Un segundo veredicto sobre la misma decisión reemplaza al anterior: vale lo último que decidió
    el analista. Junto al veredicto se guarda la clasificación del motor tal como estaba, porque el
    motor puede volver a triar el evento más adelante y la revisión tiene que seguir diciendo sobre
    qué se pronunció.
    """
    decision = _documento(DECISIONES, doc_id, es_url)
    if decision is None:
        return None

    if veredicto.veredicto == "confirma" and not decision.get("decision", {}).get("severidad"):
        raise SinClasificacionError(
            "El motor no llegó a clasificar este evento: no hay nada que confirmar. Corresponde "
            "corregir con la clasificación que el analista considere."
        )
    previa = _documento(REVISIONES, doc_id, es_url)
    if previa and previa.get("a_ciegas"):
        raise RevisadaACiegasError(
            "Esta decisión ya tiene una revisión a ciegas. Es la referencia con la que se mide el "
            "motor, y un veredicto tomado después de ver su clasificación no la reemplaza."
        )

    documento = (
        {"@timestamp": datetime.now(UTC).isoformat(timespec="seconds"), "doc_id": doc_id}
        | veredicto.model_dump(mode="json")
        | {"motor": _lo_que_dijo_el_motor(decision)}
    )
    if usuario:
        documento["usuario"] = usuario
    _guardar_revision(doc_id, documento, es_url)
    return documento


def _muestra() -> list[dict[str, Any]]:
    try:
        datos = json.loads(MUESTRA_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SinMuestraError("Falta la muestra de revisión. Generala con: make muestra") from exc
    conductas: list[dict[str, Any]] = datos.get("conductas", [])
    return conductas


def _revisadas_a_ciegas(ids: list[str], es_url: str) -> set[str]:
    if not ids:
        return set()
    consulta = {"bool": {"filter": [{"ids": {"values": ids}}, {"term": {"a_ciegas": True}}]}}
    r = _buscar(REVISIONES, {"size": len(ids), "_source": False, "query": consulta}, es_url)
    return {h["_id"] for h in r["hits"]["hits"]} if r else set()


def siguiente_a_ciegas(es_url: str = queries.ES_URL) -> dict[str, Any]:
    """La próxima conducta de la muestra que no tiene revisión a ciegas, sin lo que dijo el motor.

    La clasificación se saca acá y no en el panel: lo que no viaja no se puede ver por accidente.
    Tampoco viaja el estrato, porque dice si el motor escaló o no, que es justo lo que quien revisa
    no tiene que saber. El piso y el techo sí, porque salen de la evidencia y no del motor.
    """
    ids = [c["doc_id"] for c in _muestra()]
    hechas = _revisadas_a_ciegas(ids, es_url)
    progreso = {"total": len(ids), "revisadas": len(hechas)}
    for doc_id in ids:
        if doc_id in hechas:
            continue
        decision = _documento(DECISIONES, doc_id, es_url)
        if decision is None:
            continue
        evento = decision.get("evento", {})
        motor = decision.get("decision", {})
        campos = ("momento", "sensor", "categoria", "accion", "resultado", "protocolo", "resumen")
        return {
            **progreso,
            "terminada": False,
            "doc_id": doc_id,
            "evento": {campo: evento.get(campo) for campo in campos},
            "atributos": _atributos_del_evento(doc_id, es_url),
            "piso": motor.get("piso"),
            "techo": motor.get("techo"),
        }
    return {**progreso, "terminada": True}


def revisar_a_ciegas(
    doc_id: str,
    clasificacion: ClasificacionACiegas,
    es_url: str = queries.ES_URL,
    usuario: str | None = None,
) -> dict[str, Any] | None:
    """Guarda lo que el analista eligió a ciegas y lo compara con la clasificación del motor.

    El veredicto lo calcula el servidor: confirma si coinciden la severidad y la táctica, corrige si
    no. Así no depende de lo que el analista piense después de ver la respuesta del motor, que es
    lo que la revisión a ciegas existe para evitar. None si el evento no tiene decisión del motor.
    """
    decision = _documento(DECISIONES, doc_id, es_url)
    if decision is None:
        return None

    motor = _lo_que_dijo_el_motor(decision)
    coincide = clasificacion.severidad == motor["severidad"] and (
        clasificacion.tactica_mitre or None
    ) == (motor["tactica_mitre"] or None)
    try:
        estratos = {c["doc_id"]: c.get("estrato") for c in _muestra()}
    except SinMuestraError:
        estratos = {}

    documento = (
        {
            "@timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
            "doc_id": doc_id,
            "veredicto": "confirma" if coincide else "corrige",
        }
        | clasificacion.model_dump(mode="json")
        | {"a_ciegas": True, "estrato": estratos.get(doc_id), "motor": motor}
    )
    if usuario:
        documento["usuario"] = usuario
    _guardar_revision(doc_id, documento, es_url)
    return documento
