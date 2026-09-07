"""Qué viaja entre los nodos del grafo, y qué se le permite ser a una decisión.

Es el contrato contra el que está escrito el resto del motor: cada nodo lee algunas de estas claves
y escribe otras, y no cruza nada más.

Un `TypedDict` y no una dataclass porque LangGraph funde en el estado lo que devuelve cada nodo,
clave por clave. Con una dataclass, cambiar un campo obligaría a rearmar el objeto entero.

La escala de severidad no vive acá sino en `severidad.py`. Este módulo dice que una decisión lleva
un nivel; el otro dice qué niveles hay y qué evidencia establece cada uno.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field

from .consumer import EventoDelBus
from .severidad import Severidad

# Cuántas veces se le devuelve el reproche al proveedor antes de abandonar. Tres y no diez: si el
# modelo no acertó el esquema con el error explicado dos veces, la vuelta once tampoco lo va a
# arreglar, y cada intento es una llamada paga.
MAX_INTENTOS = 3


class Decision(BaseModel):
    """La respuesta del motor sobre un evento. Es el envoltorio, todavía no el vocabulario.

    Cada campo está para que quien lea pueda reconstruir por qué el motor dijo lo que dijo: una
    decisión de triaje que no se puede auditar es una opinión.
    """

    # `extra="forbid"` lo pide el modo estricto del proveedor, y además vale por sí mismo: un campo
    # que el modelo inventa y que nadie lee es una alucinación que pasa en silencio.
    model_config = ConfigDict(extra="forbid")

    doc_id: str = Field(description="identidad del evento en el índice")
    # Enum y no `str`: así el nodo de validación rechaza un nivel inventado sin escribir una sola
    # comprobación. Que el nivel además sea defendible para este evento es otra cosa, y la resuelve
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
    """Todo sobre lo que el modelo puede razonar. Lo arma el nodo de contexto, nunca el modelo.

    Estructura declarada y no texto libre, así lo que se le mostró al proveedor se puede
    reconstruir después. Un prompt armado por concatenación no.
    """

    doc_id: str
    resumen: str = Field(description="el evento en una línea")
    sensor: str = ""
    protocolo: str = ""
    origen: str = ""
    usuario: str = ""
    comando: str = ""
    momento: str = ""
    # Lo que aportan las consultas de `tools.py`. Vacío es un estado válido: una dirección vista
    # por primera vez no tiene historial, y eso es información, no una falla.
    hallazgos: dict[str, Any] = Field(default_factory=dict)


MotivoDeCorte = Literal[
    "esquema_invalido",  # el proveedor respondió, pero nunca en la forma pedida
    "sin_contexto",  # el evento no traía lo mínimo para razonar sobre él
]


class EstadoTriaje(TypedDict, total=False):
    """El paso de un evento por el grafo.

    `total=False` a propósito: cada nodo devuelve solo las claves que tocó, y esa lista es la forma
    más corta de decir qué hace.
    """

    evento: EventoDelBus
    contexto: Contexto
    # Lo que contestó el proveedor, todavía sin validar. Se guarda aparte de `decision` para que el
    # nodo de validación tenga algo que reprochar y el registro conserve qué se recibió realmente.
    borrador: dict[str, Any]
    decision: Decision
    intentos: int
    # Los errores de validación, redactados para devolvérselos al proveedor. El `operator.add` es
    # necesario: sin reductor, LangGraph pisa la clave en cada vuelta, y un modelo que arregla el
    # campo que le señalaron y rompe otro queda alternando entre dos errores sin verlos nunca
    # juntos.
    reproches: Annotated[list[str], operator.add]
    # Cuántas veces la validación rechazó, que no es lo mismo que cuántos reproches hay: una sola
    # ronda puede dejar cuatro. Existe como contador aparte porque el grafo necesita saber cuántos
    # intentos se gastaron, y contar reproches daba por agotado el presupuesto en la primera vuelta.
    rechazos: Annotated[int, operator.add]
    motivo_de_corte: MotivoDeCorte


def estado_inicial(evento: EventoDelBus) -> EstadoTriaje:
    return {"evento": evento, "intentos": 0, "reproches": [], "rechazos": 0}
