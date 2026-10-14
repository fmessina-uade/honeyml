"""La marca que dice que el proveedor de inferencia dejó de aceptar pedidos por saldo o por cuota.

La pone el motor cuando choca con la cuota y la saca cuando el proveedor vuelve a responder; la lee
la API para que el panel avise. Lo que significa es preciso: el último pedido al proveedor se
rechazó por cuota y desde entonces ninguno salió bien. Mientras el motor solo copia del repertorio
no le pide nada al proveedor, así que la marca sigue puesta aunque las decisiones copiadas sigan
llegando.

Vive en el bus porque el motor y la API ya hablan con él, y no en el índice porque es un estado del
momento y no un registro. Vence sola a las veinticuatro horas para que un motor que se apagó con la
marca puesta no deje el aviso colgado para siempre; un motor vivo la renueva en cada reintento.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import redis

from .. import consumer as bus

CLAVE = "honeyml:motor:sin_saldo"
VIGENCIA_S = 24 * 60 * 60

# El motivo es el mensaje de `CuotaAgotadaError`, que ya dice qué pasó y cómo se resuelve. Se
# recorta porque viaja al panel en cada resumen.
LARGO_DEL_MOTIVO = 300


class MarcaSinSaldo:
    """La marca en el bus. Ningún método levanta: el aviso no puede voltear al motor ni a la API."""

    def __init__(self, cliente: redis.Redis | None = None) -> None:
        self.r = cliente or redis.Redis(
            host=bus.HOST,
            port=bus.PORT,
            password=bus.PASSWORD,
            decode_responses=True,
            socket_timeout=2,
            socket_connect_timeout=2,
        )

    def poner(self, motivo: str, vigencia_s: int = VIGENCIA_S) -> None:
        """Pone la marca o la renueva, conservando desde cuándo falta el saldo."""
        ahora = datetime.now(UTC).isoformat(timespec="seconds")
        previa = self.leer()
        carga = {
            "desde": (previa or {}).get("desde") or ahora,
            "ultimo_intento": ahora,
            "motivo": motivo[:LARGO_DEL_MOTIVO],
        }
        try:
            self.r.set(CLAVE, json.dumps(carga, ensure_ascii=False), ex=vigencia_s)
        except redis.RedisError:
            return

    def quitar(self) -> None:
        try:
            self.r.delete(CLAVE)
        except redis.RedisError:
            return

    def leer(self) -> dict[str, Any] | None:
        """La marca, o None si no está o si el bus no responde.

        Con el bus caído no se puede saber, y avisar "sin saldo" sobre algo que no se midió sería
        peor que no avisar: el panel ya muestra por su lado cuándo llegó la última decisión.
        """
        try:
            crudo = self.r.get(CLAVE)
        except redis.RedisError:
            return None
        if not crudo:
            return None
        try:
            dato = json.loads(str(crudo))
        except json.JSONDecodeError:
            return None
        return dato if isinstance(dato, dict) else None
