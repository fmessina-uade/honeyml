"""Lo que llega repetido no pisa nada.

El bus puede recibir otra vez eventos decididos semanas antes: Filebeat relee desde el principio un
archivo que cambia de identidad, algo que en desarrollo pasa al bajar registros con rsync. Las
marcas de deduplicación del consumidor vencen a las 24 horas y ya no los reconocen, y con la
reutilización encendida el evento de origen de una firma se copiaría de sí mismo y pisaría la
decisión razonada.

Se fija la protección en las capas que la sostienen: el motor no vuelve a triar lo que ya tiene
decisión, el almacén no sobrescribe, la persistencia no escribe una copia de sí misma, y el motor le
avisa al consumidor que el evento ya estaba decidido. El conteo del lado del consumidor necesita un
bus de verdad y vive en las pruebas de integración.
"""

from __future__ import annotations

import io
import json
import urllib.error
from typing import Any

import pytest

from honeyml.agent import motor
from honeyml.agent.adapters import almacen as almacen_mod
from honeyml.agent.adapters.almacen import AlmacenElastic, AlmacenNoDisponibleError
from honeyml.agent.adapters.inferencia import Respuesta
from honeyml.agent.consumer import EventoDelBus
from honeyml.agent.nodes import contexto, historial, persistencia
from honeyml.agent.state import Contexto, Decision, estado_inicial

DOC_ID = "459c0f59e6781f286fe03ac429e621c037e92a69ace3b2d494b6ae45d4c7b120"

DECISION = {
    "severidad": "alto",
    "confianza": 0.9,
    "tactica_mitre": "Descubrimiento",
    "motivo_sin_tactica": None,
    "justificacion": "Ejecutó un comando de reconocimiento dentro del señuelo.",
    "evidencia": ["comando ejecutado: uname -a"],
}


def _evento(**kw: Any) -> EventoDelBus:
    base: dict[str, Any] = {
        "entry_id": "1-0",
        "doc_id": DOC_ID,
        "timestamp": "2026-09-14T10:00:00Z",
        "honeypot": "cowrie",
        "category": "process",
        "source_ip": "203.0.113.7",
        "session": "s1",
        "command": "uname -a",
    }
    base.update(kw)
    return EventoDelBus(**base)


def _estado(**kw: Any) -> Any:
    estado = estado_inicial(_evento())
    estado.update(kw)  # type: ignore[typeddict-item]
    return estado


class _Almacen:
    """Un almacén en memoria que contesta lo que se le indique: escribió, o ya estaba."""

    def __init__(self, escribe: bool = True, ya_decidido: bool = False) -> None:
        self.escribe = escribe
        self.ya_decidido = ya_decidido
        self.escrituras: list[str] = []

    def guardar(self, doc_id: str, documento: dict[str, Any]) -> bool:
        if self.escribe:
            self.escrituras.append(doc_id)
        return self.escribe

    def existe(self, doc_id: str) -> bool:
        return self.ya_decidido


class _Repertorio:
    def __init__(self) -> None:
        self.datos: dict[str, dict[str, Any]] = {}

    def consultar(self, firma: str) -> dict[str, Any] | None:
        return self.datos.get(firma)

    def registrar(self, firma: str, decision: dict[str, Any], doc_id: str) -> None:
        self.datos[firma] = {"decision": decision, "doc_id": doc_id}


# El almacén.


class _Respuesta:
    status = 201

    def __enter__(self) -> _Respuesta:
        return self

    def __exit__(self, *_a: Any) -> None:
        return None


class _Red:
    """Reemplaza `urlopen`: anota la URL de cada pedido y contesta en orden lo que se le indique."""

    def __init__(self, respuestas: list[Any]) -> None:
        self.respuestas = respuestas
        self.urls: list[str] = []
        self.metodos: list[str] = []

    def __call__(self, pedido: Any, timeout: float = 0) -> Any:
        self.urls.append(pedido.full_url)
        self.metodos.append(pedido.get_method())
        siguiente = self.respuestas.pop(0)
        if isinstance(siguiente, BaseException):
            raise siguiente
        return siguiente


def _http(codigo: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "http://x",
        codigo,
        "",
        {},  # type: ignore[arg-type]
        io.BytesIO(b"{}"),
    )


@pytest.fixture
def red(monkeypatch: pytest.MonkeyPatch) -> Any:
    def armar(respuestas: list[Any]) -> _Red:
        falsa = _Red(respuestas)
        monkeypatch.setattr(almacen_mod.urllib.request, "urlopen", falsa)
        monkeypatch.setattr(almacen_mod.time, "sleep", lambda _s: None)
        return falsa

    return armar


def test_por_omision_escribe_sin_sobrescribir(red: Any) -> None:
    """`_create` y no `_doc`: es lo que hace que Elasticsearch se niegue a pisar."""
    transporte = red([_Respuesta()])
    assert AlmacenElastic().guardar(DOC_ID, {"a": 1}) is True
    assert "/_create/" in transporte.urls[0]


def test_una_decision_que_ya_existe_no_se_pisa(red: Any) -> None:
    """El 409 no es una falla: es la respuesta correcta a una repetición, y no se reintenta."""
    transporte = red([_http(409)])
    assert AlmacenElastic().guardar(DOC_ID, {"a": 1}) is False
    assert len(transporte.urls) == 1


def test_un_409_tras_una_falla_pasajera_se_informa_como_existente(red: Any) -> None:
    """Aunque pueda ser nuestra propia escritura que llegó, se informa como ya existente.

    Ese mismo 409 lo produce también una repetición, y tratarlo como escrito registraría en el
    repertorio una decisión distinta de la guardada. Informarlo como existente cuesta a lo sumo una
    llamada más adelante; la otra opción rompe la auditoría.
    """
    transporte = red([TimeoutError("se cortó"), _http(409)])
    assert AlmacenElastic().guardar(DOC_ID, {"a": 1}) is False
    assert len(transporte.urls) == 2


def test_reescribir_vuelve_a_sobrescribir(red: Any) -> None:
    transporte = red([_Respuesta()])
    assert AlmacenElastic(reescribir=True).guardar(DOC_ID, {"a": 1}) is True
    assert "/_doc/" in transporte.urls[0]


def test_reescribiendo_un_409_no_se_disimula(red: Any) -> None:
    """Con `_doc` no debería llegar nunca un 409. Si llega, es algo raro y tiene que verse."""
    red([_http(409)])
    with pytest.raises(AlmacenNoDisponibleError):
        AlmacenElastic(reescribir=True).guardar(DOC_ID, {"a": 1})


def test_saber_si_existe_no_trae_el_documento(red: Any) -> None:
    transporte = red([_Respuesta()])
    assert AlmacenElastic().existe(DOC_ID) is True
    assert transporte.metodos == ["HEAD"]
    assert transporte.urls[0].endswith(f"/honeyml-decisiones/_doc/{DOC_ID}")


def test_un_404_es_que_no_hay_decision(red: Any) -> None:
    """También lo contesta un índice que todavía no se creó, y la respuesta es la misma."""
    red([_http(404)])
    assert AlmacenElastic().existe(DOC_ID) is False


def test_si_la_consulta_falla_levanta_sin_reintentar(red: Any) -> None:
    """Todavía no se gastó ninguna llamada, así que el evento puede volver al bus sin costo."""
    transporte = red([TimeoutError("se cortó")])
    with pytest.raises(AlmacenNoDisponibleError) as exc:
        AlmacenElastic().existe(DOC_ID)
    assert exc.value.pasajero is True
    assert len(transporte.urls) == 1


# La persistencia.


def test_nunca_escribe_una_copia_de_si_misma() -> None:
    """Si el origen de la firma es este mismo evento, lo que llegó es una repetición.

    Vale aunque el almacén aceptara la escritura: un documento que dice haberse copiado de sí mismo
    no tiene lectura posible en una auditoría.
    """
    almacen, repertorio = _Almacen(), _Repertorio()
    salida = persistencia.guardar(
        _estado(firma="f1", decision=Decision.model_validate(DECISION), reutilizada_de=DOC_ID),
        almacen=almacen,
        repertorio=repertorio,
    )
    assert salida == {"ya_existia": True}
    assert almacen.escrituras == []
    assert repertorio.datos == {}


def test_si_ya_existia_no_registra_la_firma() -> None:
    """Lo guardado puede decir otra cosa que este estado, y el repertorio apuntaría a eso."""
    repertorio = _Repertorio()
    salida = persistencia.guardar(
        _estado(firma="f1", decision=Decision.model_validate(DECISION)),
        almacen=_Almacen(escribe=False),
        repertorio=repertorio,
    )
    assert salida == {"ya_existia": True}
    assert repertorio.datos == {}


def test_una_escritura_nueva_si_registra_la_firma() -> None:
    """El control: sin repetición, la reutilización sigue funcionando igual que antes."""
    repertorio = _Repertorio()
    salida = persistencia.guardar(
        _estado(firma="f1", decision=Decision.model_validate(DECISION)),
        almacen=_Almacen(),
        repertorio=repertorio,
    )
    assert salida == {}
    assert repertorio.datos["f1"]["doc_id"] == DOC_ID


# El motor.


class _Servicio:
    def __init__(self) -> None:
        self.llamadas = 0

    def completar(
        self,
        sistema: str,
        usuario: str,
        esquema: dict[str, Any],
        *,
        intento: int = 0,
        nombre_esquema: str = "decision",
    ) -> Respuesta:
        self.llamadas += 1
        return Respuesta(
            contenido=json.dumps(DECISION),
            tokens_entrada=1200,
            tokens_salida=180,
            segundos=0.9,
            modelo="openai/gpt-oss-20b",
        )


@pytest.fixture
def sin_indice(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        contexto,
        "construir",
        lambda estado: {"contexto": Contexto(doc_id=DOC_ID, resumen="cowrie/process, uname -a")},
    )
    monkeypatch.setattr(historial, "recuperar", lambda estado: {})


def test_el_manejador_avisa_cuando_ya_estaba_decidido(sin_indice: None) -> None:
    """Es lo que usa el consumidor para contar el evento como repetido y no como procesado."""
    assert motor.manejador(servicio=_Servicio(), almacen=_Almacen(escribe=False))(_evento()) is True
    assert motor.manejador(servicio=_Servicio(), almacen=_Almacen())(_evento()) is False


def test_lo_ya_decidido_no_vuelve_a_pasar_por_el_grafo(sin_indice: None) -> None:
    """Se confirma como repetido sin gastar una llamada ni intentar escribir."""
    servicio, almacen = _Servicio(), _Almacen(ya_decidido=True)
    assert motor.manejador(servicio=servicio, almacen=almacen)(_evento()) is True
    assert servicio.llamadas == 0
    assert almacen.escrituras == []


def test_reescribiendo_se_decide_aunque_ya_exista(sin_indice: None) -> None:
    servicio, almacen = _Servicio(), _Almacen(ya_decidido=True)
    motor.manejador(servicio=servicio, almacen=almacen, saltear_decididos=False)(_evento())
    assert servicio.llamadas == 1
    assert almacen.escrituras == [DOC_ID]
