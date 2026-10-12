"""La forma del grafo y el nodo de contexto, sin Elasticsearch y sin proveedor.

Lo que vale la pena fijar acá no es que el código corra, sino las pocas decisiones que después es
fácil revertir sin querer.

Una respuesta inutilizable igual llega a persistencia en vez de desaparecer. Un índice inalcanzable
corta el ciclo en lugar de producir una decisión confiada sobre nada. Una consulta que simplemente
falla queda anotada y no pasa por un resultado vacío. Y el historial nunca incluye lo que pasó
después del evento que se está juzgando.

Cada una de esas es una regla que alguien podría "simplificar" en un refactor, y ninguna aparecería
como prueba en rojo sin este archivo.
"""

from __future__ import annotations

from typing import Any
from urllib.error import URLError

import pytest
from langgraph.errors import GraphRecursionError
from pydantic import ValidationError

from honeyml.agent import consumer, graph, tools
from honeyml.agent import state as estado
from honeyml.agent.adapters import config
from honeyml.agent.adapters import inferencia as adaptador
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
    """Una decisión válida para el evento de `_evento()`, que es de categoría `process`.

    El nivel no es decorativo: con `MEDIO` esta decisión quedaba por debajo del piso del evento y
    el grafo la rechaza, con razón: es exactamente el defecto que la guardia de límites existe
    para atrapar.
    """
    return Decision(
        severidad=Severidad.ALTO,
        confianza=0.8,
        motivo_sin_tactica="sin_objetivo_tactico",
        justificacion="ejecutó comandos dentro del señuelo",
    )


def test_el_esquema_rechaza_un_nivel_que_no_existe() -> None:
    """El enum de `severidad.py` hace este control sin que nadie escriba una comprobación.

    El nivel es "medio", no "media": una diferencia de una letra que sin el enum llegaría a
    persistirse tal cual.
    """
    with pytest.raises(ValidationError):
        Decision(
            doc_id="abc123",
            severidad="media",  # type: ignore[arg-type]
            confianza=0.8,
            motivo_sin_tactica=None,
            justificacion="x",
        )


# Topología
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


def test_el_grafo_recorre_todos_los_nodos_con_implementaciones_de_prueba() -> None:
    visitados: list[str] = []

    def falso(nombre: str, devuelve: dict[str, Any]) -> graph.Nodo:
        def nodo(_: Any) -> dict[str, Any]:
            visitados.append(nombre)
            return devuelve

        return nodo

    compilado = graph.construir_grafo(
        {
            # Sin decisión: el camino largo es el que tiene que recorrer todos los nodos. Un falso
            # que devolviera una decisión saltearía cinco de ellos y la prueba pasaría igual.
            graph.MEMORIA: falso(graph.MEMORIA, {"firma": "abc123"}),
            graph.CONTEXTO: falso(graph.CONTEXTO, {"contexto": Contexto(doc_id="a", resumen="b")}),
            graph.HISTORIAL: falso(graph.HISTORIAL, {}),
            graph.INFERENCIA: falso(graph.INFERENCIA, {"borrador": {}}),
            graph.VALIDACION: falso(graph.VALIDACION, {"decision": _decision()}),
            graph.PERSISTENCIA: falso(graph.PERSISTENCIA, {}),
        }
    )
    compilado.invoke(estado_inicial(_evento()))
    assert visitados == graph.ORDEN


# Las guardias del ciclo correctivo
#
# Son contratos entre el grafo y los nodos de inferencia y validación. Ninguno se rompe de forma
# visible: el ciclo sigue andando, más caro o con una decisión que no debería haberse guardado.
# Sin estas pruebas, un cambio en cualquiera de los dos nodos puede incumplirlos en silencio.


def _recorrer(cfg: dict[str, Any], evento: Any = None) -> tuple[list[str], Any]:
    """Corre el grafo con nodos de prueba y devuelve el recorrido y el estado final."""
    visitados: list[str] = []

    def envolver(nombre: str, devuelve: Any) -> graph.Nodo:
        def nodo(estado: Any) -> Any:
            visitados.append(nombre)
            return devuelve(estado) if callable(devuelve) else devuelve

        return nodo

    compilado = graph.construir_grafo({n: envolver(n, d) for n, d in cfg.items()})
    final = graph.ejecutar(compilado, estado_inicial(evento or _evento()))
    return visitados, final


_CTX: dict[str, Any] = {"contexto": Contexto(doc_id="abc123", resumen="x")}


def test_el_ciclo_termina_aunque_nadie_cuente_los_intentos() -> None:
    """Sin esta guardia el ciclo da vueltas hasta el techo de pasos, gastando llamadas pagas.

    Son dos contadores llevados por dos nodos distintos: `intentos` lo incrementa la inferencia,
    donde se hace la llamada, y `rechazos` la validación, una vez por ronda. Que se olvide uno de
    los dos es inocuo, porque el otro igual termina el ciclo.
    """
    visitados, final = _recorrer(
        {
            graph.CONTEXTO: _CTX,
            graph.HISTORIAL: {},
            graph.INFERENCIA: {"borrador": {}},  # nunca toca `intentos`
            graph.VALIDACION: {"reproches": ["falta severidad"], "rechazos": 1},
            graph.PERSISTENCIA: {},
        }
    )
    assert visitados.count(graph.INFERENCIA) == MAX_INTENTOS
    assert graph.intentos_gastados(final) == MAX_INTENTOS
    assert visitados[-1] == graph.PERSISTENCIA


def test_los_reproches_se_acumulan_en_vez_de_pisarse() -> None:
    """Sin el reductor de `state.py`, cada vuelta pisa el reproche de la anterior.

    Y entonces un modelo que arregla el campo señalado y rompe otro nunca ve los dos juntos.
    """
    _, final = _recorrer(
        {
            graph.CONTEXTO: _CTX,
            graph.HISTORIAL: {},
            graph.INFERENCIA: {"borrador": {}},
            graph.VALIDACION: lambda s: {
                "reproches": [f"error {graph.intentos_gastados(s)}"],
                "rechazos": 1,
            },
            graph.PERSISTENCIA: {},
        }
    )
    assert final["reproches"] == ["error 0", "error 1", "error 2"]


def test_una_severidad_por_debajo_del_piso_no_llega_a_persistirse() -> None:
    """El grafo tiene que mirar los límites, no solo la existencia de la decisión.

    `informativo` sobre un evento que documenta ejecución de comandos no es una diferencia de
    criterio: contradice el registro.
    """
    imposible = Decision(
        severidad=Severidad.INFORMATIVO,
        confianza=0.9,
        motivo_sin_tactica="sin_objetivo_tactico",
        justificacion="parece inofensivo",
    )
    visitados, final = _recorrer(
        {
            graph.CONTEXTO: _CTX,
            graph.HISTORIAL: {},
            graph.INFERENCIA: {"borrador": {}},
            graph.VALIDACION: {
                "decision": imposible,
                "reproches": ["por debajo del piso"],
                "rechazos": 1,
            },
            graph.PERSISTENCIA: {},
        }
    )
    assert estado.decision_utilizable(final) is False
    assert visitados.count(graph.INFERENCIA) == MAX_INTENTOS  # se reintentó, no se aceptó
    assert estado.resultado_del_ciclo(final) == "esquema_invalido"


def test_persistencia_siempre_recibe_un_motivo_cuando_no_hay_decision() -> None:
    """Sin decisión tiene que llegar con motivo, o el nodo no puede distinguir qué pasó."""
    _, agotado = _recorrer(
        {
            graph.CONTEXTO: _CTX,
            graph.HISTORIAL: {},
            graph.INFERENCIA: {"borrador": {}},
            graph.VALIDACION: {"reproches": ["falta severidad"], "rechazos": 1},
            graph.PERSISTENCIA: {},
        }
    )
    assert estado.resultado_del_ciclo(agotado) == "esquema_invalido"

    _, sin_ctx = _recorrer(
        {
            graph.CONTEXTO: {"motivo_de_corte": "sin_contexto"},
            graph.HISTORIAL: {},
            graph.INFERENCIA: {},
            graph.VALIDACION: {},
            graph.PERSISTENCIA: {},
        },
        evento=_evento(source_ip=""),
    )
    assert estado.resultado_del_ciclo(sin_ctx) == "sin_contexto"


def test_una_decision_valida_no_declara_motivo_de_corte() -> None:
    _, final = _recorrer(
        {
            graph.CONTEXTO: _CTX,
            graph.HISTORIAL: {},
            graph.INFERENCIA: {"borrador": {}},
            graph.VALIDACION: {"decision": _decision()},
            graph.PERSISTENCIA: {},
        }
    )
    assert estado.resultado_del_ciclo(final) is None


def test_una_correccion_a_tiempo_corta_el_bucle() -> None:
    """El reintento correctivo tiene que servir para algo: si acierta, el ciclo sigue de largo."""
    visitados, final = _recorrer(
        {
            graph.CONTEXTO: _CTX,
            graph.HISTORIAL: {},
            graph.INFERENCIA: {"borrador": {}},
            graph.VALIDACION: lambda s: (
                {"decision": _decision()}
                if graph.intentos_gastados(s) >= 1
                else {"reproches": ["falta severidad"], "rechazos": 1}
            ),
            graph.PERSISTENCIA: {},
        }
    )
    assert visitados.count(graph.INFERENCIA) == 2
    assert estado.decision_utilizable(final) is True


def test_un_borrador_con_varios_problemas_igual_se_reintenta() -> None:
    """La regresión que buscábamos: cuatro problemas agotaban el presupuesto sin reintentar.

    La validación junta todos los problemas de un borrador en una sola pasada, así que una ronda
    puede dejar cuatro reproches. Mientras el presupuesto se medía contando reproches, esa ronda se
    leía como cuatro intentos gastados y el modelo no llegaba nunca a corregir.
    """
    visitados, final = _recorrer(
        {
            graph.CONTEXTO: _CTX,
            graph.HISTORIAL: {},
            graph.INFERENCIA: lambda s: {"borrador": {}, "intentos": int(s.get("intentos", 0)) + 1},
            graph.VALIDACION: lambda s: (
                {"decision": _decision()}
                if s.get("reproches")
                else {"reproches": ["a", "b", "c", "d"], "rechazos": 1}
            ),
            graph.PERSISTENCIA: {},
        }
    )
    assert visitados.count(graph.INFERENCIA) == 2
    assert len(final["reproches"]) == 4  # la historia completa se conserva
    assert final["rechazos"] == 1  # pero es una sola ronda
    assert estado.decision_utilizable(final) is True


def test_si_los_dos_contadores_se_olvidan_corta_el_techo_de_pasos() -> None:
    """La última red: un ciclo sin salida muere acotado y ruidoso, no en diez mil vueltas pagas.

    Es el caso de un defecto nuestro, no del proveedor. Se deja explotar a propósito: el evento
    queda sin confirmar y el consumidor lo manda a la cola de muertos tras unas pocas entregas, en
    vez de que un error de programación pase por una decisión legítima.
    """
    with pytest.raises(GraphRecursionError):
        _recorrer(
            {
                graph.CONTEXTO: _CTX,
                graph.HISTORIAL: {},
                graph.INFERENCIA: {"borrador": {}},  # no cuenta intentos
                graph.VALIDACION: {"reproches": ["x"]},  # ni rechazos
                graph.PERSISTENCIA: {},
            }
        )


def test_la_ventana_de_reclamo_cubre_el_ciclo_completo() -> None:
    """El bus no puede reclamar un evento que todavía se está triando.

    Es la única guardia de este archivo que no vive dentro del grafo, sino entre el grafo y el bus,
    y por eso es la más fácil de romper sin darse cuenta: alcanza con subir el timeout del proveedor
    o MAX_INTENTOS y nadie se entera hasta que en producción aparecen decisiones duplicadas y
    eventos en la cola de muertos sin motivo.

    Si esta prueba se pone en rojo, lo que hay que revisar es `consumer.INACTIVIDAD_MS`.
    """
    por_llamada = config.TIMEOUT_SEGUNDOS * adaptador.MAX_REINTENTOS + sum(
        adaptador.ESPERA_BASE * (2**i) for i in range(adaptador.MAX_REINTENTOS - 1)
    )
    ciclo_completo = por_llamada * MAX_INTENTOS

    assert consumer.INACTIVIDAD_MS / 1000 >= ciclo_completo


def test_el_techo_de_pasos_sale_de_la_topologia() -> None:
    """Que sea derivado y no un número a ojo es lo que lo mantiene correcto si cambia el margen."""
    assert graph.LIMITE_DE_PASOS == 3 + 2 * (MAX_INTENTOS + 2) + 1

    # Y que le alcance para el camino más largo de verdad, que es la razón de que exista: los tres
    # nodos lineales, un par (inferencia, validación) por intento, y persistencia.
    assert graph.LIMITE_DE_PASOS >= 3 + 2 * MAX_INTENTOS + 1


# Nodo de contexto
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


# Herramientas
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
