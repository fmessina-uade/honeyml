"""Comportamiento del consumidor del bus contra un Redis de verdad.

Acá se comprueban las propiedades que hacen que el motor sobreviva, que son justo las que no se
pueden verificar leyendo el código: que la confirmación llegue recién después de que el manejador
salió bien, que una falla deje el evento recuperable, que otro consumidor pueda levantar lo que dejó
uno muerto, y que un evento que falla siempre deje de trabar al grupo en vez de dar vueltas.

Corren contra un stream y un grupo descartables, nunca los de producción, y limpian lo suyo al
terminar.

    make test-integration        (necesita el bus arriba: make bus-up)
"""

from __future__ import annotations

import uuid

import pytest

redis = pytest.importorskip("redis", reason="requiere el extra [agent]")

from honeyml.agent.consumer import PREFIJO_VISTO, ConsumidorDelBus, EventoDelBus  # noqa: E402

pytestmark = pytest.mark.integration


@pytest.fixture
def bus():
    """Una conexión viva, o se saltea si el bus no está arriba. Nunca un verde falso."""
    r = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True, socket_timeout=3)
    try:
        r.ping()
    except redis.RedisError:
        pytest.skip("el bus no responde en 127.0.0.1:6379 (make bus-up)")
    return r


@pytest.fixture
def stream(bus):
    """Un stream propio por prueba, así nada toca 'honeyml:events'."""
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
    """Las marcas de deduplicación sobreviven al stream: sin esto, una recorrida vería los eventos
    de la anterior."""
    for d in doc_ids:
        bus.delete(PREFIJO_VISTO + d)


def test_procesa_y_confirma(bus, stream):
    """El camino feliz: el manejador recibe el evento y no queda nada pendiente."""
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
    # Cero pendientes es toda la gracia: el evento quedó resuelto, no solamente entregado.
    assert bus.xpending(stream, "triaje-prueba")["pending"] == 0

    _limpiar_marcas(bus, doc_id)


def test_el_grupo_se_crea_una_sola_vez(bus, stream):
    """Crear el grupo dos veces no puede levantar: cada arranque lo llama."""
    c = _consumidor(stream, lambda e: None)
    c.asegurar_grupo()
    c.asegurar_grupo()  # BUSYGROUP se absorbe
    assert bus.xinfo_groups(stream)[0]["name"] == "triaje-prueba"


def test_repetido_se_saltea_sin_volver_a_procesar(bus, stream):
    """El mismo doc_id entregado dos veces tiene que correr el manejador una sola.

    No es hipotético: el stream real llevó 52.165 mensajes con 52.156 identificadores de documento
    distintos, porque un reinicio del normalizador reproduce lo que había entre puntos de control.
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
    # Igual queda resuelto: dejarlo pendiente lo traería de vuelta para siempre.
    assert bus.xpending(stream, "triaje-prueba")["pending"] == 0

    _limpiar_marcas(bus, doc_id)


def test_un_manejador_que_avisa_repeticion_cuenta_como_repetido(bus, stream):
    """Si la decisión ya existía, el evento se confirma igual pero no se cuenta como procesado.

    Es lo que separa una relectura del corpus de una tanda de triaje en el resumen de la corrida.
    El 14/09 el bus recibió decenas de miles de eventos ya decididos, y contados como procesados
    habrían parecido trabajo nuevo.
    """
    doc_id = uuid.uuid4().hex
    _limpiar_marcas(bus, doc_id)
    _publicar(bus, stream, doc_id)

    c = _consumidor(stream, lambda _evento: True, nombre="agente-1")
    c.correr(limite=1)

    assert c.contadores.repetidos == 1
    assert c.contadores.procesados == 0
    # Resuelto y marcado, igual que un evento procesado: el trabajo está hecho.
    assert bus.xpending(stream, "triaje-prueba")["pending"] == 0
    assert bus.exists(PREFIJO_VISTO + doc_id)

    _limpiar_marcas(bus, doc_id)


def test_fallo_del_manejador_deja_el_evento_pendiente(bus, stream):
    """Una decisión fallada tiene que seguir siendo recuperable, no comida por la confirmación."""
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
    # No queda marcado como hecho, así un intento posterior rehace el trabajo de verdad.
    assert not bus.exists(PREFIJO_VISTO + doc_id)

    _limpiar_marcas(bus, doc_id)


def test_huerfano_lo_reclama_otro_consumidor(bus, stream):
    """Lo que dejó pendiente un consumidor muerto lo tiene que levantar uno vivo.

    Esta es la propiedad que separa "el motor reinicia" de "el motor no pierde nada".
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
    """Un evento que falla siempre tiene que dejar de trabar al grupo.

    Sin un techo se reclamaría para siempre: el grupo no avanza nunca y cada vuelta gasta una
    llamada de inferencia sobre el mismo evento.
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


def test_un_evento_sin_doc_id_va_directo_a_la_cola_de_muertos(bus, stream):
    """No se puede deduplicar ni persistir, así que no vale gastar una llamada paga en él.

    El pipeline arma el campo con `.to_s` sobre la metadata, así que si la huella no se calculó
    llega la cadena vacía en lugar de faltar. Sin esta guardia el evento entraba al grafo, se
    triaba, y recién fallaba al indexar bajo un identificador que no existe: hasta tres llamadas
    pagas por entrega, y tres entregas antes de que la cola lo apartara.
    """
    _publicar(bus, stream, doc_id="")

    vistos: list[EventoDelBus] = []
    c = _consumidor(stream, vistos.append, nombre="agente-1")
    c.correr(limite=1)

    assert vistos == []  # el manejador no llegó a verlo
    assert c.contadores.descartados == 1
    assert bus.xpending(stream, "triaje-prueba")["pending"] == 0  # el grupo avanza
    assert bus.xlen(f"{stream}:muertos") == 1
