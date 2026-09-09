"""Une el bus con el grafo: lo que convierte cinco nodos sueltos en un motor que corre.

Hasta acá el grafo funcionaba y nadie lo llamaba. `make consumer` leía el bus con
`manejador_de_registro`, que imprime el evento y lo confirma, y el grafo solo se ejercitaba desde
las pruebas. Este módulo es la pieza que faltaba, y la única que conoce a los dos lados.

Vive aparte, y no dentro del consumidor ni del grafo, porque la dependencia tiene que ir en un solo
sentido. El grafo importa los nodos, los nodos importan el consumidor para tipar el evento; si el
consumidor importara el grafo, el círculo se cierra. Acá arriba de los dos no hay ciclo.

Los adaptadores se crean una sola vez y se inyectan en los nodos. Es la diferencia que más se
nota en operación: creados por evento, el desglose de consumo por modelo arrancaba de cero cada vez
y "cuántos eventos resolvió el modelo económico" respondía siempre uno, además de releer la
configuración del disco en cada llamada.

El contrato con el consumidor es el mismo de siempre y no hace falta cambiarlo. Si el ciclo levanta,
sea porque el índice no responde, porque no se alcanzó al proveedor o porque el almacén rechazó la
decisión, la excepción sale, el evento no se confirma y otro consumidor lo reclama. Si retorna, la
decisión ya está guardada.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from typing import Any

import redis

from . import consumer as bus
from .adapters.almacen import Almacen, AlmacenElastic
from .adapters.config import MODELO_POR_DEFECTO, CredencialAusenteError
from .adapters.inferencia import PRECIOS
from .adapters.servicio import AdaptadorDeInferencia, ServicioDeInferencia
from .graph import INFERENCIA, PERSISTENCIA, construir_grafo, ejecutar
from .nodes import inferencia as nodo_inferencia
from .nodes import persistencia as nodo_persistencia
from .state import EstadoTriaje, estado_inicial, resultado_del_ciclo

# Tamaño de atraso a partir del cual el motor se niega a arrancar sin que se lo pidan explícito.
#
# Dos mil eventos son unos dos días y medio de tráfico, así que ponerse al día tras un fin de semana
# no molesta. Por encima de eso ya es reprocesamiento histórico, y ahí conviene que lo diga quien
# corre el comando: el bus tenía 52.165 mensajes acumulados al 25/08, que a precio de una llamada
# por evento son entre siete y quince dólares. Un `make triaje` sin argumentos no puede gastar eso
# por accidente.
TOPE_SIN_CONFIRMAR = 2000

# Tokens de una llamada típica, medidos sobre el corpus. Sirven para estimar el gasto antes de
# arrancar, no para contabilizarlo: lo real lo lleva el adaptador y queda en cada decisión.
TOKENS_TIPICOS = (1200, 180)


def compilar(servicio: ServicioDeInferencia | None = None, almacen: Almacen | None = None) -> Any:
    """Arma el grafo con los adaptadores ya inyectados, una sola vez por corrida.

    Los dos nodos que hablan con el mundo reciben su dependencia acá. El resto de la topología queda
    tal como la define `construir_grafo`, así que esto no puede cambiar el orden de los nodos ni las
    condiciones de las aristas por accidente.
    """
    inferencia = servicio or AdaptadorDeInferencia()
    destino = almacen or AlmacenElastic()
    return construir_grafo(
        {
            INFERENCIA: lambda estado: nodo_inferencia.consultar(estado, servicio=inferencia),
            PERSISTENCIA: lambda estado: nodo_persistencia.guardar(estado, almacen=destino),
        }
    )


def costo_estimado(eventos: int) -> float:
    """Cuánto costaría triar esa cantidad, con una llamada por evento al modelo más caro.

    Es un techo para el caso feliz y un piso para el peor: un evento que necesita corrección gasta
    una llamada por intento. Alcanza para decidir si conviene arrancar.
    """
    entrada, salida = TOKENS_TIPICOS
    p_entrada, p_salida = PRECIOS[MODELO_POR_DEFECTO]
    return eventos * (entrada * p_entrada + salida * p_salida) / 1_000_000


def atraso(consumidor: bus.ConsumidorDelBus) -> int:
    """Cuántos eventos le quedan por atender al grupo, antes de gastar una sola llamada.

    Si el grupo ya existe, `XINFO GROUPS` informa el rezago. Si todavía no existe, se va a crear
    desde el inicio del stream, así que lo que va a ver es todo lo acumulado.
    """
    try:
        for grupo in consumidor.r.xinfo_groups(consumidor.stream):
            if grupo.get("name") == consumidor.grupo:
                rezago = grupo.get("lag")
                return (
                    int(rezago) if rezago is not None else int(consumidor.r.xlen(consumidor.stream))
                )
        return int(consumidor.r.xlen(consumidor.stream))
    except redis.ResponseError:
        # El stream todavía no existe: no hay nada que triar.
        return 0


def _linea(evento: bus.EventoDelBus, final: EstadoTriaje) -> str:
    """Una línea por evento, para ver la corrida sin abrir Kibana."""
    decision = final.get("decision")
    if decision is None:
        return f"  ? {resultado_del_ciclo(final)}: {evento.resumen()}"

    intentos = int(final.get("intentos", 0))
    corregido = f" tras {intentos} intentos" if intentos > 1 else ""
    tactica = decision.tactica_mitre or "sin táctica"
    return f"  · {decision.severidad.value:<10} {tactica:<22}{corregido} {evento.resumen()}"


def manejador(
    servicio: ServicioDeInferencia | None = None, almacen: Almacen | None = None
) -> Callable[[bus.EventoDelBus], None]:
    """El manejador que reemplaza a `manejador_de_registro`: corre un evento por el grafo.

    Devuelve una función y no una clase porque el consumidor solo pide eso. El grafo compilado queda
    capturado en la clausura, así se arma una vez y no por evento.
    """
    compilado = compilar(servicio=servicio, almacen=almacen)

    def triar(evento: bus.EventoDelBus) -> None:
        final = ejecutar(compilado, estado_inicial(evento))
        print(_linea(evento, final))

    return triar


def main() -> int:
    ap = argparse.ArgumentParser(description="Motor de triaje: consume el bus y clasifica.")
    ap.add_argument("--host", default=bus.HOST)
    ap.add_argument("--puerto", type=int, default=bus.PORT)
    ap.add_argument("--stream", default=bus.STREAM)
    ap.add_argument("--grupo", default=bus.GROUP)
    ap.add_argument("--nombre", default=None, help="nombre del consumidor dentro del grupo")
    ap.add_argument("--lote", type=int, default=10)
    ap.add_argument("--limite", type=int, default=None, help="triar N eventos y salir")
    ap.add_argument(
        "--desde-ahora",
        action="store_true",
        help="si el grupo es nuevo, ignorar lo acumulado y tomar solo lo que llegue",
    )
    ap.add_argument(
        "--todo",
        action="store_true",
        help=f"triar el atraso completo aunque supere los {TOPE_SIN_CONFIRMAR} eventos",
    )
    args = ap.parse_args()

    # El adaptador se crea acá y no dentro del manejador para poder pedirle el resumen al final.
    try:
        inferencia = AdaptadorDeInferencia()
    except CredencialAusenteError as exc:
        print(f"✗ {exc}")
        return 1

    consumidor = bus.ConsumidorDelBus(
        manejador(servicio=inferencia),
        host=args.host,
        puerto=args.puerto,
        stream=args.stream,
        grupo=args.grupo,
        nombre=args.nombre,
        lote=args.lote,
    )

    try:
        consumidor.r.ping()
    except redis.RedisError as exc:
        print(f"  El bus no responde en {args.host}:{args.puerto} ({exc}).")
        print("  Levantalo con: make bus-up")
        return 1

    falta = atraso(consumidor)
    print(f"  atraso del grupo '{args.grupo}': {falta:,} evento(s)".replace(",", "."))
    if falta:
        print(f"  gasto estimado si se tría todo: USD {costo_estimado(falta):.2f}")

    if args.limite is None and falta > TOPE_SIN_CONFIRMAR and not args.todo:
        print(
            f"\n  Son más de {TOPE_SIN_CONFIRMAR} eventos y no se pidió un límite. Para no gastar "
            "eso sin querer, el motor no arranca solo.\n"
            "    make triaje LIMITE=20     para probar con veinte\n"
            "    make triaje TODO=1        para triar el atraso completo"
        )
        return 1

    c = consumidor.correr(limite=args.limite, desde_ahora=args.desde_ahora)

    print("\n  resumen del bus")
    print(f"    procesados:  {c.procesados}")
    print(f"    repetidos:   {c.repetidos}   (mismo doc_id ya resuelto)")
    print(f"    reclamados:  {c.reclamados}   (huérfanos de otro consumidor)")
    print(f"    fallados:    {c.fallados}   (siguen pendientes, se reintentan)")
    print(f"    descartados: {c.descartados}   (a '{consumidor.stream_muertos}')")
    print("\n  consumo de inferencia")
    print(inferencia.resumen())
    return 0


if __name__ == "__main__":
    sys.exit(main())
