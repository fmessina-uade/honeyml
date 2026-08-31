"""What travels between the nodes of the triage graph, and what a decision is allowed to be.

This is the contract the rest of the engine is written against. Every node reads some of these
keys and writes others; nothing else crosses between them. Pinning it down before the nodes exist
is the point of the exercise — with the shape settled, the five nodes can be built in any order and
still fit together.

WHY A TypedDict AND NOT A DATACLASS
LangGraph merges what each node returns into the running state, key by key. A dataclass would force
every node to rebuild the whole object to change one field, and `total=False` lets a node return
only what it actually touched — which is also the clearest possible statement of what it does.

WHERE THE SEVERITY SCALE LIVES
In `severidad.py`, not here. This module says a decision carries a level; that one says which levels
exist, what evidence establishes each, and how far above the proven floor the engine may go. They
are separate because the second is a statement about the domain that the panel, the validation node
and the Fase 4 campaign all read — and only this one is about what travels between nodes.
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field

from .consumer import EventoDelBus
from .severidad import Severidad

# Cuántas veces se le devuelve el reproche al proveedor antes de abandonar. Tres y no diez: si el
# modelo no acertó el esquema con el error explicado dos veces, la vuelta once tampoco lo va a
# arreglar, y cada intento es una llamada paga.
MAX_INTENTOS = 3


class Decision(BaseModel):
    """The engine's answer about one event. This is the envelope, not yet the vocabulary.

    Every field exists so that a reader can reconstruct *why* the engine said what it said. The
    justification and the evidence are not decoration: a triage decision that cannot be audited is
    an opinion, and the whole point of the project is that this one can be checked against the
    telemetry it came from.
    """

    doc_id: str = Field(description="identidad del evento en el índice")
    # Enum y no `str`: la validación de la fila 84 rechaza un nivel inventado sin escribir una sola
    # comprobación, y el esquema que se le publica al proveedor lista los valores admitidos. Que un
    # nivel además sea *defendible para este evento* es otra cosa, y la resuelve
    # `severidad.dentro_de_limites`, que necesita el evento y por eso no puede vivir acá.
    severidad: Severidad = Field(description="nivel asignado; la escala vive en severidad.py")
    confianza: float = Field(ge=0.0, le=1.0)
    tactica_mitre: str | None = Field(default=None, description="táctica observada, si aplica")
    justificacion: str = Field(min_length=1, description="por qué, en una o dos oraciones")
    evidencia: list[str] = Field(
        default_factory=list,
        description="hechos del contexto en los que se apoya; sin esto no se puede auditar",
    )
    # Ver `motivo_de_corte`: una decisión no concluyente sigue siendo una decisión persistida, y
    # tiene que poder distinguirse de una que el motor sí pudo tomar.
    concluyente: bool = True


class Contexto(BaseModel):
    """Everything the model gets to reason over. Assembled by fila 81, never by the model itself.

    Kept as a declared structure rather than a free-form string so that what was shown to the
    provider is reproducible after the fact. A prompt built by concatenation cannot be reconstructed
    from the decision it produced.
    """

    doc_id: str
    resumen: str = Field(description="el evento en una línea")
    sensor: str = ""
    protocolo: str = ""
    origen: str = ""
    usuario: str = ""
    comando: str = ""
    momento: str = ""
    # Lo que aportan las herramientas de la fila 73. Vacío es un estado válido: una dirección vista
    # por primera vez no tiene historial, y eso es información, no una falla.
    hallazgos: dict[str, Any] = Field(default_factory=dict)


MotivoDeCorte = Literal[
    "esquema_invalido",  # el proveedor respondió, pero nunca en la forma pedida
    "sin_contexto",  # el evento no traía lo mínimo para razonar sobre él
]


class EstadoTriaje(TypedDict, total=False):
    """One event's trip through the graph.

    `total=False` a propósito: cada nodo devuelve solo las claves que tocó, y la lista de claves de
    su `return` es la declaración más corta y más honesta de qué hace ese nodo.
    """

    evento: EventoDelBus
    contexto: Contexto
    # Lo que contestó el proveedor, todavía sin validar. Se guarda aparte de `decision` para que el
    # nodo de validación tenga algo que reprochar y el registro conserve qué se recibió realmente.
    borrador: dict[str, Any]
    decision: Decision
    intentos: int
    # Los errores de validación, redactados para devolvérselos al proveedor. Se acumulan en vez de
    # reemplazarse: un modelo que arregla el campo que le señalaron y rompe otro tiene que ver los
    # dos, o el ciclo se queda alternando entre dos errores hasta agotar los intentos.
    reproches: list[str]
    motivo_de_corte: MotivoDeCorte


def estado_inicial(evento: EventoDelBus) -> EstadoTriaje:
    """The only entry point: a bus event and nothing else decided yet."""
    return {"evento": evento, "intentos": 0, "reproches": []}
