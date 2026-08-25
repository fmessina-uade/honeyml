"""Bus consumer behaviour against a real Redis.

These check the properties that make the engine survivable, which are exactly the ones that cannot
be verified by reading the code: that an acknowledgement only happens after the handler succeeded,
that a failure leaves the event recoverable, that another consumer can take over what a dead one
left behind, and that an event which always fails stops blocking the group instead of looping.

They run against a throwaway stream and group, never the production ones, and clean up after
themselves.

    make test-integration        (needs the bus up: make bus-up)
"""

from __future__ import annotations

import uuid

import pytest

redis = pytest.importorskip("redis", reason="requiere el extra [agent]")

from honeyml.agent.consumer import PREFIJO_VISTO, ConsumidorDelBus, EventoDelBus  # noqa: E402

pytestmark = pytest.mark.integration


@pytest.fixture
def bus():
    """A live connection, or a skip if the bus is not up. Never a false green."""
    r = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True, socket_timeout=3)
    try:
        r.ping()
    except redis.RedisError:
        pytest.skip("el bus no responde en 127.0.0.1:6379 (make bus-up)")
    return r


@pytest.fixture
def stream(bus):
    """A stream of its own per test, so nothing touches 'honeyml:events'."""
    nombre = f"prueba:bus:{uuid.uuid4().hex[:8]}"
    yield nombre
    bus.delete(nombre, f"{nombre}:muertos")


def _publicar(bus, stream: str, doc_id: str, command: str = "uname -a") -> str:
    return bus.xadd(
        stream,
        {
            "doc_id": doc_id,
            "timestamp": "2026-08-25T00:00:00.000Z",
            "honeypot": "cowrie",
            "category": "process",
            "action": "command-input",
            "outcome": "unknown",
            "protocol": "ssh",
            "source_ip": "203.0.113.7",
            "session": "abc123",
            "user": "root",
            "command": command,
        },
    )


def _consumidor(stream: str, manejador, **kw) -> ConsumidorDelBus:
    return ConsumidorDelBus(
        manejador,
        stream=stream,
        grupo="triaje-prueba",
        bloqueo_ms=200,
        inactividad_ms=0,
        **kw,
    )


def _limpiar_marcas(bus, *doc_ids: str) -> None:
    """Dedup marks outlive the stream, so a rerun would see the previous run's events."""
    for d in doc_ids:
        bus.delete(PREFIJO_VISTO + d)


def test_procesa_y_confirma(bus, stream):
    """The happy path: the handler receives the event and nothing stays pending."""
    doc_id = uuid.uuid4().hex
    _limpiar_marcas(bus, doc_id)
    _publicar(bus, stream, doc_id)

    vistos: list[EventoDelBus] = []
    c = _consumidor(stream, vistos.append, nombre="agente-1")
    c.correr(limite=1)

    assert len(vistos) == 1
    assert vistos[0].doc_id == doc_id
    assert vistos[0].command == "uname -a"
    assert c.contadores.procesados == 1
    # Zero pending is the whole point: the event is settled, not merely delivered.
    assert bus.xpending(stream, "triaje-prueba")["pending"] == 0

    _limpiar_marcas(bus, doc_id)


def test_el_grupo_se_crea_una_sola_vez(bus, stream):
    """Creating the group twice must not raise: every start calls it."""
    c = _consumidor(stream, lambda e: None)
    c.asegurar_grupo()
    c.asegurar_grupo()  # BUSYGROUP se absorbe
    assert bus.xinfo_groups(stream)[0]["name"] == "triaje-prueba"


def test_repetido_se_saltea_sin_volver_a_procesar(bus, stream):
    """The same doc_id delivered twice must run the handler once.

    This is not hypothetical: the real stream carried 52.165 messages with 52.156 distinct
    document ids, because a normalizer restart replays what was between checkpoints.
    """
    doc_id = uuid.uuid4().hex
    _limpiar_marcas(bus, doc_id)

    vistos: list[EventoDelBus] = []
    _publicar(bus, stream, doc_id)
    c = _consumidor(stream, vistos.append, nombre="agente-1")
    c.correr(limite=1)

    # el mismo evento vuelve a publicarse: distinta entrada del stream, mismo documento
    _publicar(bus, stream, doc_id)
    c2 = _consumidor(stream, vistos.append, nombre="agente-1")
    c2.correr(limite=5)

    assert len(vistos) == 1, "el manejador no debe correr dos veces sobre el mismo documento"
    assert c2.contadores.repetidos == 1
    # Settled anyway: leaving it pending would bring it back forever.
    assert bus.xpending(stream, "triaje-prueba")["pending"] == 0

    _limpiar_marcas(bus, doc_id)


def test_fallo_del_manejador_deja_el_evento_pendiente(bus, stream):
    """A failed decision must stay recoverable, not be swallowed by the acknowledgement."""
    doc_id = uuid.uuid4().hex
    _limpiar_marcas(bus, doc_id)
    _publicar(bus, stream, doc_id)

    def explota(_evento: EventoDelBus) -> None:
        raise RuntimeError("el servicio de inferencia no respondió")

    c = _consumidor(stream, explota, nombre="agente-1")
    c.correr(limite=1)

    assert c.contadores.fallados == 1
    assert c.contadores.procesados == 0
    assert bus.xpending(stream, "triaje-prueba")["pending"] == 1
    # Not marked as done, so a later attempt will actually redo the work.
    assert not bus.exists(PREFIJO_VISTO + doc_id)

    _limpiar_marcas(bus, doc_id)


def test_huerfano_lo_reclama_otro_consumidor(bus, stream):
    """What a dead consumer left pending must be taken over by a live one.

    This is the property that separates 'the engine restarts' from 'the engine loses nothing'.
    """
    doc_id = uuid.uuid4().hex
    _limpiar_marcas(bus, doc_id)
    _publicar(bus, stream, doc_id)

    def cae(_evento: EventoDelBus) -> None:
        raise RuntimeError("el consumidor se cayó antes de decidir")

    # agente-1 toma el evento y muere antes de decidir
    muerto = _consumidor(stream, cae, nombre="agente-1")
    muerto.correr(limite=1)
    assert bus.xpending(stream, "triaje-prueba")["pending"] == 1

    # agente-2 lo rescata
    vistos: list[EventoDelBus] = []
    vivo = _consumidor(stream, vistos.append, nombre="agente-2")
    rescatados = vivo.reclamar_huerfanos()

    assert len(rescatados) == 1
    assert rescatados[0].doc_id == doc_id
    assert rescatados[0].entregas == 2, "la reentrega tiene que quedar contada"

    for evento in rescatados:
        vivo.procesar(evento)
    assert len(vistos) == 1
    assert bus.xpending(stream, "triaje-prueba")["pending"] == 0

    _limpiar_marcas(bus, doc_id)


def test_evento_venenoso_termina_en_muertos(bus, stream):
    """An event that always fails must stop blocking the group.

    Without a ceiling it would be reclaimed forever: the group never advances and every round
    spends an inference call on the same event.
    """
    doc_id = uuid.uuid4().hex
    _limpiar_marcas(bus, doc_id)
    _publicar(bus, stream, doc_id, command="rm -rf /")

    def explota(_evento: EventoDelBus) -> None:
        raise ValueError("esquema inválido")

    c = _consumidor(stream, explota, nombre="agente-1", max_entregas=2)
    c.correr(limite=1)  # entrega 1, falla

    # se reintenta hasta pasar el techo
    for _ in range(3):
        for evento in c.reclamar_huerfanos():
            c.procesar(evento)

    assert c.contadores.descartados == 1
    assert bus.xpending(stream, "triaje-prueba")["pending"] == 0, "el grupo tiene que avanzar"

    muertos = bus.xrange(f"{stream}:muertos")
    assert len(muertos) == 1
    _, campos = muertos[0]
    assert campos["doc_id"] == doc_id
    assert campos["command"] == "rm -rf /", "el evento tiene que quedar inspeccionable"
    assert "entregas" in campos["_motivo"]

    _limpiar_marcas(bus, doc_id)
