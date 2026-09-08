"""Dónde queda guardada una decisión, detrás de una interfaz para poder probar el nodo sin red.

Misma frontera que en `inferencia.py` y por el mismo motivo: el nodo de persistencia depende del
protocolo `Almacen` y no sabe que del otro lado hay un Elasticsearch. Acá el proveedor no se cambió
nunca, pero la frontera igual paga: el nodo se prueba sin levantar el stack, que son treinta
segundos de arranque en cada corrida de las pruebas.

Un solo índice, `honeyml-decisiones`, y no uno por fecha como los de los honeypots. Aquellos reciben
unos 40.000 eventos por día y el corte diario tiene sentido; acá son unas 800, así que un índice por
día serían 365 fragmentos al año para un volumen que entra en uno.

Pero el argumento que decide es la idempotencia. El identificador del documento es el `doc_id` del
evento, así que reescribir la decisión de un evento la sobrescribe en lugar de duplicarla. Con
índices por fecha eso se rompe: un reenvío que cruce la medianoche escribiría el mismo evento en dos
índices distintos, y el duplicado es justamente lo que el identificador determinístico evita.

El mapeo va en `dynamic: strict` a propósito. Si el motor algún día manda un campo que la plantilla
no declara, conviene que Elasticsearch rechace el documento y el evento vuelva al bus, en vez de que
el campo entre con un tipo adivinado y nadie se entere hasta que una consulta del panel devuelva
algo raro.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Protocol

INDICE = "honeyml-decisiones"
ES_URL_POR_DEFECTO = "http://localhost:9200"

# Suficiente para una escritura de un documento chico. Si tarda más que esto, el problema no es la
# latencia: el índice no está sano y conviene devolver el evento al bus.
TIMEOUT_SEGUNDOS = 15

# Reintentos ante una falla pasajera, y por qué existen habiendo un bus que reintenta solo.
#
# Porque no cuestan lo mismo. Si esto levanta, el evento vuelve al bus y la siguiente entrega
# rehace el ciclo entero, inferencia incluida: hasta tres llamadas pagas de nuevo por un parpadeo de
# un segundo en el índice. Reintentar acá cambia esa reentrega por medio segundo de espera.
#
# Tres intentos y no más: si el índice sigue sin responder después de eso, no es un parpadeo, y ahí
# sí conviene devolver el evento al bus y liberar al consumidor.
MAX_REINTENTOS = 3
ESPERA_BASE = 0.5

# Desde este código HTTP para arriba, el problema es del servidor y vale reintentar. Un 4xx es un
# defecto nuestro (un campo que el mapeo estricto rechaza, por ejemplo) y repetirlo da lo mismo.
PRIMER_CODIGO_DEL_SERVIDOR = 500


class AlmacenNoDisponibleError(RuntimeError):
    """No se pudo guardar. El evento no se confirma y otro consumidor lo va a reclamar.

    `pasajero` distingue las dos formas de fallar, que no se tratan igual. Un timeout o un 5xx
    pueden andar en el próximo intento. Un 4xx es un defecto nuestro, un campo que el mapeo estricto
    rechaza, y repetirlo tres veces solo demora el diagnóstico.
    """

    def __init__(self, mensaje: str, *, pasajero: bool = False) -> None:
        super().__init__(mensaje)
        self.pasajero = pasajero


class Almacen(Protocol):
    """Lo único que el nodo de persistencia necesita pedir."""

    def guardar(self, doc_id: str, documento: dict[str, Any]) -> None: ...


class AlmacenElastic:
    """Escribe en Elasticsearch por `urllib`, sin cliente, igual que el resto del proyecto."""

    def __init__(self, es_url: str = ES_URL_POR_DEFECTO, indice: str = INDICE) -> None:
        self.es_url = es_url.rstrip("/")
        self.indice = indice

    def guardar(self, doc_id: str, documento: dict[str, Any]) -> None:
        """Indexa la decisión bajo el `doc_id` del evento, reintentando si la falla es pasajera.

        Usa `PUT /_doc/<id>`, que sobrescribe. Es lo que hace idempotente al reintento, tanto al de
        acá como al del bus: el consumidor marca el evento como procesado recién después de que esto
        retorna, así que una caída entre ambos pasos deja el evento pendiente y la vuelta siguiente
        reescribe el mismo documento en lugar de agregar otro.
        """
        if not doc_id:
            # No debería llegar: el consumidor aparta los eventos sin identificador. Igual se
            # comprueba, porque sin esto la URL queda en `/_doc/` y Elasticsearch contesta un 405
            # que no dice nada del problema real.
            raise AlmacenNoDisponibleError(
                "La decisión no trae doc_id y no hay bajo qué indexarla."
            )

        ultimo: Exception | None = None
        for intento in range(MAX_REINTENTOS):
            try:
                self._escribir(doc_id, documento)
                return
            except AlmacenNoDisponibleError as exc:
                if not exc.pasajero:
                    raise
                ultimo = exc
                if intento < MAX_REINTENTOS - 1:
                    time.sleep(ESPERA_BASE * (2**intento))
        raise AlmacenNoDisponibleError(
            f"Elasticsearch no respondió en {MAX_REINTENTOS} intentos ({doc_id}): {ultimo}",
            pasajero=True,
        ) from ultimo

    def _escribir(self, doc_id: str, documento: dict[str, Any]) -> None:
        """Un solo viaje. Marca la excepción como pasajera cuando vale la pena reintentar."""
        pedido = urllib.request.Request(
            f"{self.es_url}/{self.indice}/_doc/{urllib.parse.quote(doc_id, safe='')}",
            data=json.dumps(documento, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        try:
            with urllib.request.urlopen(pedido, timeout=TIMEOUT_SEGUNDOS) as resp:
                if resp.status not in (200, 201):
                    raise AlmacenNoDisponibleError(
                        f"Elasticsearch respondió {resp.status} al guardar {doc_id}."
                    )
        except urllib.error.HTTPError as exc:
            # El cuerpo del 400 dice qué campo rechazó el mapeo estricto, y sin eso el diagnóstico
            # es adivinar. Se lee una sola vez porque el flujo no se puede releer.
            detalle = exc.read().decode("utf-8", "replace")[:400]
            raise AlmacenNoDisponibleError(
                f"Elasticsearch rechazó la decisión de {doc_id} ({exc.code}): {detalle}",
                pasajero=exc.code >= PRIMER_CODIGO_DEL_SERVIDOR,
            ) from exc
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            raise AlmacenNoDisponibleError(
                f"No se pudo alcanzar Elasticsearch para guardar {doc_id}: {exc}", pasajero=True
            ) from exc
