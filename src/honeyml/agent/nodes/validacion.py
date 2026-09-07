"""Cuarto nodo: decide si lo que contestó el proveedor se puede usar, y si no, redacta el reproche.

Es el único nodo que no habla con nadie. No hay red, no hay índice, no hay proveedor: entra el
borrador y sale una decisión o una lista de reproches. Por eso tampoco levanta excepciones, a
diferencia de contexto y de historial: acá no hay nada que pueda estar caído.

El reproche tiene dos lectores y eso condiciona cómo se escribe. Uno es el modelo, que lo recibe en
el siguiente intento y tiene que poder corregir con eso. El otro es quien audite la decisión meses
después. Los errores crudos de Pydantic no le sirven a ninguno de los dos ("Input should be a valid
number" no dice qué campo ni qué se esperaba), así que se traducen nombrando el campo y el valor
admitido.

Todos los problemas se juntan en una sola pasada, en lugar de devolver el primero y cortar. Con el
presupuesto de tres intentos, señalar un error por vuelta significa que un borrador con dos
problemas los consume todos: el modelo arregla lo que le marcaron, rompe o deja lo otro, y el ciclo
termina sin decisión. Es la misma razón por la que "reproches" acumula en vez de pisarse.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError
from pydantic_core import ErrorDetails

from ...education.annotations import TACTICAS_OBSERVABLES
from ..consumer import EventoDelBus
from ..severidad import reproche as reproche_de_severidad
from ..state import Decision, EstadoTriaje

# Cómo se traduce cada clase de error de Pydantic. La clave es el `type` que trae el error, y el
# valor arma la oración con el campo adentro.
#
# El diccionario no pretende ser exhaustivo: `_texto` cae en un mensaje genérico que arrastra el
# original cuando aparece un tipo que no está acá. Preferimos eso a una tabla enorme que igual
# quedaría incompleta cuando Pydantic agregue un caso.
PLANTILLAS: dict[str, str] = {
    "missing": "Falta el campo '{campo}', que es obligatorio.",
    "extra_forbidden": "El campo '{campo}' no existe en el esquema y no se admite.",
    "enum": "El campo '{campo}' tiene un valor que no está en la lista admitida.",
    "string_too_short": "El campo '{campo}' no puede venir vacío.",
    "greater_than_equal": "El campo '{campo}' quedó por debajo del mínimo admitido.",
    "less_than_equal": "El campo '{campo}' superó el máximo admitido.",
    "float_parsing": "El campo '{campo}' tiene que ser un número.",
    "string_type": "El campo '{campo}' tiene que ser texto.",
    "list_type": "El campo '{campo}' tiene que ser una lista.",
    "bool_type": "El campo '{campo}' tiene que ser verdadero o falso.",
}

# La marca que deja el nodo de inferencia cuando la respuesta no era JSON. Con esquema estricto no
# debería pasar nunca, pero si el proveedor cambia de comportamiento conviene que se note como un
# reproche y no como una explosión.
CLAVE_SIN_PARSEAR = "_sin_parsear"


def _campo(loc: tuple[Any, ...]) -> str:
    """El nombre del campo tal como lo va a reconocer el modelo, no la ruta interna de Pydantic."""
    return ".".join(str(p) for p in loc) if loc else "(raíz)"


def _texto(error: ErrorDetails) -> str:
    campo = _campo(error.get("loc", ()))
    plantilla = PLANTILLAS.get(str(error.get("type", "")))
    if plantilla:
        return plantilla.format(campo=campo)
    return f"El campo '{campo}' no cumple el esquema: {error.get('msg', 'motivo no informado')}."


def _reproches_del_esquema(exc: ValidationError) -> list[str]:
    """Los errores de Pydantic, redactados de forma que el modelo pueda corregirlos.

    Se deduplica conservando el orden porque un mismo campo puede disparar dos errores (tipo y
    rango, por ejemplo) y repetir la corrección no agrega información al pedido.
    """
    vistos: dict[str, None] = {}
    for error in exc.errors():
        vistos.setdefault(_texto(error), None)
    return list(vistos)


def _reproches_de_contenido(decision: Decision, evento: EventoDelBus) -> list[str]:
    """Lo que el esquema no puede exigir, pero el motor sí.

    Son tres cosas que un JSON puede cumplir y aun así dejar la decisión inservible: que hable de
    otro evento, que no se apoye en nada, o que asigne una táctica que el señuelo no observa.
    """
    problemas: list[str] = []

    # Una decisión con el identificador equivocado es peor que ninguna: se persiste, queda
    # archivada bajo otro evento, y nada la vuelve a mirar.
    if decision.doc_id != evento.doc_id:
        problemas.append(
            f"El campo 'doc_id' dice '{decision.doc_id}' y el evento que se está clasificando es "
            f"'{evento.doc_id}'. Tiene que copiarse tal cual del contexto."
        )

    # El esquema admite una lista vacía y no hay forma de prohibirlo ahí. Pero una decisión sin los
    # hechos que la sostienen no se puede auditar, que es exactamente para lo que existe el campo.
    if not decision.evidencia:
        problemas.append(
            "El campo 'evidencia' vino vacío. Tiene que listar los hechos concretos del contexto "
            "en los que se apoya el nivel asignado."
        )

    if decision.tactica_mitre and decision.tactica_mitre not in TACTICAS_OBSERVABLES:
        admitidas = ", ".join(f"'{t}'" for t in TACTICAS_OBSERVABLES)
        problemas.append(
            f"La táctica '{decision.tactica_mitre}' no es una de las que este señuelo puede "
            f"observar. Las admitidas son {admitidas}, o nulo si ninguna aplica."
        )

    return problemas


def _rechazo(problemas: list[str]) -> EstadoTriaje:
    """Un rechazo es una ronda, traiga los problemas que traiga. Ver `graph.intentos_gastados`."""
    return {"reproches": problemas, "rechazos": 1}


def validar(estado: EstadoTriaje) -> EstadoTriaje:
    """Convierte el borrador en una decisión, o deja escrito por qué no se pudo.

    Devuelve `decision` cuando todo cierra, y `reproches` cuando no. Nunca las dos, y nunca ninguna:
    quien decide si se reintenta o se persiste es `graph.ruta_tras_validar`, que se apoya
    justamente en esa distinción.

    Cada rechazo suma uno a `rechazos`, sin importar cuántos problemas traiga. Ese contador es el
    que mide el presupuesto de intentos: los reproches pueden ser varios por ronda y no sirven para
    contar vueltas.
    """
    borrador = estado.get("borrador")
    evento = estado.get("evento")

    # El grafo no llega acá sin las dos cosas. Si igual pasara, devolver un reproche mandaría a
    # repetir una llamada que va a fallar igual, así que se sale sin decisión y sin reproche: el
    # ciclo lo lee como agotado y persiste el evento como no concluyente.
    if borrador is None or evento is None:
        return {}

    if CLAVE_SIN_PARSEAR in borrador:
        return _rechazo(
            [
                "La respuesta anterior no era JSON válido. Respondé únicamente con el objeto JSON "
                "que pide el esquema, sin texto alrededor."
            ]
        )

    try:
        decision = Decision.model_validate(borrador)
    except ValidationError as exc:
        return _rechazo(_reproches_del_esquema(exc))

    problemas = _reproches_de_contenido(decision, evento)

    # La severidad se comprueba con la función de `severidad.py` y no con una regla escrita acá. Es
    # la misma que usa el grafo para decidir si la decisión es utilizable, y tenerla en dos lugares
    # abriría la puerta a que la validación acepte lo que el grafo después descarta.
    fuera_de_escala = reproche_de_severidad(decision.severidad, evento)
    if fuera_de_escala:
        problemas.append(fuera_de_escala)

    if problemas:
        return _rechazo(problemas)
    return {"decision": decision}
