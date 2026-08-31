"""The triage graph: which nodes exist, in what order they run, and where the cycle can turn back.

The engine is a state machine and not a chain because of one edge — validation can send the answer
back to inference with the error attached. Everything else is a straight line, and saying so
explicitly is worth more than the flexibility of leaving it implicit.

    contexto ─→ historial ─→ inferencia ─→ validación ─┬─(válida)──────────→ persistencia ─→ fin
        │                         ↑                     │                         ↑
        │                         └──(reproche)─────────┘   hasta MAX_INTENTOS    │
        └──(sin dirección de origen: nada que correlacionar)──────────────────────┘

TWO WAYS OF FAILING, AND WHY THEY END DIFFERENTLY

*The provider answered, but never in the required shape.* After MAX_INTENTOS corrective attempts the
cycle stops trying and persists a non-conclusive decision. The event is settled: the provider is
reachable and retrying tomorrow will not produce a different grammar. Keeping it pending would burn
one paid call per redelivery, forever, over an event that is already understood to be unusable.

*The provider could not be reached at all.* The node raises, the exception leaves the graph, and the
consumer never acknowledges — so the event stays pending and another consumer reclaims it later.
Nothing is persisted, because nothing was decided.

The difference matters and is easy to collapse by accident. An outage is temporary and deserves a
retry; a model that cannot follow a schema is not, and deserves a record saying so.

WHY THE NODES ARE INJECTED
Each node belongs to a different row of the plan (81 through 85). Passing them in means the topology
can be built and tested before any of them exists, and each row swaps one function into a graph
whose shape nobody has to touch again.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, cast

from langgraph.graph import END, StateGraph

from .nodes import contexto as nodo_contexto
from .state import MAX_INTENTOS, EstadoTriaje

# Un nodo devuelve el estado *parcial* que tocó, no un diccionario cualquiera. `EstadoTriaje` es
# `total=False`, así que ese tipo ya dice exactamente eso: cualquier subconjunto de las claves del
# estado, y ninguna otra. Escribirlo como `dict[str, Any]` aceptaba claves inventadas que LangGraph
# después descarta en silencio.
Nodo = Callable[[EstadoTriaje], EstadoTriaje]

CONTEXTO = "contexto"
HISTORIAL = "historial"
INFERENCIA = "inferencia"
VALIDACION = "validacion"
PERSISTENCIA = "persistencia"

# Qué fila del cronograma le debe una implementación a cada nodo. Está acá y no en un comentario
# suelto porque es lo que hace accionable el error cuando falta una: el mensaje nombra la tarea.
DUENO: dict[str, str] = {
    CONTEXTO: "fila 81 — nodo de construcción de contexto",
    HISTORIAL: "fila 82 — nodo de recuperación de información histórica",
    INFERENCIA: "fila 83 — nodo de consulta al servicio de inferencia",
    VALIDACION: "fila 84 — nodo de validación de esquema con reintentos correctivos",
    PERSISTENCIA: "fila 85 — nodo de persistencia de la decisión",
}

ORDEN = [CONTEXTO, HISTORIAL, INFERENCIA, VALIDACION, PERSISTENCIA]


def _pendiente(nombre: str) -> Nodo:
    """Placeholder for a node whose row has not been built yet.

    Fails when the graph *runs*, not when it is imported, so the topology stays inspectable and
    testable while the engine is half-written. The message names the task, so hitting it reads as
    "this is not built yet" and not as a bug.
    """

    def nodo(_: EstadoTriaje) -> EstadoTriaje:
        raise NotImplementedError(
            f"El nodo '{nombre}' todavía no está implementado: {DUENO[nombre]}"
        )

    nodo.__name__ = f"pendiente_{nombre}"
    return nodo


def nodos_disponibles() -> dict[str, Nodo]:
    """The real implementations that exist today; the rest come back as placeholders."""
    reales: dict[str, Nodo] = {CONTEXTO: nodo_contexto.construir}
    return {nombre: reales.get(nombre) or _pendiente(nombre) for nombre in ORDEN}


def ruta_tras_contexto(estado: EstadoTriaje) -> str:
    """Skip straight to persistence when there was nothing to reason about.

    An event with no source address has nothing to correlate: no history, no origin, no session.
    Sending it down the full path would spend an inference call to be told what the absence of a
    field already says. It is still persisted, marked non-conclusive, so the event does not simply
    disappear between arriving and being classified.
    """
    return PERSISTENCIA if estado.get("motivo_de_corte") else HISTORIAL


def ruta_tras_validar(estado: EstadoTriaje) -> str:
    """Where to go once validation has had its say.

    Both non-retry branches lead to persistence on purpose. A decision that could not be validated
    is still recorded — marked non-conclusive — because the alternative is an event that vanishes
    between "arrived" and "classified" with nothing to show for it. The panel can then present it
    the way CU-03 describes instead of simply not listing it.
    """
    if estado.get("decision") is not None:
        return PERSISTENCIA
    if estado.get("intentos", 0) < MAX_INTENTOS:
        return INFERENCIA
    return PERSISTENCIA


def construir_grafo(nodos: Mapping[str, Nodo] | None = None) -> Any:
    """Wire the topology and compile it. `nodos` overrides any implementation, one by one."""
    elegidos = {**nodos_disponibles(), **(nodos or {})}

    g: StateGraph[EstadoTriaje] = StateGraph(EstadoTriaje)
    for nombre in ORDEN:
        # El `cast` es contra una limitación declarada de LangGraph, no contra un tipo mal puesto.
        # `add_node` acota el estado a un protocolo estructural, y su propio `_typing.py` avisa:
        # "we cannot use either TypedDict or dataclass directly due to limitations in type
        # checking". Se probó también con el TypedDict de typing_extensions —el que usa la propia
        # biblioteca— y el veredicto no cambia. En ejecución el nodo recibe y devuelve exactamente
        # `EstadoTriaje`, que es lo que declara `Nodo` unas líneas más arriba.
        g.add_node(nombre, cast("Any", elegidos[nombre]))

    g.set_entry_point(CONTEXTO)
    g.add_conditional_edges(
        CONTEXTO,
        ruta_tras_contexto,
        {HISTORIAL: HISTORIAL, PERSISTENCIA: PERSISTENCIA},
    )
    g.add_edge(HISTORIAL, INFERENCIA)
    g.add_edge(INFERENCIA, VALIDACION)
    g.add_conditional_edges(
        VALIDACION,
        ruta_tras_validar,
        {INFERENCIA: INFERENCIA, PERSISTENCIA: PERSISTENCIA},
    )
    g.add_edge(PERSISTENCIA, END)
    return g.compile()


def describir() -> str:
    """The topology as text, with each node's state today. Printed by `make grafo`."""
    disponibles = nodos_disponibles()
    lineas = ["Grafo de triaje", ""]
    for i, nombre in enumerate(ORDEN):
        listo = not disponibles[nombre].__name__.startswith("pendiente_")
        marca = "✅" if listo else "⏳"
        flecha = "   │" if i < len(ORDEN) - 1 else ""
        lineas.append(f"  {marca} {nombre:<14} {DUENO[nombre]}")
        if flecha:
            lineas.append(flecha)
    lineas += [
        "",
        f"  validación → inferencia cuando el esquema falla, hasta {MAX_INTENTOS} intentos",
        "  validación → persistencia cuando la decisión es válida, o cuando se agotaron",
        "",
        "  Un proveedor inalcanzable no toma ninguna de las dos salidas: el nodo levanta, el",
        "  consumidor no confirma y el evento vuelve a quedar pendiente para otro consumidor.",
    ]
    return "\n".join(lineas)


if __name__ == "__main__":
    print(describir())
