"""El grafo de triaje: qué nodos hay, en qué orden corren y dónde el ciclo puede volver atrás.

    contexto -> historial -> inferencia -> validación --(válida)---> persistencia -> fin
        |                        ^             |                          ^
        |                        +--(reproche)-+   hasta MAX_INTENTOS     |
        +--(sin dirección de origen, nada que correlacionar)--------------+

Es una máquina de estados y no una cadena por una sola arista: la validación puede devolverle la
respuesta al nodo de inferencia con el error adjunto. Todo lo demás es una línea recta.

La parte que más cuesta ver leyendo el código es que hay dos formas de fallar y terminan distinto.
Si el proveedor contestó pero nunca con la forma pedida, después de MAX_INTENTOS se persiste una
decisión no concluyente y el evento queda cerrado: el proveedor está vivo y reintentar mañana no le
va a cambiar la gramática. Si en cambio no se lo pudo alcanzar, el nodo levanta, la excepción sale
del grafo y el consumidor no confirma, así que otro lo reclama más tarde y no se persiste nada.
Confundirlas es fácil, pero una caída es temporal y un modelo que no puede seguir un esquema no.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, cast

from langgraph.graph import END, StateGraph

from .nodes import contexto as nodo_contexto
from .nodes import historial as nodo_historial
from .nodes import inferencia as nodo_inferencia
from .nodes import validacion as nodo_validacion
from .severidad import dentro_de_limites
from .state import MAX_INTENTOS, EstadoTriaje, MotivoDeCorte

# Un nodo devuelve el estado parcial que tocó, no un diccionario cualquiera: con `dict[str, Any]`
# entraban claves inventadas que LangGraph después descarta en silencio.
Nodo = Callable[[EstadoTriaje], EstadoTriaje]

CONTEXTO = "contexto"
HISTORIAL = "historial"
INFERENCIA = "inferencia"
VALIDACION = "validacion"
PERSISTENCIA = "persistencia"

# Qué hace cada nodo, en una línea. Está acá porque es lo que vuelve accionable el error cuando
# falta una implementación: el mensaje dice qué falta escribir.
RESPONSABILIDAD: dict[str, str] = {
    CONTEXTO: "arma el contexto del evento a partir de las consultas de solo lectura",
    HISTORIAL: "agrega la trayectoria de la dirección y la correlación de ráfaga",
    INFERENCIA: "le pide al servicio de inferencia una decisión sobre el contexto",
    VALIDACION: "verifica el esquema y los límites, y redacta el reproche cuando no cumple",
    PERSISTENCIA: "guarda la decisión de forma durable",
}

ORDEN = [CONTEXTO, HISTORIAL, INFERENCIA, VALIDACION, PERSISTENCIA]

# Techo de pasos, derivado de la topología y no elegido a ojo: contexto, historial, un par
# (inferencia, validación) por intento, persistencia, y una vuelta de margen. Cualquier corrida que
# lo supere está en un bucle que el diseño no contempla, y conviene que muera rápido con un número
# que se pueda relacionar con esta línea, en vez del 10.007 por defecto de LangGraph.
LIMITE_DE_PASOS = 2 + 2 * (MAX_INTENTOS + 2) + 1


def _pendiente(nombre: str) -> Nodo:
    """Marcador para un nodo que todavía no está escrito.

    Falla cuando el grafo corre y no cuando se importa, así la topología se puede inspeccionar y
    probar con el motor a medio hacer.
    """

    def nodo(_: EstadoTriaje) -> EstadoTriaje:
        raise NotImplementedError(
            f"El nodo '{nombre}' todavía no está implementado: {RESPONSABILIDAD[nombre]}"
        )

    nodo.__name__ = f"pendiente_{nombre}"
    return nodo


def nodos_disponibles() -> dict[str, Nodo]:
    """Las implementaciones que existen hoy. El resto vuelve como marcador."""
    reales: dict[str, Nodo] = {
        CONTEXTO: nodo_contexto.construir,
        HISTORIAL: nodo_historial.recuperar,
        INFERENCIA: nodo_inferencia.consultar,
        VALIDACION: nodo_validacion.validar,
    }
    return {nombre: reales.get(nombre) or _pendiente(nombre) for nombre in ORDEN}


def ruta_tras_contexto(estado: EstadoTriaje) -> str:
    """Salta directo a persistencia cuando no había nada sobre lo que razonar.

    Un evento sin dirección de origen no tiene con qué correlacionarse, y mandarlo por el camino
    completo gastaría una llamada de inferencia para que nos digan lo que la ausencia del campo ya
    dice. Igual se persiste, marcado como no concluyente, así no desaparece.
    """
    return PERSISTENCIA if estado.get("motivo_de_corte") else HISTORIAL


def intentos_gastados(estado: EstadoTriaje) -> int:
    """Cuántos intentos gastó ya este ciclo.

    El máximo entre dos contadores que se llevan por separado a propósito. `intentos` lo incrementa
    el nodo de inferencia, donde se hace la llamada paga. `rechazos` lo incrementa la validación,
    una vez por ronda. Si alguno de los dos se olvidara, el otro igual termina el ciclo.

    Cuenta rondas y no reproches sueltos. Contarlos era el número correcto mientras la validación
    devolvía uno por vez, pero desde que junta todos los problemas de un borrador en una pasada, un
    borrador con cuatro problemas daba el presupuesto por agotado sin haber reintentado nunca.
    """
    return max(int(estado.get("intentos", 0)), int(estado.get("rechazos", 0)))


def decision_utilizable(estado: EstadoTriaje) -> bool:
    """Si la decisión se puede guardar como la respuesta del motor.

    Son dos condiciones y no una: que exista, y que sea defendible para este evento. Comprobar solo
    la existencia deja pasar un `informativo` sobre una transferencia de archivo, que contradice el
    registro en vez de ser una diferencia de criterio.
    """
    decision = estado.get("decision")
    if decision is None:
        return False
    evento = estado.get("evento")
    if evento is None:
        # Sin evento no hay piso contra el cual medir. No debería pasar (el estado inicial siempre
        # lo trae) y si pasa, el problema no es la severidad.
        return True
    return dentro_de_limites(decision.severidad, evento)


def ruta_tras_validar(estado: EstadoTriaje) -> str:
    """A dónde va el ciclo después de que la validación dijo lo suyo.

    Las dos ramas que no reintentan van a persistencia a propósito: una decisión que no se pudo
    validar igual se guarda, marcada como no concluyente, así el panel la puede mostrar como
    pendiente (CU-03) en vez de que el evento desaparezca sin dejar rastro.
    """
    if decision_utilizable(estado):
        return PERSISTENCIA

    # Reintentar sin un reproche es repetir la misma llamada: el proveedor no recibiría nada que
    # corregir. Cierra además el único camino por el que el bucle podía no terminar, porque una
    # validación que rechaza sin dejar reproche no mueve ningún contador.
    if not estado.get("reproches"):
        return PERSISTENCIA

    if intentos_gastados(estado) < MAX_INTENTOS:
        return INFERENCIA
    return PERSISTENCIA


def resultado_del_ciclo(estado: EstadoTriaje) -> MotivoDeCorte | None:
    """Por qué termina este ciclo. `None` significa que terminó con una decisión que vale guardar.

    Vive acá y no en persistencia porque es la contracara de `ruta_tras_validar`: separarlas dejaría
    que una diga "andá a persistir" y la otra no sepa por qué.
    """
    declarado = estado.get("motivo_de_corte")
    if declarado:
        return declarado
    if decision_utilizable(estado):
        return None
    return "esquema_invalido"


def construir_grafo(nodos: Mapping[str, Nodo] | None = None) -> Any:
    """Arma la topología y la compila. `nodos` permite reemplazar implementaciones de a una."""
    elegidos = {**nodos_disponibles(), **(nodos or {})}

    g: StateGraph[EstadoTriaje] = StateGraph(EstadoTriaje)
    for nombre in ORDEN:
        # El `cast` es contra una limitación de LangGraph, no contra un tipo mal puesto. `add_node`
        # acota el estado a un protocolo estructural, y su propio `_typing.py` lo avisa: "we cannot
        # use either TypedDict or dataclass directly due to limitations in type checking". Probamos
        # también con el TypedDict de typing_extensions (el que usa la propia biblioteca) y el
        # veredicto no cambia. En ejecución el nodo recibe y devuelve `EstadoTriaje`, que es lo que
        # declara `Nodo` unas líneas más arriba.
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
    """Corre un evento por el grafo, con el techo de pasos aplicado.

    Conviene usar siempre esta función y no invocar el grafo directamente. Invocarlo directo también
    funciona, pero se queda con el límite por defecto de LangGraph (diez mil pasos), y ese número no
    tiene ninguna relación con esta topología. En la práctica convierte un contrato incumplido en
    una factura.
    """
    resultado: EstadoTriaje = compilado.invoke(estado, config={"recursion_limit": LIMITE_DE_PASOS})
    return resultado


def describir() -> str:
    """La topología en texto, con el estado de cada nodo. Es lo que imprime `make grafo`."""
    disponibles = nodos_disponibles()
    lineas = ["Grafo de triaje", ""]
    for i, nombre in enumerate(ORDEN):
        listo = not disponibles[nombre].__name__.startswith("pendiente_")
        marca = "✅" if listo else "⏳"
        flecha = "   │" if i < len(ORDEN) - 1 else ""
        lineas.append(f"  {marca} {nombre:<14} {RESPONSABILIDAD[nombre]}")
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
