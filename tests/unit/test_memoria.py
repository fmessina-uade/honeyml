"""La reutilización de decisiones entre eventos de la misma conducta.

Es la pieza que vuelve pagable el atraso: 71.654 eventos del bus son 2.088 firmas distintas, así
que triar por conducta en lugar de por evento baja el costo de unos 35 dólares a un par, y el
régimen continuo de ~900 llamadas diarias a unas 25. Pero copiar una decisión es afirmar algo que no
se razonó, y eso solo es defendible si se cumplen unas cuantas cosas. Acá están fijadas.

La que sostiene todo lo demás es la invariante del piso: la firma incluye la categoría y el
resultado, y son los dos únicos campos de los que dependen el piso y el techo de severidad. Una
severidad defendible para el evento que se trió lo es por construcción para cualquier otro de la
misma firma. Sin eso habría que confiar en que el modelo sea consistente, y no lo es.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from honeyml.agent import firma as modulo_firma
from honeyml.agent.consumer import EventoDelBus
from honeyml.agent.nodes import memoria, persistencia
from honeyml.agent.severidad import Severidad, dentro_de_limites, piso, techo
from honeyml.agent.state import Decision, estado_inicial


def _evento(**kw: Any) -> EventoDelBus:
    base: dict[str, Any] = {
        "entry_id": "0-1",
        "doc_id": "doc-uno",
        "timestamp": "2026-09-10T04:12:55Z",
        "honeypot": "cowrie",
        "category": "process",
        "action": "command-input",
        "outcome": "unknown",
        "protocol": "ssh",
        "source_ip": "203.0.113.62",
        "session": "sesion-uno",
        "user": "",
        "command": "uname -a",
    }
    base.update(kw)
    return EventoDelBus(**base)


def _decision(severidad: Severidad = Severidad.ALTO) -> Decision:
    return Decision(
        severidad=severidad,
        confianza=0.8,
        tactica_mitre="Ejecución",
        justificacion="El atacante ejecutó un comando dentro del señuelo.",
        evidencia=["uname -a"],
    )


class RepertorioFalso:
    """Un repertorio en memoria, con la misma interfaz que el de Redis."""

    def __init__(self) -> None:
        self.datos: dict[str, dict[str, Any]] = {}
        self.consultas: list[str] = []

    def consultar(self, firma: str) -> dict[str, Any] | None:
        self.consultas.append(firma)
        return self.datos.get(firma)

    def registrar(self, firma: str, decision: dict[str, Any], doc_id: str) -> None:
        self.datos[firma] = {"decision": decision, "doc_id": doc_id}


# ---- la firma -------------------------------------------------------------------------------


def test_la_firma_ignora_quien_y_cuando() -> None:
    """Dos direcciones distintas haciendo lo mismo comparten firma. Es todo el punto."""
    uno = _evento(source_ip="1.1.1.1", session="a", doc_id="x", timestamp="2026-01-01T00:00:00Z")
    otro = _evento(source_ip="2.2.2.2", session="b", doc_id="y", timestamp="2026-09-09T23:00:00Z")
    assert modulo_firma.de_evento(uno) == modulo_firma.de_evento(otro)


def test_el_protocolo_parte_la_firma() -> None:
    """Fuerza bruta por SSH y por telnet no son la misma conducta, ni MSSQL y MySQL.

    Sin el protocolo adentro se juntarían, y no es un caso de borde: alcanza a una parte grande de
    los eventos del bus, a cambio de unas pocas firmas más.
    """
    ssh = _evento(category="authentication", action="login", protocol="ssh", user="root")
    telnet = _evento(category="authentication", action="login", protocol="telnet", user="root")
    assert modulo_firma.de_evento(ssh) != modulo_firma.de_evento(telnet)


@pytest.mark.parametrize("campo", modulo_firma.CAMPOS)
def test_cada_campo_de_la_conducta_parte_la_firma(campo: str) -> None:
    """Cambiar cualquiera de los seis da otra firma. Si no, se estarían mezclando conductas."""
    base = _evento()
    distinto = _evento(**{campo: "otra-cosa"})
    assert modulo_firma.de_evento(base) != modulo_firma.de_evento(distinto)


def test_el_separador_no_deja_colisionar_campos_corridos() -> None:
    """`user='ab'` con comando vacío no puede dar lo mismo que `user='a'` con comando `b`."""
    uno = modulo_firma.de_evento(_evento(user="ab", command=""))
    otro = modulo_firma.de_evento(_evento(user="a", command="b"))
    assert uno != otro


# ---- la invariante que vuelve correcta la reutilización --------------------------------------


@pytest.mark.parametrize(
    ("categoria", "resultado"),
    [
        ("authentication", "success"),
        ("authentication", "failure"),
        ("process", "unknown"),
        ("file", "unknown"),
        ("network", "unknown"),
    ],
)
def test_el_piso_no_depende_de_nada_que_la_firma_deje_afuera(
    categoria: str, resultado: str
) -> None:
    """Misma firma implica mismo piso y mismo techo, pase lo que pase con el resto del evento.

    Es la garantía de la que depende todo: una severidad defendible para el evento que se trió lo es
    para cualquier otro de la misma firma. Si algún día el piso pasara a mirar la dirección o la
    hora, esta prueba falla y la reutilización deja de ser legítima.
    """
    uno = _evento(
        category=categoria, outcome=resultado, source_ip="1.1.1.1", timestamp="2026-01-01T00:00:00Z"
    )
    otro = _evento(
        category=categoria,
        outcome=resultado,
        source_ip="9.9.9.9",
        session="otra",
        doc_id="otro",
        timestamp="2026-09-09T23:59:00Z",
    )
    assert modulo_firma.de_evento(uno) == modulo_firma.de_evento(otro)
    assert piso(uno) == piso(otro)
    assert techo(uno) == techo(otro)

    for nivel in Severidad:
        assert dentro_de_limites(nivel, uno) == dentro_de_limites(nivel, otro)


# ---- el nodo --------------------------------------------------------------------------------


def test_sin_repertorio_calcula_la_firma_y_no_decide() -> None:
    """El comportamiento con la reutilización apagada: se sigue por el camino largo."""
    salida = memoria.recordar(estado_inicial(_evento()))
    assert salida["firma"]
    assert "decision" not in salida


def test_una_firma_nueva_no_trae_decision() -> None:
    repertorio = RepertorioFalso()
    salida = memoria.recordar(estado_inicial(_evento()), repertorio=repertorio)
    assert "decision" not in salida
    assert repertorio.consultas == [salida["firma"]]


def test_una_firma_conocida_trae_la_decision_y_de_donde_salio() -> None:
    repertorio = RepertorioFalso()
    marca = modulo_firma.de_evento(_evento())
    repertorio.registrar(marca, _decision().model_dump(mode="json"), "doc-original")

    salida = memoria.recordar(estado_inicial(_evento(doc_id="doc-copia")), repertorio=repertorio)
    assert salida["decision"].severidad is Severidad.ALTO
    assert salida["reutilizada_de"] == "doc-original"


def test_una_entrada_que_ya_no_valida_se_descarta() -> None:
    """Si cambió el esquema, la decisión vieja no se copia: el evento se razona de nuevo.

    Copiar algo que hoy no valida metería en el índice un documento que el propio motor rechazaría
    si lo produjera ahora.
    """
    repertorio = RepertorioFalso()
    marca = modulo_firma.de_evento(_evento())
    repertorio.datos[marca] = {"decision": {"severidad": "inventada"}, "doc_id": "viejo"}

    salida = memoria.recordar(estado_inicial(_evento()), repertorio=repertorio)
    assert "decision" not in salida


# ---- el registro, que pasa por persistencia --------------------------------------------------


def _estado(**kw: Any) -> Any:
    estado = estado_inicial(_evento())
    estado.update(kw)  # type: ignore[typeddict-item]
    return estado


class AlmacenFalso:
    def __init__(self) -> None:
        self.escrito: list[tuple[str, dict[str, Any]]] = []

    def guardar(self, doc_id: str, documento: dict[str, Any]) -> bool:
        self.escrito.append((doc_id, documento))
        return True


def test_registra_la_firma_despues_de_guardar() -> None:
    repertorio, almacen = RepertorioFalso(), AlmacenFalso()
    persistencia.guardar(
        _estado(firma="f1", decision=_decision()), almacen=almacen, repertorio=repertorio
    )
    assert repertorio.datos["f1"]["doc_id"] == "doc-uno"


def test_no_registra_si_el_almacen_falla() -> None:
    """El orden es el mismo que usa el consumidor: la marca se escribe después del éxito.

    Al revés, la firma quedaría apuntando a una decisión que no se persistió, y las miles de
    repeticiones que vienen detrás copiarían de un documento que no existe.
    """

    class AlmacenRoto:
        def guardar(self, doc_id: str, documento: dict[str, Any]) -> None:
            raise RuntimeError("el índice no responde")

    repertorio = RepertorioFalso()
    with pytest.raises(RuntimeError):
        persistencia.guardar(
            _estado(firma="f1", decision=_decision()),
            almacen=AlmacenRoto(),  # type: ignore[arg-type]
            repertorio=repertorio,
        )
    assert repertorio.datos == {}


def test_no_registra_una_decision_no_concluyente() -> None:
    """Propagar un ciclo fallido le pondría el mismo fracaso a las 6.588 repeticiones."""
    repertorio, almacen = RepertorioFalso(), AlmacenFalso()
    persistencia.guardar(
        _estado(firma="f1", motivo_de_corte="sin_contexto"),
        almacen=almacen,
        repertorio=repertorio,
    )
    assert repertorio.datos == {}


def test_no_re_registra_lo_que_vino_del_repertorio() -> None:
    """El `doc_id` de origen tiene que seguir siendo el del evento que sí se razonó."""
    repertorio, almacen = RepertorioFalso(), AlmacenFalso()
    repertorio.registrar("f1", _decision().model_dump(mode="json"), "doc-original")
    persistencia.guardar(
        _estado(firma="f1", decision=_decision(), reutilizada_de="doc-original"),
        almacen=almacen,
        repertorio=repertorio,
    )
    assert repertorio.datos["f1"]["doc_id"] == "doc-original"


def test_el_documento_declara_que_la_decision_es_copiada() -> None:
    """Una decisión reutilizada tiene que ser distinguible de una razonada en el índice."""
    copiado = persistencia.documento(
        _estado(firma="f1", decision=_decision(), reutilizada_de="doc-original")
    )
    razonado = persistencia.documento(_estado(firma="f1", decision=_decision()))

    assert copiado["ciclo"]["reutilizada_de"] == "doc-original"
    assert copiado["ciclo"]["firma"] == "f1"
    assert razonado["ciclo"]["reutilizada_de"] is None
    assert razonado["ciclo"]["firma"] == "f1"
    # Las dos son concluyentes: copiar no degrada la decisión, solo dice de dónde vino.
    assert copiado["decision"]["concluyente"] is True
    assert razonado["decision"]["concluyente"] is True


def test_una_copia_no_se_atribuye_consumo_ni_intentos() -> None:
    """Copiar no gastó una llamada, así que el documento no puede decir que sí.

    Es lo que mantiene honestas las métricas del motor. Una copia con bloque `modelo` relleno
    contaría un costo que nadie pagó, y un `intentos` en uno contaría un intento que no hubo.

    La trampa que esto previene es sutil y va a aparecer al armar el panel: a medida que la
    reutilización crece, cualquier promedio de `ciclo.intentos` o de `modelo.costo_usd` sobre TODAS
    las decisiones se acerca a cero, y eso parece que el motor mejoró cuando lo que pasa es que la
    mayoría de los eventos no pasó por el motor. La regla es que toda métrica de desempeño filtre
    `ciclo.reutilizada_de` en nulo; las de cobertura del triaje, en cambio, cuentan todo.
    """
    consumo = {
        "nombre": "openai/gpt-oss-20b",
        "tokens_entrada": 1500,
        "tokens_salida": 400,
        "costo_usd": 0.0002,
        "segundos": 1.5,
    }
    razonado = persistencia.documento(
        _estado(firma="f1", decision=_decision(), intentos=1, consumo=consumo)
    )
    copiado = persistencia.documento(
        _estado(firma="f1", decision=_decision(), reutilizada_de="doc-original")
    )

    assert razonado["modelo"] == consumo
    assert razonado["ciclo"]["intentos"] == 1

    assert copiado["modelo"] == {}
    assert copiado["ciclo"]["intentos"] == 0

    # Y la decisión en sí es idéntica: lo que cambia es lo que costó, no lo que dice.
    assert copiado["decision"] == razonado["decision"]


def test_filtrar_las_copias_deja_solo_lo_que_costo_algo() -> None:
    """La consulta que el panel tiene que usar para medir el motor, fijada acá.

    Sin esto la convención vive en un comentario y se pierde. Con esto, si alguien cambia el nombre
    o el sentido del campo, la prueba lo frena.
    """
    documentos = [
        persistencia.documento(_estado(firma="f1", decision=_decision(), intentos=1)),
        persistencia.documento(
            _estado(firma="f1", decision=_decision(), reutilizada_de="doc-original")
        ),
        persistencia.documento(
            _estado(firma="f1", decision=_decision(), reutilizada_de="doc-original")
        ),
    ]
    razonadas = [d for d in documentos if d["ciclo"]["reutilizada_de"] is None]

    assert len(documentos) == 3  # cobertura del triaje: tres eventos decididos
    assert len(razonadas) == 1  # desempeño del motor: una sola llamada
    assert sum(d["ciclo"]["intentos"] for d in razonadas) == 1


def test_los_campos_nuevos_estan_declarados_en_la_plantilla() -> None:
    """El índice va en `dynamic: strict`, así que un campo sin declarar se rechaza al escribir.

    Es la clase de error que no aparece en ninguna prueba con almacén falso y rompe recién contra el
    Elasticsearch de verdad, con el evento ya consumido del bus.
    """
    from pathlib import Path

    plantilla = json.loads(
        (
            Path(__file__).parents[2] / "infra/elastic/templates/honeyml-decisiones-template.json"
        ).read_text(encoding="utf-8")
    )
    ciclo = plantilla["template"]["mappings"]["properties"]["ciclo"]["properties"]
    documento = persistencia.documento(
        _estado(firma="f1", decision=_decision(), reutilizada_de="doc-original")
    )
    for campo in documento["ciclo"]:
        assert campo in ciclo, f"'{campo}' no está declarado en la plantilla del índice"
