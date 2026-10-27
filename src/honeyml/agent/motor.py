"""Une el bus con el grafo: lo que convierte los nodos sueltos en un motor que corre.

`make consumer` lee el bus con `manejador_de_registro`, que imprime el evento y lo confirma sin
triarlo. Este módulo es la pieza que conecta el bus con el grafo, y la única que conoce a los dos
lados.

Vive aparte, y no dentro del consumidor ni del grafo, porque la dependencia tiene que ir en un solo
sentido. El grafo importa los nodos, los nodos importan el consumidor para tipar el evento; si el
consumidor importara el grafo, el círculo se cierra. Acá arriba de los dos no hay ciclo.

Los adaptadores se crean una sola vez y se inyectan en los nodos. Creados por evento, el desglose
de consumo por modelo arrancaría de cero cada vez y "cuántos eventos resolvió el modelo económico"
respondería siempre uno, además de releer la configuración del disco en cada llamada.

El contrato con el consumidor es corto. Si el ciclo levanta, sea porque el índice no responde,
porque no se alcanzó al proveedor o porque el almacén rechazó la decisión, la excepción sale, el
evento no se confirma y otro consumidor lo reclama. Si retorna, la decisión ya está guardada. Lo
único que se traduce es la cuota del proveedor: sale como `DetenerConsumo`, porque afecta a todos
los eventos que siguen y no solo al que la encontró. En modo continuo ese corte no termina el
proceso: el motor deja una marca en el bus para que el panel avise, y queda en pausa reintentando.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Callable
from typing import Any, cast

import redis

from . import consumer as bus
from . import firma as firma_de_conducta
from .adapters.almacen import Almacen, AlmacenConsultable, AlmacenElastic
from .adapters.config import MODELO_POR_DEFECTO, CredencialAusenteError
from .adapters.inferencia import PRECIOS, CuotaAgotadaError
from .adapters.repertorio import PREFIJO, Repertorio, RepertorioEnElBus
from .adapters.saldo import MarcaSinSaldo
from .adapters.servicio import AdaptadorDeInferencia, ServicioDeInferencia
from .graph import INFERENCIA, MEMORIA, PERSISTENCIA, construir_grafo, ejecutar
from .nodes import inferencia as nodo_inferencia
from .nodes import memoria as nodo_memoria
from .nodes import persistencia as nodo_persistencia
from .state import SUFIJO_DE_FALLA, EstadoTriaje, estado_inicial, resultado_del_ciclo

# Tamaño de atraso a partir del cual el motor se niega a arrancar sin que se lo pidan explícito.
#
# Dos mil eventos son unos dos días y medio de tráfico, así que ponerse al día tras un fin de semana
# no molesta. Por encima de eso ya es reprocesamiento histórico, y ahí conviene que lo diga quien
# corre el comando: decenas de miles de mensajes, a una llamada por evento, son decenas de dólares.
# Un `make triaje` sin argumentos no puede gastar eso por accidente.
TOPE_SIN_CONFIRMAR = 2000

# Tokens de una llamada típica. Sirven para estimar el gasto antes de arrancar, no para
# contabilizarlo: lo real lo lleva el adaptador y queda guardado en cada decisión.
#
# Salen de corridas contra datos reales, porque una estimación que se queda corta es el peor error
# para una guardia pensada justamente para avisar antes de gastar.
TOKENS_TIPICOS = (2545, 980)

# Cada cuánto reintenta el motor cuando el proveedor se quedó sin saldo. Cinco minutos alcanzan para
# retomar enseguida cuando se carga crédito, y son pocos pedidos rechazados por hora. Mientras tanto
# no se lee el bus: lo que llega espera ahí, sin perderse.
PAUSA_SIN_SALDO_S = 300


def compilar(
    servicio: ServicioDeInferencia | None = None,
    almacen: Almacen | None = None,
    repertorio: Repertorio | None = None,
) -> Any:
    """Arma el grafo con los adaptadores ya inyectados, una sola vez por corrida.

    Los tres nodos que hablan con el mundo reciben su dependencia acá. El resto de la topología
    queda tal como la define `construir_grafo`, así que esto no puede cambiar el orden de los nodos
    ni las condiciones de las aristas por accidente.

    El repertorio se pasa explícito y no se construye por omisión, al revés que los otros dos. Sin
    él el motor razona cada evento, que es el comportamiento correcto y el más caro: que reutilizar
    haya que pedirlo es lo que evita que una corrida de prueba empiece a copiar decisiones sin que
    quien la lanzó lo haya decidido.
    """
    inferencia = servicio or AdaptadorDeInferencia()
    destino = almacen or AlmacenElastic()
    return construir_grafo(
        {
            MEMORIA: lambda estado: nodo_memoria.recordar(estado, repertorio=repertorio),
            INFERENCIA: lambda estado: nodo_inferencia.consultar(estado, servicio=inferencia),
            PERSISTENCIA: lambda estado: nodo_persistencia.guardar(
                estado, almacen=destino, repertorio=repertorio
            ),
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


def firmas_nuevas(consumidor: bus.ConsumidorDelBus) -> int:
    """Cuántas conductas del atraso todavía no tienen decisión en el repertorio.

    Con la reutilización encendida es lo que de verdad se paga: el atraso puede tener cien mil
    mensajes, pero una conducta ya resuelta se copia sin llamar al proveedor. Estimar por mensajes
    multiplicaría el gasto por las repeticiones de cada conducta, que llegan a miles.
    """
    desde = "-"
    try:
        for grupo in consumidor.r.xinfo_groups(consumidor.stream):
            if grupo.get("name") == consumidor.grupo and grupo.get("last-delivered-id"):
                desde = f"({grupo['last-delivered-id']}"
    except redis.ResponseError:
        return 0
    crudo = consumidor.r.xrange(consumidor.stream, min=desde)
    firmas = {
        firma_de_conducta.de_evento(bus.EventoDelBus.desde_mensaje(eid, campos))
        for eid, campos in cast("list[bus.Mensaje]", crudo or [])
    }
    return sum(1 for f in firmas if not consumidor.r.exists(PREFIJO + f))


def _linea(evento: bus.EventoDelBus, final: EstadoTriaje) -> str:
    """Una línea por evento, para seguir la corrida desde la consola."""
    if final.get("ya_existia"):
        return f"  ~ ya estaba decidido, no se reescribió: {evento.resumen()}"

    decision = final.get("decision")
    if decision is None:
        return f"  ? {resultado_del_ciclo(final)}: {evento.resumen()}"

    intentos = int(final.get("intentos", 0))
    corregido = f" tras {intentos} intentos" if intentos > 1 else ""
    # Una marca distinta para lo copiado: en una corrida larga lo que importa ver de un vistazo es
    # cuántas decisiones se pagaron y cuántas salieron del repertorio.
    marca = "=" if final.get("reutilizada_de") else "+"
    # Sin táctica va el motivo entre paréntesis, que entra en la misma columna.
    tactica = decision.tactica_mitre or f"({decision.motivo_sin_tactica or 'sin táctica'})"
    linea = f"  {marca} {decision.severidad.value:<10} {tactica:<22}{corregido} {evento.resumen()}"

    # El documento guarda qué consulta falló y no por qué. El porqué es para quien depura, y este
    # registro es el único lugar donde queda.
    fallidas = nodo_persistencia.consultas_fallidas(final)
    if not fallidas:
        return linea
    hallazgos = final["contexto"].hallazgos
    detalle = [
        f"      {nombre} falló: {hallazgos[nombre + SUFIJO_DE_FALLA]}" for nombre in fallidas
    ]
    return "\n".join([f"{linea}\n    ! a revisión, decidida sin {', '.join(fallidas)}", *detalle])


def manejador(
    servicio: ServicioDeInferencia | None = None,
    almacen: AlmacenConsultable | None = None,
    repertorio: Repertorio | None = None,
    *,
    saltear_decididos: bool = True,
    marca: MarcaSinSaldo | None = None,
) -> Callable[[bus.EventoDelBus], bool]:
    """El manejador que reemplaza a `manejador_de_registro`: corre un evento por el grafo.

    Devuelve una función y no una clase porque el consumidor solo pide eso. El grafo compilado queda
    capturado en la clausura, así se arma una vez y no por evento.

    Antes del grafo se pregunta si el evento ya tiene decisión. Reingerir el corpus desde los
    registros crudos, o una relectura de Filebeat, trae de vuelta eventos decididos hace semanas:
    sin la pregunta, cada uno recorre el grafo entero y el que no acierta el repertorio paga una
    llamada que después choca contra la decisión guardada. Con `saltear_decididos` en falso se
    vuelve a decidir, que es lo que pide una corrida que reescribe a propósito.

    Con `marca`, la cuota agotada queda anotada en el bus para el panel, y la anotación se saca en
    cuanto el proveedor vuelve a contestar.
    """
    destino = almacen or AlmacenElastic()
    compilado = compilar(servicio=servicio, almacen=destino, repertorio=repertorio)

    # Arranca como puesta porque al levantar no se sabe si quedó una marca de una corrida anterior:
    # la primera respuesta del proveedor la saca, y después solo se vuelve a sacar si se volvió a
    # poner. Así no se escribe en el bus por cada evento.
    marca_puesta = marca is not None

    def triar(evento: bus.EventoDelBus) -> bool:
        nonlocal marca_puesta
        if saltear_decididos and destino.existe(evento.doc_id):
            print(f"  ~ ya estaba decidido: {evento.resumen()}")
            return True
        try:
            final = ejecutar(compilado, estado_inicial(evento))
        except CuotaAgotadaError as exc:
            # El problema no es el evento sino el proveedor, y va a afectar igual a todos los que
            # siguen. Tomado como una falla común, cada evento fallaría, se reclamaría y a la
            # tercera entrega terminaría en la cola de muertos.
            if marca is not None:
                marca.poner(str(exc))
                marca_puesta = True
            raise bus.DetenerConsumo(str(exc)) from exc
        # `intentos` solo sube cuando el proveedor contestó. Una copia del repertorio o un evento
        # cortado antes de razonar no prueban que haya saldo, así que no sacan la marca.
        if marca is not None and marca_puesta and int(final.get("intentos") or 0) > 0:
            marca.quitar()
            marca_puesta = False
        print(_linea(evento, final))
        # Le avisa al consumidor si la decisión ya existía, para que lo cuente como repetido.
        return bool(final.get("ya_existia"))

    return triar


def esperar(consumidor: bus.ConsumidorDelBus, segundos: int) -> bool:
    """Espera de a un segundo y devuelve falso si en el medio llegó una señal.

    De a uno para que un `docker stop` durante la pausa corte en el acto y no espere los minutos
    que falten: Docker manda SIGKILL a los diez segundos.
    """
    for _ in range(segundos):
        if consumidor.parado:
            return False
        time.sleep(1)
    return not consumidor.parado


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
    ap.add_argument(
        "--reutilizar",
        action="store_true",
        help="copiar la decisión cuando otra conducta idéntica ya se resolvió",
    )
    ap.add_argument(
        "--reescribir",
        action="store_true",
        help="volver a decidir eventos ya decididos, pisando lo guardado",
    )
    args = ap.parse_args()

    if args.reescribir and args.reutilizar:
        # Reescribir es decidir de nuevo, casi siempre porque cambió la escala o el pedido, y el
        # repertorio guarda justamente las decisiones tomadas con las reglas anteriores. Juntas, la
        # corrida pisaría el índice con copias de lo que se quería rehacer.
        print(
            "  --reescribir y --reutilizar no se combinan: se copiarían las decisiones que se "
            "quieren rehacer.\n"
            "  Para rehacer con reutilización, primero hay que vaciar las claves "
            "honeyml:firma:* del bus."
        )
        return 1

    # El adaptador se crea acá y no dentro del manejador para poder pedirle el resumen al final.
    try:
        inferencia = AdaptadorDeInferencia()
    except CredencialAusenteError as exc:
        print(f"  No se puede arrancar: {exc}")
        return 1

    repertorio = RepertorioEnElBus() if args.reutilizar else None
    almacen = AlmacenElastic(reescribir=args.reescribir)

    consumidor = bus.ConsumidorDelBus(
        manejador(
            servicio=inferencia,
            almacen=almacen,
            repertorio=repertorio,
            saltear_decididos=not args.reescribir,
            marca=MarcaSinSaldo(),
        ),
        host=args.host,
        puerto=args.puerto,
        stream=args.stream,
        grupo=args.grupo,
        nombre=args.nombre,
        # Con `--limite 5` y un lote de diez, el consumidor leería diez y confirmaría cinco: los
        # otros cinco quedarían entregados sin confirmar hasta que venza la ventana de reclamo, y
        # la corrida siguiente los vería como huérfanos.
        lote=min(args.lote, args.limite) if args.limite else args.lote,
    )

    try:
        consumidor.r.ping()
    except redis.RedisError as exc:
        print(f"  El bus no responde en {args.host}:{args.puerto} ({exc}).")
        print("  Levantalo con: make bus-up")
        return 1

    falta = atraso(consumidor)
    print(f"  atraso del grupo '{args.grupo}': {falta:,} evento(s)".replace(",", "."))
    if falta and repertorio is not None:
        nuevas = firmas_nuevas(consumidor)
        print(f"  conductas sin decisión en el atraso: {nuevas:,}".replace(",", "."))
        print(f"  gasto estimado reutilizando: USD {costo_estimado(nuevas):.2f}")
    elif falta:
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
    # En modo continuo una cuota agotada no termina el proceso. Si saliera, el contenedor lo
    # volvería a levantar, chocaría otra vez y quedaría en un bucle de reinicios que no avisa nada.
    # En cambio queda en pausa con la marca puesta y reintenta. Una corrida acotada sí termina.
    while args.limite is None and consumidor.motivo_de_parada and not consumidor.senal:
        print(f"\n  Sin saldo de inferencia: {consumidor.motivo_de_parada}")
        print(f"  En pausa, se reintenta en {PAUSA_SIN_SALDO_S // 60} minutos.")
        consumidor.reanudar()
        if not esperar(consumidor, PAUSA_SIN_SALDO_S):
            break
        c = consumidor.correr(limite=None, desde_ahora=args.desde_ahora)

    if consumidor.motivo_de_parada:
        print(f"\n  La corrida se detuvo: {consumidor.motivo_de_parada}")
        print("  Los eventos del lote en curso quedaron pendientes sin sumar entregas y se retoman")
        print("  en la próxima corrida.")

    print("\n  resumen del bus")
    print(f"    procesados:  {c.procesados}")
    print(f"    repetidos:   {c.repetidos}   (mismo doc_id ya resuelto)")
    print(f"    reclamados:  {c.reclamados}   (huérfanos de otro consumidor)")
    print(f"    fallados:    {c.fallados}   (siguen pendientes, se reintentan)")
    print(f"    descartados: {c.descartados}   (a '{consumidor.stream_muertos}')")
    print("\n  consumo de inferencia")
    print(inferencia.resumen())
    if repertorio is not None:
        print(repertorio.resumen())
    return 2 if consumidor.motivo_de_parada else 0


if __name__ == "__main__":
    sys.exit(main())
