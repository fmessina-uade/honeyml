"""Primer nodo del grafo: convierte un mensaje del bus en algo sobre lo que valga la pena razonar.

Lo que llega del bus es una línea: esta dirección, por este protocolo, ejecutó esto. Alcanza para
saber que algo pasó y no alcanza para decir si importa. Este nodo llama a las consultas de solo
lectura de `tools` y arma las circunstancias: qué había hecho antes esa dirección, qué más pasó en
la misma sesión, si la secuencia es una que el corpus ya vio miles de veces, y qué proporción de
direcciones llega hasta ahí.

Hay dos tipos de falla y conviene no mezclarlos. Si el índice no responde, el nodo levanta: con
todas las consultas vacías no sale una decisión peor sino una decisión confiada sobre nada, al
precio de una llamada paga. Si en cambio una consulta puntual falla o no encuentra nada, se anota y
se sigue, porque una dirección nueva no tiene historial y un evento de Dionaea no tiene sesión. Lo
que importa es que el hueco quede escrito en `hallazgos`: un modelo que sabe que la consulta de
historial falló razona distinto de uno que cree que la dirección es nueva.

Lo que este nodo nunca hace es interpretar. Si empezara a decidir qué merece atención, la
clasificación estaría hecha a medias antes de que corra el clasificador.
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
    """Corre una consulta: deja pasar la falla de transporte y anota cualquier otra cosa.

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
            categoria=evento.category,
            resultado=evento.outcome,
            sensor=evento.honeypot,
            protocolo=evento.protocol,
            origen=evento.source_ip,
            usuario=evento.user,
            comando=evento.command,
            momento=evento.timestamp,
            hallazgos=hallazgos,
        )
    }
