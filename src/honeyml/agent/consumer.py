"""Frontera de entrada del motor: lee el bus con un grupo de consumidores y entrega los eventos.

Todo lo que viene después (contexto, recuperación, inferencia, validación, persistencia) recibe
eventos de acá y nunca habla con el bus.

El contrato del manejador es una sola regla: si levanta una excepción el evento no se confirma y
vuelve, y si retorna, la decisión es durable y se confirma. Si además devuelve `True`, la decisión
ya existía de antes y el evento se cuenta como repetido. Y si levanta `DetenerConsumo`, el problema
no es el evento sino algo que afecta a todos los que siguen: la corrida se corta y los eventos del
lote quedan pendientes sin cobrarles la entrega. Con ese contrato el grafo se enchufa sin tocar la
lógica de este módulo: quien los une es `motor.py`.

Hay cuatro problemas resueltos a propósito, y los cuatro son silenciosos si no se los atiende.

Los repetidos: el bus entrega al menos una vez por diseño, así que se deduplica por `doc_id`, que es
el mismo identificador del índice, y la marca se escribe después de que el manejador tuvo éxito y
nunca antes. Un fallo no puede marcar trabajo como hecho.

El consumidor caído: lo que queda pendiente más allá de un umbral de inactividad lo toma otro con
`XCLAIM`. Es lo que separa "el motor reinicia" de "el motor no pierde nada".

El evento venenoso: uno que siempre falla se reclamaría para siempre, frenando al grupo y gastando
una llamada de inferencia por vuelta. Pasado un techo de entregas va a un stream de descartados y se
confirma, así la cola avanza y el evento queda inspeccionable.

Y el corte a mitad de decisión: `SIGTERM` y `SIGINT` terminan el lote en curso en lugar de cortar.
No es pérdida, porque lo no confirmado se reclama, pero evita desperdiciar una llamada paga.

Se usa `XPENDING` y no `XAUTOCLAIM` para reclamar, porque solo el primero informa cuántas veces se
entregó cada mensaje, que es lo que distingue un evento lento de uno venenoso.
"""

from __future__ import annotations

import argparse
import os
import re
import signal
import socket
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, cast

import redis

# Los valores por defecto coinciden con infra/redis/docker-compose.yml: el bus escucha solo en
# loopback y no se alcanza desde afuera de la zona de análisis.
HOST = os.getenv("BUS_HOST", "127.0.0.1")
PORT = int(os.getenv("BUS_PORT", "6379"))
STREAM = os.getenv("BUS_STREAM", "honeyml:events")
GROUP = os.getenv("BUS_GROUP", "triaje")

# Un mensaje que falló esta cantidad de entregas se considera venenoso y se aparta.
MAX_ENTREGAS = int(os.getenv("BUS_MAX_ENTREGAS", "3"))
STREAM_MUERTOS = os.getenv("BUS_STREAM_MUERTOS", "honeyml:events:muertos")

# Cuánto tiene que quedarse quieto un mensaje pendiente antes de que otro consumidor lo pueda
# tomar. Sale del presupuesto de tiempo del ciclo de triaje y no de una corazonada:
#
#   una llamada    60 s de timeout × 3 reintentos del cliente + 6 s de espera exponencial = 186 s
#   un ciclo       186 s × 3 intentos correctivos                                         = 558 s
#
# Una ventana más corta que una sola llamada lenta, como 60 s, hace perder el evento a un ciclo que
# se demora: otro consumidor lo reclama mientras el primero sigue trabajando, los dos pagan la
# inferencia, y el contador de entregas sube hasta mandarlo a la cola de muertos sin que haya nada
# roto. `test_la_ventana_de_reclamo_cubre_el_ciclo_completo` fija la relación, así que cambiar el
# timeout o MAX_INTENTOS sin revisar esto rompe una prueba en vez de aparecer en producción.
#
# El costo de que sobre es que un consumidor caído deja su evento quieto diez minutos, que para el
# ritmo al que llegan los eventos es barato.
INACTIVIDAD_MS = int(os.getenv("BUS_INACTIVIDAD_MS", "600000"))

# Marcas de deduplicación. Una clave por documento, así cada una vence por su cuenta en lugar de
# caerse todo el conjunto junto.
#
# Son un ahorro y no la garantía. Cubren los duplicados que deja un reinicio del normalizador, que
# llegan a los minutos, y para eso un día sobra. Pero un duplicado también puede llegar semanas
# después: si Filebeat relee el corpus, el bus recibe otra vez eventos ya decididos y la marca
# venció hace rato. Lo que impide pisar una decisión es que el almacén escribe con `_create`; la
# marca solo evita volver a correr el grafo mientras está viva.
PREFIJO_VISTO = "honeyml:visto:"
TTL_VISTO = int(os.getenv("BUS_TTL_VISTO", "86400"))


# Un mensaje tal como lo entrega Redis con decode_responses activo: el id de entrada y sus campos.
Mensaje = tuple[str, dict[str, str]]

# Prefijos que Cowrie deja en la línea del registro y que no son parte del comando que tipeó el
# atacante. El pipeline los saca antes de indexar, pero el bus puede retener mensajes publicados
# sin ese recorte. Un evento así llega con `CMD: uname -a`, y el motor razona sobre el prefijo como
# si fuera parte de lo ejecutado.
#
# Se sanea acá y no solo en el pipeline porque son dos poblaciones distintas: lo que ya está en el
# bus no se vuelve a publicar. Que el mismo recorte viva en los dos lados es a propósito, y la
# expresión es la misma que la del filtro de Logstash para que no se separen.
PREFIJOS_DEL_REGISTRO = re.compile(r"^(CMD: |Command (not )?found: )")


def _mensajes(respuesta: Any) -> list[Mensaje]:
    """Reduce la respuesta de un stream de Redis a la forma que el protocolo sí garantiza.

    redis-py anota estos comandos con uniones anchas (`bytes | str`, opcionales anidados) porque la
    forma real depende del comando y de si `decode_responses` está activo. Acá el cliente se
    construye con esa opción prendida, así que todo vuelve como `str`, pero eso es un hecho de
    ejecución que el verificador de tipos no puede ver.

    Toda la frontera sin tipar queda concentrada en esta única función a propósito. La alternativa
    es repartir supresiones por cada llamada, que es justamente apagar el verificador en los
    lugares donde un error de verdad se notaría.
    """
    return cast("list[Mensaje]", respuesta or [])


@dataclass
class EventoDelBus:
    """Un mensaje como lo ve el motor.

    `entry_id` es la coordenada en el bus, la que hace falta para confirmar. `doc_id` es la
    identidad del documento en el índice, que es sobre lo que razona el resto del motor y lo que
    usa la deduplicación.
    """

    entry_id: str
    doc_id: str
    timestamp: str = ""
    honeypot: str = ""
    category: str = ""
    action: str = ""
    outcome: str = ""
    protocol: str = ""
    source_ip: str = ""
    session: str = ""
    user: str = ""
    command: str = ""
    entregas: int = 1
    crudo: dict[str, str] = field(default_factory=dict)

    @classmethod
    def desde_mensaje(
        cls, entry_id: str, campos: dict[str, str], entregas: int = 1
    ) -> EventoDelBus:
        # `crudo` conserva el mensaje sin tocar: si mañana hay que revisar qué llegó del bus, el
        # saneamiento no puede haber borrado la prueba.
        return cls(
            entry_id=entry_id,
            doc_id=campos.get("doc_id", ""),
            timestamp=campos.get("timestamp", ""),
            honeypot=campos.get("honeypot", ""),
            category=campos.get("category", ""),
            action=campos.get("action", ""),
            outcome=campos.get("outcome", ""),
            protocol=campos.get("protocol", ""),
            source_ip=campos.get("source_ip", ""),
            session=campos.get("session", ""),
            user=campos.get("user", ""),
            command=PREFIJOS_DEL_REGISTRO.sub("", campos.get("command", "")),
            entregas=entregas,
            crudo=campos,
        )

    def resumen(self) -> str:
        """Una línea para los registros. El evento entero vive en el índice."""
        que = self.command or self.user or self.action
        return f"{self.honeypot}/{self.category} {self.source_ip} {self.protocol} · {que[:60]}"


class DetenerConsumo(Exception):  # noqa: N818 - es una señal de control, no un error
    """Lo levanta el manejador cuando seguir consumiendo haría daño en vez de solo fallar.

    El caso típico es la cuota del proveedor. Una falla común deja el evento pendiente, se
    reclama y a la tercera entrega va a la cola de muertos, que es lo correcto para un evento que
    siempre falla. Con la cuota agotada fallan todos por igual, y tratarlos así mandaría a esa cola
    miles de eventos que no tienen nada malo.
    """


@dataclass
class Contadores:
    procesados: int = 0
    repetidos: int = 0
    fallados: int = 0
    reclamados: int = 0
    descartados: int = 0

    @property
    def atendidos(self) -> int:
        """Eventos sobre los que el ciclo tomó una decisión, haya salido como haya salido.

        `reclamados` queda afuera a propósito: reclamar es levantar un evento, no resolverlo. Todo
        evento reclamado termina cayendo en alguno de los otros cuatro contadores, así que sumarlo
        acá contaría el mismo trabajo dos veces.
        """
        return self.procesados + self.repetidos + self.fallados + self.descartados


class ConsumidorDelBus:
    """Lee el stream como parte de un grupo de consumidores y le pasa los eventos a un manejador.

    El manejador levanta una excepción cuando falla: levantar significa "no resuelto", así que el
    mensaje queda pendiente y alguien lo va a volver a tomar. Retornar significa que la decisión ya
    es durable y el mensaje se puede confirmar. Retornar `True` agrega un matiz, que la decisión ya
    existía de antes, y el evento se cuenta como repetido en lugar de procesado. `DetenerConsumo`
    corta la corrida entera.
    """

    def __init__(
        self,
        manejador: Callable[[EventoDelBus], bool | None],
        *,
        host: str = HOST,
        puerto: int = PORT,
        stream: str = STREAM,
        grupo: str = GROUP,
        nombre: str | None = None,
        lote: int = 10,
        bloqueo_ms: int = 5000,
        max_entregas: int = MAX_ENTREGAS,
        inactividad_ms: int = INACTIVIDAD_MS,
        stream_muertos: str | None = None,
    ) -> None:
        self.manejador = manejador
        self.stream = stream
        self.grupo = grupo
        # Si no lo pasan, se deriva del stream: un stream descartable se lleva su propia cola de
        # muertos y una prueba nunca puede escribir en la de producción.
        self.stream_muertos = stream_muertos or (
            STREAM_MUERTOS if stream == STREAM else f"{stream}:muertos"
        )
        # Identifica a este consumidor dentro del grupo. Equipo y pid, así dos instancias en la
        # misma máquina no chocan y una colgada se puede rastrear hasta un proceso.
        self.nombre = nombre or f"{socket.gethostname()}-{os.getpid()}"
        self.lote = lote
        self.bloqueo_ms = bloqueo_ms
        self.max_entregas = max_entregas
        self.inactividad_ms = inactividad_ms
        self.contadores = Contadores()
        self._parar = False
        # Por qué se cortó la corrida, cuando la cortó el manejador. Vacío si terminó normalmente.
        self.motivo_de_parada = ""

        self.r = redis.Redis(
            host=host, port=puerto, decode_responses=True, socket_timeout=bloqueo_ms / 1000 + 10
        )

    # ---------------------------------------------------------------- ciclo de vida

    def asegurar_grupo(self, desde_ahora: bool = False) -> None:
        """Crea el grupo si no está. Es idempotente, así que se puede llamar en cada arranque.

        `desde_ahora` decide qué ve un grupo recién creado: solo lo que llegue de ahora en más, o
        todo lo acumulado. Por defecto, lo acumulado, porque en este sistema esos eventos viejos
        son justamente los que están esperando el triaje.
        """
        inicio = "$" if desde_ahora else "0"
        try:
            self.r.xgroup_create(self.stream, self.grupo, id=inicio, mkstream=True)
            print(f"  grupo '{self.grupo}' creado desde {'ahora' if desde_ahora else 'el inicio'}")
        except redis.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise
            print(f"  grupo '{self.grupo}' ya existía")

    def escuchar_senales(self) -> None:
        """SIGTERM/SIGINT cortan el ciclo al terminar el lote, no en medio de una decisión.

        Un corte abrupto no pierde datos, porque lo no confirmado se reclama, pero sí desperdicia
        una llamada de inferencia, y esas cuestan plata.
        """

        def parar(signum: int, _frame: Any) -> None:
            nombre = signal.Signals(signum).name
            print(f"\n  {nombre} recibido: se termina el lote en curso y se corta.")
            self._parar = True

        signal.signal(signal.SIGINT, parar)
        signal.signal(signal.SIGTERM, parar)

    # ---------------------------------------------------------------- procesamiento

    def _ya_procesado(self, doc_id: str) -> bool:
        return bool(doc_id) and bool(self.r.exists(PREFIJO_VISTO + doc_id))

    def _marcar_procesado(self, doc_id: str) -> None:
        if doc_id:
            self.r.set(PREFIJO_VISTO + doc_id, "1", ex=TTL_VISTO)

    def _a_muertos(self, evento: EventoDelBus, motivo: str) -> None:
        """Aparta un mensaje que no se puede procesar y lo resuelve, para que el grupo avance."""
        # dict[Any, Any] y no dict[str, str] por la invarianza de los diccionarios: xadd declara
        # claves y valores como una unión ancha, y un dict[str, str] no es subtipo de eso aunque
        # cada valor sí lo sea. No hay incompatibilidad real, solo una regla del sistema de tipos.
        carga: dict[Any, Any] = dict(evento.crudo)
        carga["_motivo"] = motivo
        carga["_entregas"] = str(evento.entregas)
        carga["_consumidor"] = self.nombre
        self.r.xadd(self.stream_muertos, carga, maxlen=10000, approximate=True)
        self.r.xack(self.stream, self.grupo, evento.entry_id)
        self.contadores.descartados += 1
        print(f"  ✗ descartado tras {evento.entregas} entregas: {evento.resumen()}")

    def procesar(self, evento: EventoDelBus) -> None:
        """Pasa un evento por el manejador y lo resuelve según cómo haya salido."""
        # Sin identificador no hay nada que hacer con este evento, y conviene cortarlo acá antes de
        # gastar una llamada paga. No se puede deduplicar, porque la marca se guarda por `doc_id`, y
        # no se puede persistir la decisión, porque el documento se indexa bajo ese mismo valor.
        #
        # El pipeline lo arma con `.to_s` sobre la metadata, así que si la huella no se calculó
        # llega la cadena vacía en lugar de faltar el campo. Es un defecto nuestro, aguas arriba, y
        # la cola de muertos es donde queda visible en vez de dar vueltas.
        if not evento.doc_id:
            self._a_muertos(evento, motivo="sin doc_id: no se puede deduplicar ni persistir")
            return

        if self._ya_procesado(evento.doc_id):
            # Ya se decidió en una entrega anterior. Confirmarlo es lo correcto: el trabajo está
            # hecho, y dejarlo pendiente haría que vuelva para siempre.
            self.r.xack(self.stream, self.grupo, evento.entry_id)
            self.contadores.repetidos += 1
            return

        try:
            ya_estaba = self.manejador(evento)
        except DetenerConsumo:
            # No es una falla del evento: la resuelve `correr`, que sabe qué quedó del lote.
            raise
        except Exception as exc:  # noqa: BLE001 - que falle el manejador no puede cortar el ciclo
            self.contadores.fallados += 1
            print(f"  ! falló ({type(exc).__name__}: {exc}): {evento.resumen()}")
            # A propósito no se confirma: queda pendiente y después se reclama.
            return

        # El orden importa: primero marcar, después confirmar. Si el proceso muere en el medio, el
        # evento vuelve y se saltea por estar ya procesado. Al revés se podría dar por resuelto un
        # evento cuya finalización nunca quedó anotada.
        self._marcar_procesado(evento.doc_id)
        self.r.xack(self.stream, self.grupo, evento.entry_id)

        # `True` es la forma que tiene el manejador de decir que la decisión ya existía de antes. Se
        # confirma igual, porque el trabajo está hecho, pero se cuenta como repetido: sumarlo a
        # procesados haría pasar una relectura del corpus por una tanda de triaje.
        if ya_estaba is True:
            self.contadores.repetidos += 1
        else:
            self.contadores.procesados += 1

    # ---------------------------------------------------------------- lectura

    def reclamar_huerfanos(self) -> list[EventoDelBus]:
        """Toma los mensajes que dejó pendientes un consumidor que ya no responde.

        Usa XPENDING y no XAUTOCLAIM porque solo el primero informa la cantidad de entregas, que es
        lo que distingue un evento lento de uno venenoso.
        """
        pendientes: Any = self.r.xpending_range(
            self.stream, self.grupo, min="-", max="+", count=self.lote, idle=self.inactividad_ms
        )
        if not pendientes:
            return []

        rescatados: list[EventoDelBus] = []
        for p in pendientes:
            entry_id = str(p["message_id"])
            entregas = int(p["times_delivered"])

            if entregas > self.max_entregas:
                crudo = _mensajes(self.r.xrange(self.stream, min=entry_id, max=entry_id))
                campos = crudo[0][1] if crudo else {}
                self._a_muertos(
                    EventoDelBus.desde_mensaje(entry_id, campos, entregas),
                    motivo=f"supero {self.max_entregas} entregas sin resolverse",
                )
                continue

            tomados = _mensajes(
                self.r.xclaim(
                    self.stream,
                    self.grupo,
                    self.nombre,
                    min_idle_time=self.inactividad_ms,
                    message_ids=[entry_id],
                )
            )
            for eid, campos in tomados:
                rescatados.append(EventoDelBus.desde_mensaje(eid, campos, entregas + 1))

        if rescatados:
            self.contadores.reclamados += len(rescatados)
            print(f"  ↻ {len(rescatados)} evento(s) huérfano(s) reclamado(s)")
        return rescatados

    def leer_nuevos(self) -> list[EventoDelBus]:
        """Lee mensajes nunca entregados al grupo. Bloquea para que el ciclo no gire en falso."""
        respuesta: Any = self.r.xreadgroup(
            self.grupo, self.nombre, {self.stream: ">"}, count=self.lote, block=self.bloqueo_ms
        )
        if not respuesta:
            return []
        # Una entrada por stream leído; siempre se pide uno solo, así que la primera es esa.
        _, crudo = respuesta[0]
        return [EventoDelBus.desde_mensaje(eid, campos) for eid, campos in _mensajes(crudo)]

    def correr(self, limite: int | None = None, desde_ahora: bool = False) -> Contadores:
        """Ciclo principal. Con `limite` atiende esa cantidad y vuelve; si no, se queda escuchando.

        `limite` acota los intentos, no los éxitos. Contar solo los éxitos haría que una corrida
        acotada con un manejador que falla gire para siempre: el evento fallado vuelve a pendiente,
        se reclama, falla de nuevo, y el contador no se mueve nunca. Una corrida a la que se le
        pidieron veinte eventos tiene que terminar a los veinte, hayan salido como hayan salido.
        """
        self.asegurar_grupo(desde_ahora=desde_ahora)
        self.escuchar_senales()
        print(f"  consumidor '{self.nombre}' escuchando '{self.stream}'\n")

        ultimo_reclamo = 0.0
        vacios = 0
        while not self._parar:
            # El reclamo se revisa con menos frecuencia que la lectura: es un camino de
            # recuperación y no el normal, y un XPENDING por iteración sería puro costo.
            ahora = time.monotonic()
            eventos: list[EventoDelBus] = []
            if ahora - ultimo_reclamo >= self.inactividad_ms / 1000:
                eventos = self.reclamar_huerfanos()
                ultimo_reclamo = ahora
                if limite is not None and self.contadores.atendidos >= limite:
                    break

            if not eventos:
                eventos = self.leer_nuevos()

            if not eventos:
                vacios += 1
                # En modo acotado, una lectura vacía significa que ya no queda atraso y no hay
                # nada que esperar. En modo seguimiento se sigue bloqueando, que es la gracia.
                if limite is not None and vacios >= 2:
                    break
                continue

            vacios = 0
            for i, evento in enumerate(eventos):
                try:
                    self.procesar(evento)
                except DetenerConsumo as exc:
                    self.motivo_de_parada = str(exc)
                    self._devolver_sin_cobrar(eventos[i:])
                    self._parar = True
                    break
                if limite is not None and self.contadores.atendidos >= limite:
                    self._parar = True
                    break

        return self.contadores

    def _devolver_sin_cobrar(self, eventos: list[EventoDelBus]) -> None:
        """Deja pendientes los eventos que no se atendieron, con la entrega que tenían antes.

        Leerlos ya les sumó una entrega. Sin descontarla, un corte por cuota que se repitiera tres
        veces mandaría esos mismos eventos a la cola de muertos sin que tengan nada malo.
        `RETRYCOUNT` fija el contador a mano, y es la única forma que da Redis de descontarla.
        """
        for evento in eventos:
            self.r.xclaim(
                self.stream,
                self.grupo,
                self.nombre,
                min_idle_time=0,
                message_ids=[evento.entry_id],
                retrycount=max(evento.entregas - 1, 0),
                justid=True,
            )


def manejador_de_registro(evento: EventoDelBus) -> None:
    """Manejador de inspección: imprime el evento y lo da por resuelto, sin clasificarlo.

    El que tría es el de `motor.py`, que corre el grafo. Este queda porque sigue siendo útil: mira
    qué está llegando al bus sin gastar una sola llamada paga, que es justo lo que uno quiere cuando
    está revisando el pipeline y no el motor. Sirve también para probar el ciclo de confirmación
    sin el grafo de por medio.
    """
    print(f"  · {evento.resumen()}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Consumidor del bus de eventos con grupo.")
    ap.add_argument("--host", default=HOST)
    ap.add_argument("--puerto", type=int, default=PORT)
    ap.add_argument("--stream", default=STREAM)
    ap.add_argument("--grupo", default=GROUP)
    ap.add_argument("--nombre", default=None, help="nombre del consumidor dentro del grupo")
    ap.add_argument("--lote", type=int, default=10)
    ap.add_argument("--limite", type=int, default=None, help="procesar N eventos y salir")
    ap.add_argument(
        "--desde-ahora",
        action="store_true",
        help="si el grupo es nuevo, ignorar lo acumulado y tomar solo lo que llegue",
    )
    args = ap.parse_args()

    consumidor = ConsumidorDelBus(
        manejador_de_registro,
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

    c = consumidor.correr(limite=args.limite, desde_ahora=args.desde_ahora)

    print("\n  resumen")
    print(f"    procesados:  {c.procesados}")
    print(f"    repetidos:   {c.repetidos}   (mismo doc_id ya resuelto)")
    print(f"    reclamados:  {c.reclamados}   (huérfanos de otro consumidor)")
    print(f"    fallados:    {c.fallados}   (siguen pendientes, se reintentan)")
    print(f"    descartados: {c.descartados}   (a '{consumidor.stream_muertos}')")
    return 0


if __name__ == "__main__":
    sys.exit(main())
