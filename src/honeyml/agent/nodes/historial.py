"""Segundo nodo: qué dice el pasado sobre un caso como este.

Está separado del nodo de contexto, aunque los dos lean del índice, porque contestan preguntas
distintas: contexto dice qué es este evento, y esto dice si es parte de algo mayor.

La ráfaga es lo que justifica el nodo. Las familias de huellas ya cuentan cuántas direcciones
ejecutaron una secuencia, pero sobre tres meses, y ese número no separa un goteo de una campaña:
cuarenta direcciones repartidas en un trimestre son el ruido de fondo de internet, y cuarenta
dentro de una hora son otra cosa. La ventana es lo que le da sentido al conteo.

Igual que el nodo de contexto, acá no se pondera nada: se recupera y se anota.
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
    """Suma los hallazgos históricos al contexto que armó el nodo anterior.

    Devuelve la misma clave `contexto` a propósito: entre los dos nodos construyen un solo objeto.
    """
    contexto = estado.get("contexto")
    evento = estado.get("evento")
    # El grafo solo llega acá con contexto armado (el corte por `sin_contexto` va directo a
    # persistencia), pero un nodo que da por sentado a su predecesor falla de forma ilegible.
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
