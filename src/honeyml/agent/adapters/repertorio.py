"""Qué firmas de conducta ya tienen una decisión, para no volver a pagarlas.

Misma frontera que `Almacen` y `ServicioDeInferencia`: el nodo depende del protocolo `Repertorio` y
no sabe que del otro lado hay un Redis. Así se prueba sin bus, que es lo que permite fijar el
comportamiento del ciclo sin levantar un contenedor.

Vive en Redis y no en Elasticsearch porque es una consulta por clave exacta en el camino caliente,
una por evento, y porque el bus ya está ahí. Tampoco hace falta que sea durable: si se pierde, lo
único que pasa es que las primeras repeticiones de cada firma se vuelven a pagar. Un repertorio
vacío da el comportamiento de antes, que sigue siendo correcto, solo que más caro.

Lo que se guarda es la decisión del proveedor, no el documento entero. Lo que depende del evento
(identidad, momento, origen, límites de severidad) se recalcula cada vez, así que copiarlo acá sería
guardar datos que van a estar mal en cuanto se reutilicen.
"""

from __future__ import annotations

import json
from typing import Any, Protocol

import redis

# Una clave por firma. El prefijo es el mismo estilo que `honeyml:visto:` del consumidor, así todo
# lo que el motor deja en Redis se lista con un solo patrón.
PREFIJO = "honeyml:firma:"

# Cuánto vive una firma resuelta.
#
# Treinta días. La cota de abajo la pone el atraso: reutilizar sirve mientras dure la puesta al día,
# que son varios días. La de arriba, que el criterio puede cambiar: si se ajusta la escala de
# severidad o el pedido, conviene que el repertorio se vacíe solo en un plazo razonable en lugar de
# arrastrar decisiones tomadas con las reglas viejas para siempre.
TTL = 60 * 60 * 24 * 30


class Repertorio(Protocol):
    """Lo único que el motor le pide al repertorio."""

    def consultar(self, firma: str) -> dict[str, Any] | None: ...

    def registrar(self, firma: str, decision: dict[str, Any], doc_id: str) -> None: ...


class RepertorioEnRedis:
    """El repertorio real, sobre el mismo Redis que lleva el bus."""

    def __init__(self, cliente: redis.Redis | None = None, ttl: int = TTL) -> None:
        self.r = cliente or redis.Redis(
            host="127.0.0.1", port=6379, decode_responses=True, socket_timeout=3
        )
        self.ttl = ttl
        self.aciertos = 0
        self.fallos = 0

    def consultar(self, firma: str) -> dict[str, Any] | None:
        """La decisión ya tomada para esta firma, o None.

        Un Redis caído no puede frenar el triaje: sin repertorio el evento va por el camino
        completo, que es el mismo que sigue con la reutilización apagada.
        """
        try:
            crudo = self.r.get(f"{PREFIJO}{firma}")
        except redis.RedisError:
            return None
        if not crudo:
            self.fallos += 1
            return None
        try:
            guardado: dict[str, Any] = json.loads(str(crudo))
        except json.JSONDecodeError:
            # Una entrada ilegible es basura, no una decisión: se ignora y la firma se vuelve a
            # resolver. Devolver algo a medias sería peor que pagar la llamada.
            return None
        self.aciertos += 1
        return guardado

    def registrar(self, firma: str, decision: dict[str, Any], doc_id: str) -> None:
        """Anota que esta firma ya tiene decisión, y de qué evento salió.

        `doc_id` viaja para que el documento de cada evento reutilizado pueda decir de dónde copió,
        que es lo que lo vuelve auditable: sin eso, una decisión reutilizada es indistinguible de
        una razonada.
        """
        carga = json.dumps({"decision": decision, "doc_id": doc_id}, ensure_ascii=False)
        try:
            self.r.set(f"{PREFIJO}{firma}", carga, ex=self.ttl)
        except redis.RedisError:
            # No registrar solo cuesta plata: la próxima repetición vuelve a preguntar. Frenar el
            # ciclo por esto costaría el evento, que es peor.
            return

    def resumen(self) -> str:
        total = self.aciertos + self.fallos
        if not total:
            return "    repertorio: sin consultas"
        return (
            f"    repertorio: {self.aciertos} reutilizadas de {total} "
            f"({self.aciertos / total * 100:.0f} %)"
        )
