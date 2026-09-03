"""El nodo de recuperación histórica y las dos consultas sobre las que se apoya.

La intención es la misma que en los otros archivos de pruebas del paquete: fijar las decisiones que
un refactor se llevaría puestas en silencio si nadie las escribió. Acá hay tres.

La ventana de ráfaga termina en el evento y nunca en "ahora": contar lo que pasó después sería
preguntarle al futuro si esto era una campaña. La trayectoria se ordena por la misma regla de piso
con la que se juzga al motor, y no por una segunda opinión que viva adentro de la herramienta. Y el
nodo suma al contexto en vez de reemplazarlo, así lo que encontró el nodo anterior sobrevive.
"""

from __future__ import annotations

from typing import Any
from urllib.error import URLError

import pytest

from honeyml.agent import tools
from honeyml.agent.consumer import EventoDelBus
from honeyml.agent.nodes import historial as nodo
from honeyml.agent.severidad import Severidad
from honeyml.agent.state import Contexto


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


def _estado(**kw: Any) -> Any:
    return {
        "evento": _evento(),
        "contexto": Contexto(doc_id="abc123", resumen="x", hallazgos={"origen": {"pais": "BG"}}),
        **kw,
    }


# ---- ráfaga ---------------------------------------------------------------------------------


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


# ---- trayectoria ----------------------------------------------------------------------------


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
    """El corte temporal es obligatorio: sin él la consulta miraría todo el índice de hoy."""
    assert tools.trayectoria_de_direccion("203.0.113.7", "")["conocida"] is False


# ---- el nodo --------------------------------------------------------------------------------


def test_agrega_sin_pisar_lo_que_encontro_el_nodo_anterior(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tools, "trayectoria_de_direccion", lambda ip, h: {"conocida": True})
    monkeypatch.setattr(tools, "rafaga_en_la_ventana", lambda e: {"disponible": True})

    ctx = nodo.recuperar(_estado())["contexto"]
    assert ctx.hallazgos["origen"] == {"pais": "BG"}  # lo del nodo anterior sigue ahí
    assert ctx.hallazgos["trayectoria"] == {"conocida": True}
    assert ctx.hallazgos["rafaga"] == {"disponible": True}


def test_declara_que_los_precedentes_no_se_consultaron(monkeypatch: pytest.MonkeyPatch) -> None:
    """Distinto de que no haya precedentes: todavía no existe el almacén de decisiones."""
    monkeypatch.setattr(tools, "trayectoria_de_direccion", lambda ip, h: None)
    monkeypatch.setattr(tools, "rafaga_en_la_ventana", lambda e: None)

    ctx = nodo.recuperar(_estado())["contexto"]
    assert ctx.hallazgos["precedentes"] == nodo.PRECEDENTES_PENDIENTES


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
