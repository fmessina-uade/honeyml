"""El nodo de recuperación histórica y las tres consultas sobre las que se apoya.

La intención es la misma que en los otros archivos de pruebas del paquete: fijar las decisiones que
un refactor se llevaría puestas en silencio si nadie las escribió. Acá hay cuatro.

La ventana de ráfaga y los precedentes terminan en el evento y nunca en "ahora": contar lo que pasó
después sería preguntarle al futuro si esto era una campaña. La trayectoria se ordena por la misma
regla de piso con la que se juzga al motor, y no por una segunda opinión que viva adentro de la
herramienta. Un problema del almacén de decisiones se anota y no corta el ciclo, porque no es
Elasticsearch caído. Y el nodo suma al contexto en vez de reemplazarlo, así lo que encontró el nodo
anterior sobrevive.
"""

from __future__ import annotations

from email.message import Message
from typing import Any
from urllib.error import HTTPError, URLError

import pytest

from honeyml.agent import tools
from honeyml.agent.consumer import EventoDelBus
from honeyml.agent.nodes import historial as nodo
from honeyml.agent.severidad import Severidad
from honeyml.agent.state import Contexto

# La consulta real, guardada antes de que el reemplazo automático de abajo la tape en cada prueba.
precedentes_de_direccion = tools.precedentes_de_direccion


def _evento(**kw: Any) -> EventoDelBus:
    base = {
        "entry_id": "1-0",
        "doc_id": "abc123",
        "timestamp": "2026-08-20T10:00:00Z",
        "honeypot": "cowrie",
        "category": "process",
        "action": "command",
        "protocol": "ssh",
        "source_ip": "203.0.113.7",
        "session": "s1",
        "command": "uname -a",
    }
    base.update(kw)
    return EventoDelBus(**base)  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def _sin_almacen(monkeypatch: pytest.MonkeyPatch) -> None:
    """Las pruebas del nodo no tienen Elasticsearch: los precedentes vuelven vacíos salvo que una
    prueba los reemplace."""
    monkeypatch.setattr(tools, "precedentes_de_direccion", lambda ip, h: {"decisiones": 0})


def _estado(**kw: Any) -> Any:
    return {
        "evento": _evento(),
        "contexto": Contexto(doc_id="abc123", resumen="x", hallazgos={"origen": {"pais": "BG"}}),
        **kw,
    }


# Ráfaga


def test_la_ventana_termina_en_el_evento_y_no_en_ahora(monkeypatch: pytest.MonkeyPatch) -> None:
    """Contar lo posterior sería preguntarle al futuro si esto era una campaña."""
    capturado: dict[str, Any] = {}

    def falsa(body: dict[str, Any], es_url: str = "") -> dict[str, Any]:
        capturado.update(body)
        return {
            "aggregations": {
                "por_accion": {"doc_count": 0, "direcciones": {"value": 0}},
                "por_comando": {"doc_count": 0, "direcciones": {"value": 0}},
            }
        }

    monkeypatch.setattr(tools, "_buscar", falsa)
    tools.rafaga_en_la_ventana(_evento(), ventana_horas=6)

    rango = capturado["query"]["bool"]["filter"][0]["range"]["@timestamp"]
    assert rango["lt"] == "2026-08-20T10:00:00Z"
    assert rango["gte"] == "2026-08-20T04:00:00Z"


def test_un_evento_sin_comando_no_pregunta_por_comando(monkeypatch: pytest.MonkeyPatch) -> None:
    capturado: dict[str, Any] = {}

    def falsa(body: dict[str, Any], es_url: str = "") -> dict[str, Any]:
        capturado.update(body)
        return {"aggregations": {"por_accion": {"doc_count": 3, "direcciones": {"value": 2}}}}

    monkeypatch.setattr(tools, "_buscar", falsa)
    r = tools.rafaga_en_la_ventana(_evento(category="authentication", command=""))

    assert "por_comando" not in capturado["aggs"]
    assert "mismo_comando" not in r
    assert r["misma_accion"] == {"eventos": 3, "direcciones": 2}


def test_una_marca_temporal_ilegible_no_tira_el_ciclo() -> None:
    r = tools.rafaga_en_la_ventana(_evento(timestamp="no es una fecha"))
    assert r["disponible"] is False
    assert "motivo" in r


# Trayectoria


def test_la_trayectoria_usa_el_mismo_piso_que_juzga_al_motor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Una dirección que ya ejecutó comandos alcanzó ALTO, con la misma regla que todo lo demás."""

    def falsa(body: dict[str, Any], es_url: str = "") -> dict[str, Any]:
        return {
            "hits": {"total": {"value": 40}},
            "aggregations": {
                "categorias": {
                    "buckets": [
                        {
                            "key": "authentication",
                            "resultados": {"buckets": [{"key": "success", "doc_count": 3}]},
                        },
                        {
                            "key": "process",
                            "resultados": {"buckets": [{"key": "unknown", "doc_count": 37}]},
                        },
                    ]
                }
            },
        }

    monkeypatch.setattr(tools, "_buscar", falsa)
    r = tools.trayectoria_de_direccion("203.0.113.7", "2026-08-20T10:00:00Z")

    assert r["maximo_alcanzado"] == Severidad.ALTO.value
    assert r["eventos_por_nivel"] == {Severidad.MEDIO.value: 3, Severidad.ALTO.value: 37}


def test_una_direccion_nueva_se_declara_desconocida(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        tools,
        "_buscar",
        lambda b, e="": {
            "hits": {"total": {"value": 0}},
            "aggregations": {"categorias": {"buckets": []}},
        },
    )
    assert tools.trayectoria_de_direccion("203.0.113.7", "2026-08-20T10:00:00Z") == {
        "conocida": False
    }


def test_sin_horizonte_no_se_consulta() -> None:
    """El corte temporal es obligatorio: sin él la consulta miraría todo el índice actual."""
    assert tools.trayectoria_de_direccion("203.0.113.7", "")["conocida"] is False


# Precedentes


def _respuesta(total: int, niveles: dict[str, int], tacticas: dict[str, int]) -> dict[str, Any]:
    def cubos(d: dict[str, int]) -> dict[str, Any]:
        return {"buckets": [{"key": k, "doc_count": v} for k, v in d.items()]}

    return {
        "hits": {"total": {"value": total}},
        "aggregations": {
            "niveles": cubos(niveles),
            "tacticas": cubos(tacticas),
            "ultima": {"value_as_string": "2026-08-19T22:00:00.000Z"},
        },
    }


def test_los_precedentes_se_cortan_en_el_evento(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un evento triado tarde no puede ver las decisiones de los que ocurrieron después."""
    capturado: dict[str, Any] = {}

    def falsa(body: dict[str, Any], es_url: str = "", index: str = "") -> dict[str, Any]:
        capturado.update(body=body, index=index)
        return _respuesta(0, {}, {})

    monkeypatch.setattr(tools, "_buscar", falsa)
    precedentes_de_direccion("203.0.113.7", "2026-08-20T10:00:00Z")

    filtros = capturado["body"]["query"]["bool"]["filter"]
    assert {"term": {"evento.origen": "203.0.113.7"}} in filtros
    assert {"range": {"evento.momento": {"lt": "2026-08-20T10:00:00Z"}}} in filtros
    assert capturado["index"] == "honeyml-decisiones"


def test_los_precedentes_resumen_niveles_y_tacticas(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        tools,
        "_buscar",
        lambda b, e="", index="": _respuesta(
            5, {"medio": 3, "alto": 2}, {"Ejecución": 2, "Acceso inicial": 3}
        ),
    )
    r = precedentes_de_direccion("203.0.113.7", "2026-08-20T10:00:00Z")

    assert r["decisiones"] == 5
    assert r["maximo_decidido"] == Severidad.ALTO.value
    assert r["por_nivel"] == {"medio": 3, "alto": 2}
    assert r["tacticas"] == {"Ejecución": 2, "Acceso inicial": 3}


def test_sin_indice_de_decisiones_no_hay_precedentes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Una instalación que todavía no decidió nada no tiene el índice, y eso no es una falla."""

    def no_existe(*_: Any, **__: Any) -> Any:
        raise HTTPError("http://es/honeyml-decisiones/_search", 404, "Not Found", Message(), None)

    monkeypatch.setattr(tools, "_buscar", no_existe)
    assert precedentes_de_direccion("203.0.113.7", "2026-08-20T10:00:00Z") == {"decisiones": 0}


def test_otro_error_del_indice_no_se_confunde_con_elasticsearch_caido(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`HTTPError` hereda de `URLError`, y el nodo corta el ciclo ante un `URLError`."""

    def rechaza(*_: Any, **__: Any) -> Any:
        raise HTTPError("http://es/honeyml-decisiones/_search", 400, "Bad Request", Message(), None)

    monkeypatch.setattr(tools, "_buscar", rechaza)
    with pytest.raises(RuntimeError) as exc:
        precedentes_de_direccion("203.0.113.7", "2026-08-20T10:00:00Z")
    assert not isinstance(exc.value, URLError)


# El nodo


def test_agrega_sin_pisar_lo_que_encontro_el_nodo_anterior(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tools, "trayectoria_de_direccion", lambda ip, h: {"conocida": True})
    monkeypatch.setattr(tools, "rafaga_en_la_ventana", lambda e: {"disponible": True})

    ctx = nodo.recuperar(_estado())["contexto"]
    assert ctx.hallazgos["origen"] == {"pais": "BG"}  # lo del nodo anterior sigue ahí
    assert ctx.hallazgos["trayectoria"] == {"conocida": True}
    assert ctx.hallazgos["rafaga"] == {"disponible": True}


def test_suma_los_precedentes_del_almacen(monkeypatch: pytest.MonkeyPatch) -> None:
    """Se preguntan por la dirección del evento y con su marca temporal como horizonte."""
    pedidos: list[tuple[str, str]] = []

    def precedentes(ip: str, hasta: str) -> dict[str, Any]:
        pedidos.append((ip, hasta))
        return {"decisiones": 4, "maximo_decidido": "alto"}

    monkeypatch.setattr(tools, "trayectoria_de_direccion", lambda ip, h: None)
    monkeypatch.setattr(tools, "rafaga_en_la_ventana", lambda e: None)
    monkeypatch.setattr(tools, "precedentes_de_direccion", precedentes)

    ctx = nodo.recuperar(_estado())["contexto"]
    assert ctx.hallazgos["precedentes"] == {"decisiones": 4, "maximo_decidido": "alto"}
    assert pedidos == [("203.0.113.7", "2026-08-20T10:00:00Z")]


def test_precedentes_que_fallan_quedan_anotados(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un almacén que contesta mal no corta el ciclo: la decisión sale, marcada para revisión."""

    def rompe(*_: Any) -> Any:
        raise RuntimeError("el almacén de decisiones respondió 400")

    monkeypatch.setattr(tools, "trayectoria_de_direccion", lambda ip, h: None)
    monkeypatch.setattr(tools, "rafaga_en_la_ventana", lambda e: None)
    monkeypatch.setattr(tools, "precedentes_de_direccion", rompe)

    ctx = nodo.recuperar(_estado())["contexto"]
    assert "precedentes" not in ctx.hallazgos
    assert "400" in ctx.hallazgos["precedentes_falló"]


def test_el_indice_caido_corta_el_ciclo(monkeypatch: pytest.MonkeyPatch) -> None:
    def cae(*_: Any) -> Any:
        raise URLError("connection refused")

    monkeypatch.setattr(tools, "trayectoria_de_direccion", cae)
    with pytest.raises(URLError):
        nodo.recuperar(_estado())


def test_una_consulta_que_falla_queda_anotada(monkeypatch: pytest.MonkeyPatch) -> None:
    def rompe(*_: Any) -> Any:
        raise KeyError("aggregations")

    monkeypatch.setattr(tools, "trayectoria_de_direccion", lambda ip, h: {"conocida": False})
    monkeypatch.setattr(tools, "rafaga_en_la_ventana", rompe)

    ctx = nodo.recuperar(_estado())["contexto"]
    assert "rafaga_falló" in ctx.hallazgos
    assert "KeyError" in ctx.hallazgos["rafaga_falló"]
