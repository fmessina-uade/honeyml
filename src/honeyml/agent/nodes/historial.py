"""Second node: what the past says about a case like this one.

The line between this node and the context node is worth stating, because both read from the index
and it would be easy to collapse them into one.

    contexto     ¿qué es este evento?      el hecho y sus circunstancias
    historial    ¿es parte de algo mayor?  la trayectoria y la ráfaga

The context node answers with facts about the event: who, from where, in which session, running
what. This one answers a question that no single event can settle — whether the address had already
climbed the scale before, and whether other addresses were doing the same thing at the same time.

WHY THAT SECOND QUESTION IS THE ONE THAT EARNS THE NODE

Everything the engine had until now is about one actor in isolation. But the corpus is mostly
automation: 73 % of the observed addresses never got past a probe, and the fingerprint families show
sequences repeated by hundreds of hosts. In that setting the interesting distinction is almost never
"what did this one do" — it is "how many of them are doing it right now".

The families already count how many addresses ever ran a sequence, over three months. That number
cannot separate a slow drip from a burst, and the difference between the two is the whole point:
forty addresses across a quarter is the background noise of the internet, forty inside one hour is a
push. The window is what makes the count mean something.

WHAT IT IS ALLOWED TO CONCLUDE: NOTHING

Same rule as the context node. This node retrieves and records; it does not weigh.
`maximo_alcanzado` is reported as the fact it is —"this address had already reached ALTO"— and never
turned into a recommendation to escalate. The margin of `severidad.MARGEN_DE_ESCALADA` is the
engine's to spend, with a justification, and pre-spending it here would hide the decision inside a
lookup.

THE PRECEDENT SEAM
The obvious third source of history is what the engine itself already decided about similar events,
which is what would make its answers consistent over time. That store belongs to the persistence
node and does not exist yet. Rather than pretend, the absence is written into `hallazgos`
explicitly: a model told that precedents were not consulted reasons differently from one that
believes there are none.
"""

from __future__ import annotations

from typing import Any
from urllib.error import URLError

from .. import tools
from ..state import EstadoTriaje

# Mismo criterio que en el nodo de contexto: el índice caído corta el ciclo, una consulta que falla
# se anota y sigue. Ver el encabezado de `nodes/contexto.py`.
SIN_INDICE = (URLError, ConnectionError, TimeoutError)

# Lo que se va a poder responder cuando exista el almacén de decisiones, y hoy no. Se declara para
# que la ausencia quede escrita en los hallazgos en vez de parecer un resultado vacío.
PRECEDENTES_PENDIENTES = "no consultados: todavía no hay almacén de decisiones"


def _intentar(nombre: str, hallazgos: dict[str, Any], fn: Any, *args: Any) -> Any:
    try:
        return fn(*args)
    except SIN_INDICE:
        raise
    except Exception as exc:  # noqa: BLE001 - ver el nodo de contexto
        hallazgos[f"{nombre}_falló"] = f"{type(exc).__name__}: {exc}"
        return None


def recuperar(estado: EstadoTriaje) -> EstadoTriaje:
    """Add the historical findings to the context the previous node assembled.

    Returns the same `contexto` key: the two nodes build one object between them, and splitting it
    into `contexto` and `contexto_historico` would leave the inference node stitching two halves
    back together on every call for no gain.
    """
    contexto = estado.get("contexto")
    evento = estado.get("evento")
    # El grafo solo llega acá con contexto armado —el corte por `sin_contexto` va directo a
    # persistencia—, pero un nodo que asume su predecesor y se equivoca falla de forma ilegible.
    if contexto is None or evento is None:
        return {}

    hallazgos = dict(contexto.hallazgos)

    trayectoria = _intentar(
        "trayectoria", hallazgos, tools.trayectoria_de_direccion, evento.source_ip, evento.timestamp
    )
    if trayectoria is not None:
        hallazgos["trayectoria"] = trayectoria

    rafaga = _intentar("rafaga", hallazgos, tools.rafaga_en_la_ventana, evento)
    if rafaga is not None:
        hallazgos["rafaga"] = rafaga

    hallazgos["precedentes"] = PRECEDENTES_PENDIENTES

    return {"contexto": contexto.model_copy(update={"hallazgos": hallazgos})}
