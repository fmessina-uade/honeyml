"""Dónde queda guardada una decisión, detrás de una interfaz para poder probar el nodo sin red.

Misma frontera que en `inferencia.py` y por el mismo motivo: el nodo de persistencia depende del
protocolo `Almacen` y no sabe que del otro lado hay un Elasticsearch. Acá no hay un proveedor que se
vaya a cambiar, pero la frontera igual paga: el nodo se prueba sin levantar el stack, que son
treinta segundos de arranque en cada corrida de las pruebas.

Las decisiones van a un solo índice, `honeyml-decisiones`, y no a uno por fecha como los eventos de
los honeypots, porque son una fracción del volumen de los sensores y entran en uno. Lo que más pesa
es la idempotencia: el identificador del documento es el `doc_id` del evento, así que escribir dos
veces el mismo evento choca con la primera escritura en vez de duplicarla. Con índices por fecha, un
reenvío que cruce la medianoche escribiría el mismo evento en dos índices distintos.

El mapeo va en `dynamic: strict` a propósito. Si el motor manda un campo que la plantilla no
declara, conviene que Elasticsearch rechace el documento y el evento vuelva al bus, en vez de que el
campo entre con un tipo adivinado y nadie se entere hasta que una consulta del panel devuelva algo
raro.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Protocol

INDICE = "honeyml-decisiones"
ES_URL_POR_DEFECTO = os.environ.get("ES_URL", "http://localhost:9200")

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


# Lo que contesta Elasticsearch a un `_create` sobre un documento que ya existe.
YA_EXISTE = 409
# Y a una consulta por un documento que no está, o sobre un índice que todavía no se creó.
NO_EXISTE = 404


class Almacen(Protocol):
    """Lo único que el nodo de persistencia necesita pedir.

    `guardar` devuelve si escribió. `False` quiere decir que ya había una decisión para ese evento y
    no se tocó, y no es una falla: es la respuesta correcta cuando llega una repetición.
    """

    def guardar(self, doc_id: str, documento: dict[str, Any]) -> bool: ...


class AlmacenConsultable(Almacen, Protocol):
    """El almacén que además sabe si un evento ya tiene decisión, que es lo que pregunta el motor.

    Va aparte de `Almacen` porque el nodo de persistencia no hace esa pregunta, y así sus pruebas no
    tienen que implementar una consulta que nunca usan.
    """

    def existe(self, doc_id: str) -> bool: ...


class AlmacenElastic:
    """Escribe en Elasticsearch por `urllib`, sin cliente, igual que el resto del proyecto."""

    def __init__(
        self, es_url: str = ES_URL_POR_DEFECTO, indice: str = INDICE, *, reescribir: bool = False
    ) -> None:
        self.es_url = es_url.rstrip("/")
        self.indice = indice
        self.reescribir = reescribir

    def guardar(self, doc_id: str, documento: dict[str, Any]) -> bool:
        """Indexa la decisión bajo el `doc_id` del evento, sin pisar una que ya esté.

        Escribe con `_create`, que contesta 409 si el documento existe. Un `PUT` a `_doc`
        sobrescribe, y eso solo sería seguro si las repeticiones llegaran a los minutos de un
        reinicio. Una relectura de Filebeat trae eventos decididos semanas antes, cuando la marca
        de deduplicación del consumidor, que vence a las 24 horas, dejó de reconocerlos, y con la
        reutilización encendida el evento de origen de una firma se copiaría de sí mismo y pisaría
        la decisión razonada.

        El reintento sigue siendo idempotente. Si un viaje falla pero la escritura llegó igual, el
        siguiente recibe 409 y se informa como ya existente: el documento es el nuestro de todos
        modos, y lo único que se pierde es registrar la firma, que cuesta a lo sumo una llamada más
        adelante. Tratarlo como escrito sería peor, porque ese mismo 409 también lo produce una
        repetición, y ahí se registraría una decisión distinta de la guardada.

        Con `reescribir` vuelve a sobrescribir, para triar otra vez a propósito.
        """
        if not doc_id:
            # No debería llegar: el consumidor aparta los eventos sin identificador. Igual se
            # comprueba, porque sin esto la URL queda sin identificador y Elasticsearch contesta un
            # 405 que no dice nada del problema real.
            raise AlmacenNoDisponibleError(
                "La decisión no trae doc_id y no hay bajo qué indexarla."
            )

        ultimo: Exception | None = None
        for intento in range(MAX_REINTENTOS):
            try:
                return self._escribir(doc_id, documento)
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

    def existe(self, doc_id: str) -> bool:
        """Si ya hay una decisión guardada para este evento, sin traer el documento.

        Una falla levanta como pasajera y, a diferencia de `guardar`, no se reintenta acá: todavía
        no se gastó ninguna llamada, así que devolver el evento al bus no cuesta nada.
        """
        pedido = urllib.request.Request(
            f"{self.es_url}/{self.indice}/_doc/{urllib.parse.quote(doc_id, safe='')}",
            method="HEAD",
        )
        try:
            with urllib.request.urlopen(pedido, timeout=TIMEOUT_SEGUNDOS):
                return True
        except urllib.error.HTTPError as exc:
            if exc.code == NO_EXISTE:
                return False
            raise AlmacenNoDisponibleError(
                f"Elasticsearch respondió {exc.code} al consultar {doc_id}.",
                pasajero=exc.code >= PRIMER_CODIGO_DEL_SERVIDOR,
            ) from exc
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            raise AlmacenNoDisponibleError(
                f"No se pudo alcanzar Elasticsearch para consultar {doc_id}: {exc}", pasajero=True
            ) from exc

    def _escribir(self, doc_id: str, documento: dict[str, Any]) -> bool:
        """Un solo viaje. `False` si el documento ya estaba; levanta si vale la pena reintentar."""
        operacion = "_doc" if self.reescribir else "_create"
        pedido = urllib.request.Request(
            f"{self.es_url}/{self.indice}/{operacion}/{urllib.parse.quote(doc_id, safe='')}",
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
            if exc.code == YA_EXISTE and not self.reescribir:
                return False
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
        return True
