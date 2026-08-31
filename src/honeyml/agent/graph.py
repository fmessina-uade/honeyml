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
from .nodes import historial as nodo_historial
from .severidad import dentro_de_limites
from .state import MAX_INTENTOS, EstadoTriaje, MotivoDeCorte

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

# Techo de pasos de una corrida, derivado de la topología y no elegido a ojo.
#
# El camino más largo legítimo es contexto → historial → (inferencia → validación) por cada intento
# → persistencia. Con el margen de una vuelta, cualquier corrida que lo supere está en un bucle que
# el diseño no contempla, y conviene que muera rápido y con un número que se pueda relacionar con
# esta línea —en vez del 10.007 por defecto de LangGraph, que no le dice nada a nadie.
LIMITE_DE_PASOS = 2 + 2 * (MAX_INTENTOS + 2) + 1


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
    reales: dict[str, Nodo] = {
        CONTEXTO: nodo_contexto.construir,
        HISTORIAL: nodo_historial.recuperar,
    }
    return {nombre: reales.get(nombre) or _pendiente(nombre) for nombre in ORDEN}


def ruta_tras_contexto(estado: EstadoTriaje) -> str:
    """Skip straight to persistence when there was nothing to reason about.

    An event with no source address has nothing to correlate: no history, no origin, no session.
    Sending it down the full path would spend an inference call to be told what the absence of a
    field already says. It is still persisted, marked non-conclusive, so the event does not simply
    disappear between arriving and being classified.
    """
    return PERSISTENCIA if estado.get("motivo_de_corte") else HISTORIAL


def intentos_gastados(estado: EstadoTriaje) -> int:
    """How many attempts this cycle has already spent.

    El máximo entre el contador y los reproches acumulados, y no solo el contador, porque el
    contador lo lleva un nodo que todavía no existe. Una auditoría del grafo lo mostró sin lugar a
    dudas: con la validación rechazando y nadie incrementando `intentos`, el ciclo dio **10.007
    vueltas** antes de que LangGraph lo cortara por límite de recursión —diez mil llamadas pagas
    sobre un solo evento, y un error genérico al final que no nombra la causa.

    Como la validación no puede rechazar sin dejar un reproche —es lo que se le devuelve al
    proveedor para que corrija—, contar reproches es un segundo camino hacia el mismo número. Que
    las filas 83 y 84 se olviden del contador deja de ser catastrófico y pasa a ser inocuo.
    """
    return max(int(estado.get("intentos", 0)), len(estado.get("reproches", [])))


def decision_utilizable(estado: EstadoTriaje) -> bool:
    """Whether the decision may be persisted as the engine's answer.

    Dos condiciones, no una. Que exista, y que sea defendible **para este evento**: la fila 78
    definió la escala anclada a la evidencia justamente para que una severidad por debajo del piso
    —un `informativo` sobre un evento que documenta una transferencia de archivo— sea una
    contradicción con el registro y no una diferencia de criterio.

    Esa guardia existía y estaba probada desde la fila 78, pero **no estaba cableada**: el grafo
    solo preguntaba si había decisión, así que una severidad imposible llegaba a persistencia sin
    que nada la mirara. La auditoría lo encontró en el escenario 5.
    """
    decision = estado.get("decision")
    if decision is None:
        return False
    evento = estado.get("evento")
    if evento is None:
        # Sin evento no hay piso contra el cual medir. No debería pasar —el estado inicial siempre
        # lo trae— y si pasa, el problema no es la severidad.
        return True
    return dentro_de_limites(decision.severidad, evento)


def ruta_tras_validar(estado: EstadoTriaje) -> str:
    """Where to go once validation has had its say.

    Both non-retry branches lead to persistence on purpose. A decision that could not be validated
    is still recorded — marked non-conclusive — because the alternative is an event that vanishes
    between "arrived" and "classified" with nothing to show for it. The panel can then present it
    the way CU-03 describes instead of simply not listing it.
    """
    if decision_utilizable(estado):
        return PERSISTENCIA

    # Reintentar sin un reproche es repetir la misma llamada. El proveedor no recibiría nada que
    # corregir y devolvería lo mismo, así que el ciclo se corta acá en vez de gastar tres llamadas
    # idénticas. Cierra además el único camino por el que el bucle podía no terminar: una validación
    # que devuelve una decisión inutilizable y no deja reproche no mueve ningún contador.
    if not estado.get("reproches"):
        return PERSISTENCIA

    if intentos_gastados(estado) < MAX_INTENTOS:
        return INFERENCIA
    return PERSISTENCIA


def resultado_del_ciclo(estado: EstadoTriaje) -> MotivoDeCorte | None:
    """Why this cycle is ending. `None` means it ended with a decision worth persisting.

    Lo usa el nodo de persistencia (fila 85) para saber qué está guardando. Vive acá y no allá
    porque es la contracara de `ruta_tras_validar`: las dos leen el mismo estado para responder la
    misma pregunta, y separarlas dejaría que una diga "andá a persistir" y la otra no sepa por qué.

    La auditoría mostró el hueco en el escenario 3: con los intentos agotados el ciclo llegaba a
    persistencia sin decisión **y sin motivo**, así que el nodo no podía distinguir un esquema
    irrecuperable de cualquier otra cosa que hubiera salido mal.
    """
    declarado = estado.get("motivo_de_corte")
    if declarado:
        return declarado
    if decision_utilizable(estado):
        return None
    return "esquema_invalido"


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


def ejecutar(compilado: Any, estado: EstadoTriaje) -> EstadoTriaje:
    """Run one event through the graph, with the step ceiling applied.

    Es el único punto de entrada que debería usar el motor. Invocar el grafo directamente también
    funciona, pero se queda con el límite por defecto de LangGraph —diez mil pasos— y ese número no
    tiene relación con esta topología: convierte un contrato incumplido en una factura.
    """
    resultado: EstadoTriaje = compilado.invoke(estado, config={"recursion_limit": LIMITE_DE_PASOS})
    return resultado


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
