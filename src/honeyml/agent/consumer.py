"""Event bus consumption (Redis Streams) with a consumer group.

This is the engine's ingestion boundary. Everything downstream — context building, retrieval,
inference, validation, persistence — receives events from here and never talks to the bus itself.

Why a consumer group and not a plain read:

- **Explicit acknowledgement.** An event is only settled once the handler finished. A consumer that
  dies mid-decision leaves it pending, not lost.
- **Reclaiming orphans.** Whatever stays pending past an idle threshold is taken over by another
  consumer. This is what makes the engine survivable rather than merely restartable.
- **Horizontal split.** Several consumers in the same group divide the stream without coordination,
  which is the growth path if one instance stops keeping up.

Delivery is *at least once*, by design and not by accident: on the bus side, a Logstash restart
replays whatever was between checkpoints. Measured on the real corpus: 52.165 messages carried
52.156 distinct document ids. So the consumer deduplicates by `doc_id` — the same identifier
Elasticsearch uses — and skipping is decided *before* the handler runs but recorded *after* it
succeeds, so a failure never marks work as done.

Two failure modes are handled explicitly because both are silent otherwise:

- **Poison message.** An event that always fails would be reclaimed forever, blocking the group's
  progress and burning inference budget on every round. After a delivery ceiling it is moved to a
  dead-letter stream and acknowledged, so the queue advances and the event stays inspectable.
- **Handler failure.** Not acknowledged, so it stays pending for a later reclaim. The event is never
  dropped just because one attempt failed.

Usage:
    python -m honeyml.agent.consumer --limite 20        # take 20 events and exit
    python -m honeyml.agent.consumer                     # follow the stream until interrupted
"""

from __future__ import annotations

import argparse
import os
import signal
import socket
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, cast

import redis

# Defaults match infra/redis/docker-compose.yml: the bus is bound to loopback and never reachable
# from outside the analysis zone (RNF-03).
HOST = os.getenv("BUS_HOST", "127.0.0.1")
PORT = int(os.getenv("BUS_PORT", "6379"))
STREAM = os.getenv("BUS_STREAM", "honeyml:events")
GROUP = os.getenv("BUS_GROUP", "triaje")

# A message that failed this many deliveries is treated as poison and set aside.
MAX_ENTREGAS = int(os.getenv("BUS_MAX_ENTREGAS", "3"))
STREAM_MUERTOS = os.getenv("BUS_STREAM_MUERTOS", "honeyml:events:muertos")

# How long a pending message must sit untouched before another consumer may take it over. Long
# enough that a slow decision isn't stolen mid-flight, short enough that a crash isn't parked
# for an hour.
INACTIVIDAD_MS = int(os.getenv("BUS_INACTIVIDAD_MS", "60000"))

# Dedup marks. One key per document, so each expires on its own schedule instead of the whole set
# dropping at once. A day covers the replay window by a wide margin — duplicates arrive within
# minutes of a restart, never a day later.
PREFIJO_VISTO = "honeyml:visto:"
TTL_VISTO = int(os.getenv("BUS_TTL_VISTO", "86400"))


# One message as Redis hands it over with decode_responses on: the entry id and its flat field map.
Mensaje = tuple[str, dict[str, str]]


def _mensajes(respuesta: Any) -> list[Mensaje]:
    """Narrow a Redis stream response to the shape the protocol actually guarantees.

    redis-py annotates these commands with wide unions (`bytes | str`, nested optionals) because
    the real shape depends on the command and on whether `decode_responses` is on. The client here
    is built with it on, so every value comes back as `str` — but that is a runtime fact the type
    checker cannot see.

    The whole untyped boundary is concentrated in this one function on purpose. The alternative is
    scattering suppressions over every call site, which silences the checker in the places where a
    genuine mistake would show up.
    """
    return cast("list[Mensaje]", respuesta or [])


@dataclass
class EventoDelBus:
    """One message as the engine sees it.

    `entry_id` is the bus coordinate, needed to acknowledge. `doc_id` is the document identity in
    the index, which is what the rest of the engine reasons about and what deduplication uses.
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
            command=campos.get("command", ""),
            entregas=entregas,
            crudo=campos,
        )

    def resumen(self) -> str:
        """One line, for logs. Deliberately short: the full event lives in the index."""
        que = self.command or self.user or self.action
        return f"{self.honeypot}/{self.category} {self.source_ip} {self.protocol} · {que[:60]}"


@dataclass
class Contadores:
    procesados: int = 0
    repetidos: int = 0
    fallados: int = 0
    reclamados: int = 0
    descartados: int = 0

    @property
    def atendidos(self) -> int:
        """Events the loop actually took a decision about, whichever way it went.

        `reclamados` is excluded on purpose: reclaiming is picking an event up, not resolving it.
        Every reclaimed event lands in one of the other four counters afterwards, so adding it here
        would count the same work twice.
        """
        return self.procesados + self.repetidos + self.fallados + self.descartados


class ConsumidorDelBus:
    """Reads the stream as part of a consumer group and hands events to a handler.

    The handler raises on failure. That is the whole contract: raising means "not settled", so the
    message stays pending and someone will take it again. Returning means the decision is durable
    and the message can be acknowledged.
    """

    def __init__(
        self,
        manejador: Callable[[EventoDelBus], None],
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
        # Derived from the stream when not given, so a throwaway stream gets a throwaway
        # dead-letter and a test can never write into the production one.
        self.stream_muertos = stream_muertos or (
            STREAM_MUERTOS if stream == STREAM else f"{stream}:muertos"
        )
        # Identifies this consumer inside the group. Host and pid so that two instances on the same
        # machine don't collide and a stuck one can be traced back to a process.
        self.nombre = nombre or f"{socket.gethostname()}-{os.getpid()}"
        self.lote = lote
        self.bloqueo_ms = bloqueo_ms
        self.max_entregas = max_entregas
        self.inactividad_ms = inactividad_ms
        self.contadores = Contadores()
        self._parar = False

        self.r = redis.Redis(
            host=host, port=puerto, decode_responses=True, socket_timeout=bloqueo_ms / 1000 + 10
        )

    # ---------------------------------------------------------------- ciclo de vida

    def asegurar_grupo(self, desde_ahora: bool = False) -> None:
        """Create the group if missing. Idempotent, so it is safe on every start.

        `desde_ahora` decides what a brand-new group sees: only what arrives from now on, or the
        whole backlog. The default is the backlog, because on this system the accumulated events
        are precisely the ones waiting to be triaged.
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
        """SIGTERM/SIGINT stop the loop after the current batch instead of cutting mid-decision.

        An abrupt stop is not a data loss here — unacknowledged events are reclaimed — but it does
        waste an inference call, and those cost money.
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
        """Set aside a message that cannot be processed, and settle it so the group advances."""
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
        """Run one event through the handler and settle it according to the outcome."""
        if self._ya_procesado(evento.doc_id):
            # Already decided in a previous delivery. Acknowledging is the right move: the work is
            # done, and leaving it pending would make it come back forever.
            self.r.xack(self.stream, self.grupo, evento.entry_id)
            self.contadores.repetidos += 1
            return

        try:
            self.manejador(evento)
        except Exception as exc:  # noqa: BLE001 - the handler's failure must not stop the loop
            self.contadores.fallados += 1
            print(f"  ! falló ({type(exc).__name__}: {exc}): {evento.resumen()}")
            # Deliberately not acknowledged: it stays pending and will be reclaimed.
            return

        # Order matters: mark first, acknowledge second. If the process dies in between, the event
        # comes back and is skipped as already processed. The reverse order could settle an event
        # whose completion was never recorded.
        self._marcar_procesado(evento.doc_id)
        self.r.xack(self.stream, self.grupo, evento.entry_id)
        self.contadores.procesados += 1

    # ---------------------------------------------------------------- lectura

    def reclamar_huerfanos(self) -> list[EventoDelBus]:
        """Take over messages left pending by a consumer that is no longer answering.

        Uses XPENDING and not XAUTOCLAIM because only the former reports the delivery count, which
        is what tells a slow event apart from a poisonous one.
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
        """Read messages never delivered to this group. Blocks so the loop doesn't spin."""
        respuesta: Any = self.r.xreadgroup(
            self.grupo, self.nombre, {self.stream: ">"}, count=self.lote, block=self.bloqueo_ms
        )
        if not respuesta:
            return []
        # One entry per stream read; only one is ever requested, so the first is the one.
        _, crudo = respuesta[0]
        return [EventoDelBus.desde_mensaje(eid, campos) for eid, campos in _mensajes(crudo)]

    def correr(self, limite: int | None = None, desde_ahora: bool = False) -> Contadores:
        """Main loop. With `limite` it attends to that many and returns; otherwise it follows.

        `limite` bounds *attempts*, not successes. Counting only successes would make a bounded run
        with a failing handler spin: the failed event goes back to pending, gets reclaimed, fails
        again, and the counter never moves. A run asked for twenty events has to end after twenty
        events regardless of how they turned out.
        """
        self.asegurar_grupo(desde_ahora=desde_ahora)
        self.escuchar_senales()
        print(f"  consumidor '{self.nombre}' escuchando '{self.stream}'\n")

        ultimo_reclamo = 0.0
        vacios = 0
        while not self._parar:
            # Reclaiming is checked on a slower cadence than reading: it is a recovery path, not the
            # normal one, and XPENDING on every iteration would be pure overhead.
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
                # In bounded mode an empty read means the backlog is drained; there is nothing to
                # wait for. Following mode keeps blocking, which is the point.
                if limite is not None and vacios >= 2:
                    break
                continue

            vacios = 0
            for evento in eventos:
                self.procesar(evento)
                if limite is not None and self.contadores.atendidos >= limite:
                    self._parar = True
                    break

        return self.contadores


def manejador_de_registro(evento: EventoDelBus) -> None:
    """Default handler: prints the event and settles it.

    A placeholder with a purpose — it exercises the whole acknowledgement cycle without an
    inference provider, so the consumer can be verified on its own. Rows 81-86 replace it with the
    graph, and nothing else in this module changes.
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
