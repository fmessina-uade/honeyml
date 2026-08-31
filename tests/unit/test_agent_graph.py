"""The graph's shape and the context node, with no Elasticsearch and no provider.

What is worth pinning here is not that the code runs — it is the handful of decisions that are easy
to reverse by accident later:

- an unusable answer still reaches persistence instead of vanishing
- an unreachable index stops the cycle instead of producing a confident decision about nothing
- a lookup that merely fails is written down rather than passing for an empty result
- history never includes what happened after the event being judged

Every one of those is a rule someone could "simplify away" while refactoring, and none of them would
show up as a test failure without this file.
"""

from __future__ import annotations

from typing import Any
from urllib.error import URLError

import pytest
from pydantic import ValidationError

from honeyml.agent import graph, tools
from honeyml.agent.consumer import EventoDelBus
from honeyml.agent.nodes import contexto as nodo_contexto
from honeyml.agent.severidad import Severidad
from honeyml.agent.state import MAX_INTENTOS, Contexto, Decision, estado_inicial


def _evento(**kw: Any) -> EventoDelBus:
    base = {
        "entry_id": "1-0",
        "doc_id": "abc123",
        "timestamp": "2026-08-20T10:00:00Z",
        "honeypot": "cowrie",
        "category": "process",
        "source_ip": "203.0.113.7",
        "session": "s1",
        "command": "uname -a",
    }
    base.update(kw)
    return EventoDelBus(**base)  # type: ignore[arg-type]


def _decision() -> Decision:
    return Decision(
        doc_id="abc123",
        severidad=Severidad.MEDIO,
        confianza=0.8,
        justificacion="entró con credenciales del señuelo",
    )


def test_el_esquema_rechaza_un_nivel_que_no_existe() -> None:
    """El enum de la fila 78 hace este control sin que nadie escriba una comprobación.

    Lo atrapó de entrada: el marcador de estas pruebas decía "media" y el nivel es "medio".
    """
    with pytest.raises(ValidationError):
        Decision(
            doc_id="abc123",
            severidad="media",  # type: ignore[arg-type]
            confianza=0.8,
            justificacion="x",
        )


# ---- topología ----------------------------------------------------------------------------


def test_el_grafo_compila() -> None:
    """Con los nodos que faltan como marcadores: la forma tiene que ser verificable ya."""
    assert graph.construir_grafo() is not None


def test_una_decision_valida_va_a_persistencia() -> None:
    estado = {"decision": _decision(), "intentos": 1}
    assert graph.ruta_tras_validar(estado) == graph.PERSISTENCIA  # type: ignore[arg-type]


def test_un_esquema_invalido_vuelve_a_inferencia() -> None:
    estado = {"intentos": 1, "reproches": ["falta severidad"]}
    assert graph.ruta_tras_validar(estado) == graph.INFERENCIA  # type: ignore[arg-type]


def test_agotados_los_intentos_igual_se_persiste() -> None:
    """La regla que sostiene que ningún evento desaparezca entre "llegó" y "clasificado"."""
    estado = {"intentos": MAX_INTENTOS, "reproches": ["sigue faltando severidad"]}
    assert graph.ruta_tras_validar(estado) == graph.PERSISTENCIA  # type: ignore[arg-type]


def test_sin_contexto_saltea_la_inferencia() -> None:
    """Un evento sin nada que correlacionar no debe costar una llamada paga."""
    assert graph.ruta_tras_contexto({"motivo_de_corte": "sin_contexto"}) == graph.PERSISTENCIA
    assert graph.ruta_tras_contexto({"contexto": Contexto(doc_id="x", resumen="y")}) == (
        graph.HISTORIAL
    )


def test_el_grafo_recorre_los_cinco_nodos_con_implementaciones_de_prueba() -> None:
    visitados: list[str] = []

    def falso(nombre: str, devuelve: dict[str, Any]) -> graph.Nodo:
        def nodo(_: Any) -> dict[str, Any]:
            visitados.append(nombre)
            return devuelve

        return nodo

    compilado = graph.construir_grafo(
        {
            graph.CONTEXTO: falso(graph.CONTEXTO, {"contexto": Contexto(doc_id="a", resumen="b")}),
            graph.HISTORIAL: falso(graph.HISTORIAL, {}),
            graph.INFERENCIA: falso(graph.INFERENCIA, {"borrador": {}}),
            graph.VALIDACION: falso(graph.VALIDACION, {"decision": _decision()}),
            graph.PERSISTENCIA: falso(graph.PERSISTENCIA, {}),
        }
    )
    compilado.invoke(estado_inicial(_evento()))
    assert visitados == graph.ORDEN


# ---- nodo de contexto ---------------------------------------------------------------------


def test_un_evento_sin_origen_se_corta() -> None:
    salida = nodo_contexto.construir({"evento": _evento(source_ip="")})
    assert salida == {"motivo_de_corte": "sin_contexto"}


def test_arma_el_contexto_con_lo_que_devuelven_las_herramientas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        tools, "historial_de_direccion", lambda ip, hasta: {"conocida": True, "eventos_previos": 9}
    )
    monkeypatch.setattr(tools, "origen_de_direccion", lambda ip: {"pais": "Bulgaria"})
    monkeypatch.setattr(
        tools, "comandos_de_la_sesion", lambda s, hasta: {"comandos": ["uname -a"], "total": 1}
    )
    monkeypatch.setattr(tools, "familia_de_la_sesion", lambda c: {"familia": "family-7ab552"})
    monkeypatch.setattr(tools, "arquetipos_del_corpus", lambda: {"direcciones_analizadas": 14173})

    ctx = nodo_contexto.construir({"evento": _evento()})["contexto"]
    assert ctx.doc_id == "abc123"
    assert set(ctx.hallazgos) == {"historial", "origen", "sesion", "familia", "poblacion"}
    assert ctx.hallazgos["historial"]["eventos_previos"] == 9


def test_el_indice_caido_corta_el_ciclo(monkeypatch: pytest.MonkeyPatch) -> None:
    """No se degrada a un contexto vacío: eso sería una decisión segura sobre nada."""

    def cae(*_: Any) -> Any:
        raise URLError("connection refused")

    monkeypatch.setattr(tools, "historial_de_direccion", cae)
    with pytest.raises(URLError):
        nodo_contexto.construir({"evento": _evento()})


def test_una_consulta_que_falla_queda_anotada(monkeypatch: pytest.MonkeyPatch) -> None:
    """Distinto de que el índice esté caído: el ciclo sigue, pero el hueco queda dicho."""

    def rompe(*_: Any) -> Any:
        raise KeyError("source.geo")

    monkeypatch.setattr(tools, "historial_de_direccion", lambda ip, hasta: {"conocida": False})
    monkeypatch.setattr(tools, "origen_de_direccion", rompe)
    monkeypatch.setattr(tools, "comandos_de_la_sesion", lambda s, hasta: {"comandos": []})
    monkeypatch.setattr(tools, "arquetipos_del_corpus", lambda: None)

    ctx = nodo_contexto.construir({"evento": _evento()})["contexto"]
    assert "origen_falló" in ctx.hallazgos
    assert "KeyError" in ctx.hallazgos["origen_falló"]


def test_dionaea_no_pregunta_por_sesion(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ese sensor no emite identificador de sesión: preguntar devolvería vacío y mentiría."""

    def no_deberia(*_: Any) -> Any:
        raise AssertionError("no se debe consultar la sesión cuando no hay una")

    monkeypatch.setattr(tools, "historial_de_direccion", lambda ip, hasta: {"conocida": False})
    monkeypatch.setattr(tools, "origen_de_direccion", lambda ip: {})
    monkeypatch.setattr(tools, "arquetipos_del_corpus", lambda: None)
    monkeypatch.setattr(tools, "comandos_de_la_sesion", no_deberia)

    ctx = nodo_contexto.construir({"evento": _evento(honeypot="dionaea", session="")})["contexto"]
    assert "sesion" not in ctx.hallazgos


# ---- herramientas -------------------------------------------------------------------------


def test_el_historial_se_corta_en_el_evento(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sin este corte el motor juzga un evento con evidencia que todavía no existía."""
    capturado: dict[str, Any] = {}

    def falsa_busqueda(body: dict[str, Any], es_url: str = "") -> dict[str, Any]:
        capturado.update(body)
        return {
            "hits": {"total": {"value": 0}},
            "aggregations": {
                "acciones": {"buckets": []},
                "categorias": {"buckets": []},
                "sesiones": {"value": 0},
                "primera": {},
                "accesos": {"doc_count": 0},
            },
        }

    monkeypatch.setattr(tools, "_buscar", falsa_busqueda)
    tools.historial_de_direccion("203.0.113.7", "2026-08-20T10:00:00Z")

    rangos = [f for f in capturado["query"]["bool"]["filter"] if "range" in f]
    assert rangos[0]["range"]["@timestamp"] == {"lt": "2026-08-20T10:00:00Z"}


def test_la_sesion_avisa_cuando_esta_recortada(monkeypatch: pytest.MonkeyPatch) -> None:
    def falsa_busqueda(body: dict[str, Any], es_url: str = "") -> dict[str, Any]:
        return {
            "hits": {
                "total": {"value": 400},
                "hits": [{"_source": {"process": {"command_line": f"cmd{i}"}}} for i in range(12)],
            }
        }

    monkeypatch.setattr(tools, "_buscar", falsa_busqueda)
    r = tools.comandos_de_la_sesion("s1")
    assert r["truncado"] is True
    assert len(r["comandos"]) == tools.MAX_COMMANDS
