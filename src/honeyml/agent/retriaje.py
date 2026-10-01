"""Vuelve a triar, a propósito, los eventos de una categoría después de cambiar el criterio.

Hace falta cuando cambia lo que el motor puede decir sobre conductas ya decididas, como al sumar una
táctica al vocabulario. Sin esto el criterio nuevo solo alcanza a lo que llegue de acá en adelante:
el repertorio le copia la decisión vieja a cada repetición de la firma, y el almacén no reescribe lo
que ya está.

Los eventos salen del bus y no del almacén, porque la decisión guardada no conserva el usuario ni
el comando, y sin ellos no se puede recalcular la firma. Se borran del repertorio las firmas de esos
eventos y se los pasa por el grafo con un almacén que sobrescribe: el primero de cada firma se
razona, y paga, y los demás copian ese resultado nuevo.

No toca el grupo de consumidores, así que el motor sigue atendiendo el bus mientras tanto. Correrlo
dos veces no rompe nada: la segunda vuelve a razonar una vez por firma y reescribe lo mismo. Lo que
sí se pierde es la decisión anterior, así que conviene tener el volcado del día antes de empezar.

    python -m honeyml.agent.retriaje --categoria authentication --seco
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from collections.abc import Iterator
from typing import Any, cast

import redis

from . import consumer as bus
from . import firma
from .adapters.almacen import AlmacenElastic
from .adapters.config import CredencialAusenteError
from .adapters.inferencia import CuotaAgotadaError
from .adapters.repertorio import PREFIJO, RepertorioEnElBus
from .adapters.servicio import AdaptadorDeInferencia
from .graph import ejecutar
from .motor import compilar, costo_estimado
from .state import estado_inicial

# De a cuántos mensajes se lee el stream. Leerlo entero de una vez son decenas de megabytes en un
# contenedor con la memoria acotada, para algo que se recorre una sola vez.
PAGINA = 5000


def mensajes(r: redis.Redis, stream: str) -> Iterator[bus.EventoDelBus]:
    """Todo el stream, de a páginas, en el orden en que llegó."""
    desde = "-"
    while True:
        pagina = cast("list[bus.Mensaje]", r.xrange(stream, min=desde, count=PAGINA) or [])
        for eid, campos in pagina:
            yield bus.EventoDelBus.desde_mensaje(eid, campos)
        if len(pagina) < PAGINA:
            return
        desde = f"({pagina[-1][0]}"


def eventos_de(r: redis.Redis, stream: str, categoria: str) -> list[bus.EventoDelBus]:
    """Los eventos de la categoría, uno por `doc_id`.

    Una relectura o una reingesta pueden haber publicado dos veces el mismo evento, y decidirlo dos
    veces sería reescribir el mismo documento para nada.
    """
    vistos: dict[str, bus.EventoDelBus] = {}
    for evento in mensajes(r, stream):
        if evento.category == categoria and evento.doc_id and evento.doc_id not in vistos:
            vistos[evento.doc_id] = evento
    return list(vistos.values())


def main() -> int:
    ap = argparse.ArgumentParser(description="Vuelve a triar los eventos de una categoría.")
    ap.add_argument("--categoria", required=True, help="por ejemplo, authentication")
    ap.add_argument("--seco", action="store_true", help="contar y estimar, sin escribir nada")
    ap.add_argument("--host", default=bus.HOST)
    ap.add_argument("--puerto", type=int, default=bus.PORT)
    ap.add_argument("--stream", default=bus.STREAM)
    args = ap.parse_args()

    r = redis.Redis(host=args.host, port=args.puerto, decode_responses=True, socket_timeout=10)
    eventos = eventos_de(r, args.stream, args.categoria)
    firmas = {firma.de_evento(e) for e in eventos}
    print(f"  eventos de '{args.categoria}' en el bus: {len(eventos)}")
    print(f"  firmas distintas: {len(firmas)}")
    print(f"  gasto estimado: USD {costo_estimado(len(firmas)):.2f}")
    if args.seco or not eventos:
        return 0

    try:
        inferencia = AdaptadorDeInferencia()
    except CredencialAusenteError as exc:
        print(f"  No se puede arrancar: {exc}")
        return 1

    # Primero se olvidan las firmas y recién después se decide: al revés, el primer evento copiaría
    # la decisión vieja que se quiere rehacer.
    r.delete(*(PREFIJO + f for f in firmas))
    repertorio = RepertorioEnElBus(r)
    compilado = compilar(
        servicio=inferencia, almacen=AlmacenElastic(reescribir=True), repertorio=repertorio
    )

    tacticas: Counter[str] = Counter()
    razonadas = copiadas = 0
    for i, evento in enumerate(eventos, start=1):
        try:
            estado = estado_inicial(evento)
            estado["retriaje"] = True
            final: Any = ejecutar(compilado, estado)
        except CuotaAgotadaError as exc:
            print(f"\n  Se agotó la cuota del proveedor en el evento {i}: {exc}")
            print("  Lo ya reescrito queda; volver a correrlo retoma desde el principio.")
            return 2
        decision = final.get("decision")
        tacticas[decision.tactica_mitre if decision else "(sin decisión)"] += 1
        if final.get("reutilizada_de"):
            copiadas += 1
        else:
            razonadas += 1
        if i % 1000 == 0:
            print(f"  {i}/{len(eventos)}")

    print(f"\n  razonadas: {razonadas}   copiadas: {copiadas}")
    for tactica, cuantas in tacticas.most_common():
        print(f"    {tactica or 'sin táctica'}: {cuantas}")
    print("\n  consumo de inferencia")
    print(inferencia.resumen())
    return 0


if __name__ == "__main__":
    sys.exit(main())
