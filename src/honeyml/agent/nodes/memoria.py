"""Primer nodo del grafo: si esta conducta ya se decidió, se copia la decisión y se termina.

Es el nodo más barato del motor y el que más plata ahorra. Calcula la firma del evento, la busca en
el repertorio, y cuando hay acierto el ciclo salta directo a persistencia: ni contexto, ni
historial, ni llamada al proveedor.

Va antes de contexto y no después a propósito. Puesto después, cada repetición seguiría costando las
cuatro o cinco consultas al índice que arma el contexto, y sobre decenas de miles de eventos son
cientos de miles de consultas para un resultado que nadie va a leer. Puesto acá, un acierto cuesta
una lectura en el bus.

La identidad del evento, su momento, su origen y los límites de severidad nunca se reutilizan: se
recalculan siempre, porque son del evento y no de la conducta. Y el documento que se persiste
declara de qué decisión copió: una decisión reutilizada tiene que ser distinguible de una razonada,
o el registro estaría afirmando algo que no pasó.
"""

from __future__ import annotations

from pydantic import ValidationError

from .. import firma as firma_del_evento
from ..adapters.repertorio import Repertorio
from ..state import Decision, EstadoTriaje


def recordar(estado: EstadoTriaje, repertorio: Repertorio | None = None) -> EstadoTriaje:
    """Busca la conducta en el repertorio y, si está, trae la decisión ya tomada.

    Sin repertorio inyectado el nodo no hace nada y el evento sigue por el camino completo. Es el
    comportamiento que hay que tener cuando la reutilización está apagada, y también el que deja
    correr las pruebas del grafo sin armar un repertorio de mentira en cada una.
    """
    evento = estado.get("evento")
    if evento is None:
        return {}

    marca = firma_del_evento.de_evento(evento)
    if repertorio is None:
        return {"firma": marca}

    guardado = repertorio.consultar(marca)
    if guardado is None:
        return {"firma": marca}

    try:
        decision = Decision.model_validate(guardado.get("decision") or {})
    except ValidationError:
        # El repertorio guardó algo que no valida con el modelo vigente: hay un campo nuevo, o
        # cambió una restricción. Se descarta y el evento se razona de nuevo, que es lo que
        # corresponde cuando el criterio cambió debajo de una decisión vieja.
        return {"firma": marca}

    return {
        "firma": marca,
        "decision": decision,
        "reutilizada_de": str(guardado.get("doc_id") or ""),
    }
