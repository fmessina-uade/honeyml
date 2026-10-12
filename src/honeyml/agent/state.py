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
from .severidad import Severidad, dentro_de_limites

# Cuántas veces se le devuelve el reproche al proveedor antes de abandonar. Tres y no diez: si el
# modelo no acertó el esquema con el error explicado dos veces, la vuelta once tampoco lo va a
# arreglar, y cada intento es una llamada paga.
MAX_INTENTOS = 3

# Cómo anotan los nodos de contexto e historial una consulta que falló: `historial_falló`, con el
# mensaje del error como valor. Persistencia lo busca por este sufijo para marcar la decisión para
# revisión, así que los tres lo toman de acá.
SUFIJO_DE_FALLA = "_falló"

# Por qué una decisión no lleva táctica. Un nulo solo no distingue una acción sin propósito (un
# `cd`, un `echo` de marcador) de un comando que no se entiende, ni de una conducta clara que el
# vocabulario no cubre, como una transferencia de archivos sin ejecución. Son tres lecturas que
# piden cosas distintas a quien revisa.
MotivoSinTactica = Literal[
    "sin_objetivo_tactico",
    "evidencia_insuficiente",
    "fuera_del_catalogo",
]


class Decision(BaseModel):
    """La respuesta del motor sobre un evento. Es el envoltorio, todavía no el vocabulario.

    Cada campo está para que quien lea pueda reconstruir por qué el motor dijo lo que dijo: una
    decisión de triaje que no se puede auditar es una opinión.
    """

    # `extra="forbid"` lo pide el modo estricto del proveedor, y además vale por sí mismo: un campo
    # que el modelo inventa y que nadie lee es una alucinación que pasa en silencio.
    model_config = ConfigDict(extra="forbid")

    # El `doc_id` no está acá a propósito. Es un SHA-256 de 64 caracteres hexadecimales, y copiar
    # eso exacto es justo lo que un modelo hace mal: exigirlo costaría un reproche y un reintento
    # pago por cada carácter errado, sobre una severidad que puede estar bien juzgada.
    #
    # Tampoco hace falta: persistencia indexa bajo el `doc_id` del evento, que viene del bus, y el
    # anclaje al contexto lo verifica `evidencia`, que tiene que citar hechos concretos y no puede
    # venir vacía.
    #
    # Sigue viajando en el pedido como parte del contexto, para que el prompt reconstruido
    # identifique su evento. Lo que no se pide es devolverlo.
    #
    # `concluyente` tampoco está, por lo mismo. Describe cómo terminó el ciclo, que el modelo no
    # puede saber, y el nodo de persistencia lo escribe desde `resultado_del_ciclo`. Pedírselo sería
    # obligarlo a inventar un valor que después se descarta.

    # Enum y no `str`: así el nodo de validación rechaza un nivel inventado sin escribir una sola
    # comprobación. Que el nivel además sea defendible para este evento es otra cosa, y la resuelve
    # `severidad.dentro_de_limites`, que necesita el evento y por eso no puede vivir acá.
    severidad: Severidad = Field(description="nivel asignado; la escala vive en severidad.py")
    confianza: float = Field(ge=0.0, le=1.0)
    tactica_mitre: str | None = Field(default=None, description="táctica observada, si aplica")
    # Sin valor por defecto a propósito: una decisión guardada en el repertorio antes de que el
    # campo existiera no valida, y `memoria.recordar` la descarta. Así cada conducta se vuelve a
    # razonar con el criterio de táctica vigente en vez de copiar uno que ya no rige.
    motivo_sin_tactica: MotivoSinTactica | None = Field(
        description="por qué no hay táctica; nulo cuando la hay"
    )
    justificacion: str = Field(min_length=1, description="por qué, en una o dos oraciones")
    evidencia: list[str] = Field(
        default_factory=list,
        description="hechos del contexto en los que se apoya; sin esto no se puede auditar",
    )


class Contexto(BaseModel):
    """Todo sobre lo que el modelo puede razonar. Lo arma el nodo de contexto, nunca el modelo.

    Estructura declarada y no texto libre, así lo que se le mostró al proveedor se puede
    reconstruir después. Un prompt armado por concatenación no.
    """

    doc_id: str
    resumen: str = Field(description="el evento en una línea")
    # La categoría y el resultado son los dos campos de los que la escala deriva el piso, así que
    # sin ellos el modelo no lo puede calcular: una autenticación exitosa llegaría como `bajo` con
    # su reproche, porque el modelo vería "authentication" sin saber si prosperó y elegiría el
    # nivel más bajo, que es lo que el propio pedido le pide ante la duda.
    categoria: str = ""
    resultado: str = ""
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
    # Qué modelo contestó y cuánto costó la llamada que produjo el borrador vigente. Viaja en el
    # estado porque el contador del adaptador vive en memoria y se pierde al reiniciar, y "cuántos
    # eventos resolvió el modelo económico" es una de las métricas que hay que poder informar.
    consumo: dict[str, Any]
    intentos: int
    # Los errores de validación, redactados para devolvérselos al proveedor. El `operator.add` es
    # necesario: sin reductor, LangGraph pisa la clave en cada vuelta, y un modelo que arregla el
    # campo que le señalaron y rompe otro queda alternando entre dos errores sin verlos nunca
    # juntos.
    reproches: Annotated[list[str], operator.add]
    # Cuántas veces la validación rechazó, que no es lo mismo que cuántos reproches hay: una sola
    # ronda puede dejar cuatro. Existe como contador aparte porque el grafo necesita saber cuántos
    # intentos se gastaron, y contar reproches daría por agotado el presupuesto en la primera
    # vuelta.
    rechazos: Annotated[int, operator.add]
    motivo_de_corte: MotivoDeCorte
    # La firma de conducta del evento, calculada por el primer nodo. Viaja en el estado porque la
    # calcula uno y la usan dos: el nodo de memoria para buscar y el de persistencia para registrar.
    firma: str
    # El `doc_id` del evento cuya decisión se copió, cuando la firma ya estaba resuelta. Vacío o
    # ausente quiere decir que esta decisión se razonó. Es lo que separa una cosa de la otra en el
    # registro, así que se guarda en el documento y no solo en el estado.
    reutilizada_de: str
    # Que la decisión de este evento ya estaba guardada y no se tocó. Lo pone la persistencia, y el
    # motor lo usa para que el consumidor cuente el evento como repetido y no como procesado.
    ya_existia: bool
    # Que esta decisión reemplaza a otra, porque se volvió a triar a propósito tras cambiar el
    # criterio. Se guarda porque su marca temporal ya no mide cuánto tardó el motor: el evento pudo
    # haber ocurrido semanas antes de que se lo volviera a decidir.
    retriaje: bool


def estado_inicial(evento: EventoDelBus) -> EstadoTriaje:
    return {"evento": evento, "intentos": 0, "reproches": [], "rechazos": 0}


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


def resultado_del_ciclo(estado: EstadoTriaje) -> MotivoDeCorte | None:
    """Por qué termina este ciclo. `None` significa que terminó con una decisión que vale guardar.

    Las dos funciones de acá abajo son predicados sobre el estado, no topología, y por eso viven en
    este módulo y no en `graph.py`: el nodo de persistencia necesita la segunda, y un nodo
    importando el grafo que lo importa a él es un ciclo. La dependencia tiene que ir en un solo
    sentido. Que las lean el grafo y un nodo es justamente la señal de que son del contrato.
    """
    declarado = estado.get("motivo_de_corte")
    if declarado:
        return declarado
    if decision_utilizable(estado):
        return None
    return "esquema_invalido"
