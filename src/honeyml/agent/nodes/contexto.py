"""First node of the graph: turn a bus message into something worth reasoning about.

What arrives from the bus is one line — this address, on this protocol, ran this. That is enough to
know something happened and not enough to say whether it matters. This node calls the read-only
lookups of `tools` and assembles the surroundings: what the address had already done, what else
happened in the same session, whether the sequence is one the corpus has seen thousands of times,
and what fraction of addresses ever get this far.

TWO KINDS OF FAILURE, KEPT APART

*The index is unreachable.* The node raises. Every lookup would come back empty, and an empty
context does not produce a worse decision — it produces a confident decision about nothing, at the
price of an inference call. Raising leaves the event unacknowledged so another consumer picks it up
once Elasticsearch is back. This is the same rule the graph applies to an unreachable provider, for
the same reason.

*One lookup fails or finds nothing.* Recorded and carried on. An address seen for the first time has
no history, and a Dionaea event has no session because that sensor does not have the concept — both
are ordinary, and neither should stop the cycle. What matters is that the gap is written down in
`hallazgos` rather than left implicit: a model that knows the history lookup failed reasons
differently from one that believes the address is new.

WHAT IT NEVER DOES
Interpret. No severity, no scoring, no filtering of what looks unimportant. If this node started
deciding what deserves attention, the classification would be partly made before the classifier
runs, and there would be no way to tell which part.
"""

from __future__ import annotations

from typing import Any
from urllib.error import URLError

from .. import tools
from ..state import Contexto, EstadoTriaje

# Fallos de transporte: el índice no está. Se distinguen de "la consulta no encontró nada", que es
# un resultado y no un fallo.
SIN_INDICE = (URLError, ConnectionError, TimeoutError)


def _intentar(nombre: str, hallazgos: dict[str, Any], fn: Any, *args: Any) -> Any:
    """Run one lookup, letting a transport failure through and recording anything else.

    El `except Exception` es deliberadamente ancho: una consulta que devuelve una forma inesperada,
    un campo que no está en el mapeo, un JSON que no parsea. Ninguna de esas justifica perder el
    evento, y todas tienen que quedar dichas en el contexto en lugar de parecer un resultado vacío.
    """
    try:
        return fn(*args)
    except SIN_INDICE:
        raise
    except Exception as exc:  # noqa: BLE001 - ver el docstring
        hallazgos[f"{nombre}_falló"] = f"{type(exc).__name__}: {exc}"
        return None


def construir(estado: EstadoTriaje) -> EstadoTriaje:
    """Assemble the context for this event. Returns the only key it touches."""
    evento = estado["evento"]

    # Sin dirección de origen no hay nada que consultar y nada que correlacionar: el evento se corta
    # acá en lugar de gastar una llamada de inferencia sobre una línea suelta.
    if not evento.source_ip:
        return {"motivo_de_corte": "sin_contexto"}

    hallazgos: dict[str, Any] = {}
    horizonte = evento.timestamp

    historial = _intentar(
        "historial", hallazgos, tools.historial_de_direccion, evento.source_ip, horizonte
    )
    if historial is not None:
        hallazgos["historial"] = historial

    origen = _intentar("origen", hallazgos, tools.origen_de_direccion, evento.source_ip)
    if origen:
        hallazgos["origen"] = origen

    # La sesión solo existe en Cowrie: Dionaea no emite identificador de sesión, así que preguntar
    # por ella devolvería vacío y parecería una sesión sin comandos, que es otra cosa.
    if evento.session:
        sesion = _intentar(
            "sesion", hallazgos, tools.comandos_de_la_sesion, evento.session, horizonte
        )
        if sesion:
            hallazgos["sesion"] = sesion
            familia = _intentar(
                "familia", hallazgos, tools.familia_de_la_sesion, sesion["comandos"]
            )
            if familia:
                hallazgos["familia"] = familia

    # El corpus va último y no depende del evento: es el denominador contra el cual se lee todo lo
    # anterior. Sin él, "ejecutó comandos y entró" se lee como algo común.
    poblacion = _intentar("arquetipos", hallazgos, tools.arquetipos_del_corpus)
    if poblacion:
        hallazgos["poblacion"] = poblacion

    return {
        "contexto": Contexto(
            doc_id=evento.doc_id,
            resumen=evento.resumen(),
            sensor=evento.honeypot,
            protocolo=evento.protocol,
            origen=evento.source_ip,
            usuario=evento.user,
            comando=evento.command,
            momento=evento.timestamp,
            hallazgos=hallazgos,
        )
    }
