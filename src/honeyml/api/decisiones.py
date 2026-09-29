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
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..agent.severidad import ORDEN, Severidad
from ..education.annotations import TACTICAS_OBSERVABLES
from . import queries

DECISIONES = "honeyml-decisiones"
REVISIONES = "honeyml-revisiones"
NO_EXISTE = 404

# Cómo se nombra en los filtros una decisión sin táctica. Un valor que ninguna táctica real puede
# tener, así el panel filtra por "sin táctica" con el mismo parámetro que por cualquier otra.
SIN_TACTICA = "ninguna"

# Tope de una página del listado. El panel pide de a 25; esto evita que un pedido a mano traiga el
# índice entero de una vez.
MAX_TAMANO = 100

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
        if self.tactica_mitre and self.tactica_mitre not in TACTICAS_OBSERVABLES:
            admitidas = ", ".join(TACTICAS_OBSERVABLES)
            raise ValueError(f"táctica '{self.tactica_mitre}' fuera del vocabulario: {admitidas}")
        return self


class SinClasificacionError(ValueError):
    """Se quiso confirmar una decisión en la que el motor no llegó a clasificar nada."""


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
            # Solo lo que decidió el motor al consumir el bus. Una decisión que se volvió a triar
            # tiene la marca temporal del retriaje sobre un evento que pudo ocurrir semanas antes,
            # y una sola tanda así lleva la mediana a días.
            "conclusion": {
                "filter": {
                    "bool": {
                        "filter": [{"range": {"@timestamp": {"gte": VENTANA_CONCLUSION}}}],
                        "must_not": [{"term": {"ciclo.retriaje": True}}],
                    }
                },
                "aggs": {
                    "percentiles": {"percentiles": {"field": "demora_ms", "percents": [50, 90]}}
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
        "conclusion": {
            "ventana_dias": 7,
            "decisiones": a["conclusion"]["doc_count"],
            "mediana_s": _segundos(pct.get("50.0")),
            "p90_s": _segundos(pct.get("90.0")),
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


def _fila(doc_id: str, d: dict[str, Any], revision: dict[str, Any] | None) -> dict[str, Any]:
    """Una decisión como la muestra el listado: lo justo para decidir si abrirla."""
    evento, decision, ciclo = d.get("evento", {}), d.get("decision", {}), d.get("ciclo", {})
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
        "revision": revision,
    }


def listar(
    severidad: str | None = None,
    tactica: str | None = None,
    sensor: str | None = None,
    estado: str = "todas",
    desde: int = 0,
    tamano: int = 25,
    es_url: str = queries.ES_URL,
) -> dict[str, Any]:
    """Las decisiones, de la más reciente a la más vieja por momento del evento."""
    revisados = ids_revisados(es_url)
    cuerpo = {
        "from": max(desde, 0),
        "size": min(max(tamano, 1), MAX_TAMANO),
        "track_total_hits": True,
        "query": _filtros(severidad, tactica, sensor, estado, revisados),
        "sort": [{"evento.momento": {"order": "desc", "missing": "_last"}}],
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

    r = queries._search({"size": 1, "query": {"ids": {"values": [doc_id]}}}, es_url)
    evento: dict[str, Any] | None = None
    if r["hits"]["hits"]:
        plano = _aplanar(r["hits"]["hits"][0]["_source"])
        evento = {campo: plano[campo] for campo in CAMPOS_DEL_EVENTO if campo in plano}

    return {
        "doc_id": doc_id,
        "decision": decision,
        "evento": evento,
        "revision": _documento(REVISIONES, doc_id, es_url),
    }


def revisar(
    doc_id: str, veredicto: Veredicto, es_url: str = queries.ES_URL
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

    del_motor = decision.get("decision", {})
    ciclo = decision.get("ciclo", {})
    if veredicto.veredicto == "confirma" and not del_motor.get("severidad"):
        raise SinClasificacionError(
            "El motor no llegó a clasificar este evento: no hay nada que confirmar. Corresponde "
            "corregir con la clasificación que el analista considere."
        )

    propio = veredicto.model_dump(mode="json")
    documento = {
        "@timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
        "doc_id": doc_id,
        **propio,
        "motor": {
            "severidad": del_motor.get("severidad"),
            "tactica_mitre": del_motor.get("tactica_mitre"),
            "concluyente": del_motor.get("concluyente"),
            "requiere_revision": bool(ciclo.get("requiere_revision")),
            "consultas_fallidas": ciclo.get("consultas_fallidas") or [],
        },
    }
    # `refresh=wait_for` para que el listado que el panel pide enseguida ya la cuente.
    _pedir(
        "PUT",
        f"/{REVISIONES}/_doc/{urllib.parse.quote(doc_id, safe='')}?refresh=wait_for",
        documento,
        es_url,
    )
    return documento
