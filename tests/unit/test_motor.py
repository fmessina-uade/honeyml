"""El cableado del bus con el grafo, sin red, sin índice y sin proveedor.

Lo que se fija acá son las cuatro propiedades del contrato con el consumidor, que son las que hacen
que el motor no pierda eventos ni plata:

- un evento que entra sale con su decisión persistida
- si algo del ciclo levanta, la excepción sale del manejador, así el consumidor no confirma
- el grafo se compila una vez y no por evento
- los adaptadores también, que es de lo que depende que el consumo por modelo se pueda medir
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from honeyml.agent import motor
from honeyml.agent.adapters.almacen import AlmacenNoDisponibleError
from honeyml.agent.adapters.config import MODELO_POR_DEFECTO
from honeyml.agent.adapters.inferencia import (
    PRECIOS,
    ProveedorInalcanzableError,
    Respuesta,
)
from honeyml.agent.consumer import EventoDelBus
from honeyml.agent.nodes import contexto, historial
from honeyml.agent.state import Contexto

# Un doc_id con la forma real, un SHA-256, y no un "abc123": es el largo que el motor tiene que
# poder arrastrar hasta el identificador del documento.
DOC_ID = "459c0f59e6781f286fe03ac429e621c037e92a69ace3b2d494b6ae45d4c7b120"

DECISION = {
    "severidad": "alto",
    "confianza": 0.9,
    "tactica_mitre": "Descubrimiento",
    "justificacion": "Ejecutó un comando de reconocimiento dentro del señuelo.",
    "evidencia": ["comando ejecutado: uname -a"],
}


class _Servicio:
    """Cuenta las llamadas y devuelve lo que se le indique. No toca la red."""

    def __init__(
        self, cuerpo: dict[str, Any] | None = None, falla: Exception | None = None
    ) -> None:
        self.cuerpo = cuerpo if cuerpo is not None else DECISION
        self.falla = falla
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
        if self.falla is not None:
            raise self.falla
        return Respuesta(
            contenido=json.dumps(self.cuerpo),
            tokens_entrada=1200,
            tokens_salida=180,
            segundos=0.9,
            modelo="openai/gpt-oss-20b",
        )


class _Almacen:
    def __init__(self, falla: Exception | None = None) -> None:
        self.falla = falla
        self.escrituras: list[tuple[str, dict[str, Any]]] = []

    def guardar(self, doc_id: str, documento: dict[str, Any]) -> bool:
        if self.falla is not None:
            raise self.falla
        self.escrituras.append((doc_id, documento))
        return True


def _evento(**kw: Any) -> EventoDelBus:
    base = {
        "entry_id": "1-0",
        "doc_id": DOC_ID,
        "timestamp": "2026-08-20T10:00:00Z",
        "honeypot": "cowrie",
        "category": "process",
        "source_ip": "203.0.113.7",
        "session": "s1",
        "command": "uname -a",
    }
    base.update(kw)
    return EventoDelBus(**base)  # type: ignore[arg-type]


@pytest.fixture
def sin_indice(monkeypatch: pytest.MonkeyPatch) -> None:
    """Los dos nodos que consultan Elasticsearch quedan reemplazados por uno que no sale a la red.

    Lo que se prueba acá es el cableado, no las consultas, que tienen sus propias pruebas. Se
    reemplazan en el módulo del nodo y no en el grafo, porque `construir_grafo` los toma de ahí.
    """
    monkeypatch.setattr(
        contexto,
        "construir",
        lambda estado: {"contexto": Contexto(doc_id=DOC_ID, resumen="cowrie/process · uname -a")},
    )
    monkeypatch.setattr(historial, "recuperar", lambda estado: {})


# ---- el camino que funciona ---------------------------------------------------------------------


def test_un_evento_sale_con_su_decision_persistida(sin_indice: None) -> None:
    servicio, almacen = _Servicio(), _Almacen()
    triar = motor.manejador(servicio=servicio, almacen=almacen)

    triar(_evento())

    assert servicio.llamadas == 1
    doc_id, doc = almacen.escrituras[0]
    assert doc_id == DOC_ID
    assert doc["decision"]["severidad"] == "alto"
    assert doc["decision"]["concluyente"] is True


def test_el_documento_lleva_el_doc_id_completo(sin_indice: None) -> None:
    """El identificador es un SHA-256 de 64 caracteres y tiene que llegar entero al índice."""
    almacen = _Almacen()
    motor.manejador(servicio=_Servicio(), almacen=almacen)(_evento())

    doc_id, doc = almacen.escrituras[0]
    assert len(doc_id) == 64
    assert doc["evento"]["doc_id"] == DOC_ID


def test_un_evento_sin_origen_no_gasta_una_llamada() -> None:
    """Se corta en el nodo de contexto, pero igual queda persistido como no concluyente."""
    servicio, almacen = _Servicio(), _Almacen()
    motor.manejador(servicio=servicio, almacen=almacen)(_evento(source_ip=""))

    assert servicio.llamadas == 0
    _, doc = almacen.escrituras[0]
    assert doc["ciclo"]["motivo_de_corte"] == "sin_contexto"
    assert doc["decision"]["concluyente"] is False


# ---- el contrato con el consumidor: levantar significa "no resuelto" -----------------------------


def test_si_el_proveedor_no_responde_la_excepcion_sale(sin_indice: None) -> None:
    """Tiene que salir del manejador: el consumidor no confirma y otro reclama el evento."""
    almacen = _Almacen()
    triar = motor.manejador(
        servicio=_Servicio(falla=ProveedorInalcanzableError("sin red")), almacen=almacen
    )

    with pytest.raises(ProveedorInalcanzableError):
        triar(_evento())

    assert almacen.escrituras == []  # no se persistió nada, porque no se decidió nada


def test_si_el_almacen_no_responde_la_excepcion_sale(sin_indice: None) -> None:
    """Confirmar un evento cuya decisión no se guardó lo pierde para siempre, y en silencio."""
    triar = motor.manejador(
        servicio=_Servicio(), almacen=_Almacen(falla=AlmacenNoDisponibleError("índice caído"))
    )

    with pytest.raises(AlmacenNoDisponibleError):
        triar(_evento())


# ---- lo que se arma una sola vez ----------------------------------------------------------------


def test_el_grafo_se_compila_una_vez_y_no_por_evento(
    sin_indice: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Compilarlo por evento sería trabajo repetido en el camino caliente del motor."""
    compilaciones = 0
    original = motor.construir_grafo

    def contando(*a: Any, **kw: Any) -> Any:
        nonlocal compilaciones
        compilaciones += 1
        return original(*a, **kw)

    monkeypatch.setattr(motor, "construir_grafo", contando)

    triar = motor.manejador(servicio=_Servicio(), almacen=_Almacen())
    for _ in range(3):
        triar(_evento())

    assert compilaciones == 1


def test_el_adaptador_se_crea_una_vez_y_no_por_evento(
    sin_indice: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """De esto depende que el consumo por modelo se pueda medir.

    Creado por evento, el desglose arrancaría de cero cada vez y "cuántos eventos resolvió el
    modelo económico" respondería siempre uno, además de releer la configuración del disco en
    cada llamada.

    Se cuenta el camino sin inyección, que es el que corre en producción: con un adaptador inyectado
    compartirlo es trivial y la prueba no probaría nada.
    """
    creados = 0

    def contando(*a: Any, **kw: Any) -> Any:
        nonlocal creados
        creados += 1
        return _Servicio()

    monkeypatch.setattr(motor, "AdaptadorDeInferencia", contando)

    triar = motor.manejador(almacen=_Almacen())
    for i in range(3):
        triar(_evento(entry_id=f"{i}-0"))

    assert creados == 1


# ---- la línea que se imprime por evento ---------------------------------------------------------


def test_la_linea_dice_el_nivel_y_la_tactica(sin_indice: None) -> None:
    from honeyml.agent.graph import ejecutar
    from honeyml.agent.state import estado_inicial

    compilado = motor.compilar(servicio=_Servicio(), almacen=_Almacen())
    final = ejecutar(compilado, estado_inicial(_evento()))

    linea = motor._linea(_evento(), final)
    assert "alto" in linea
    assert "Descubrimiento" in linea


def test_la_linea_de_un_evento_sin_decision_dice_el_motivo() -> None:
    from honeyml.agent.graph import ejecutar
    from honeyml.agent.state import estado_inicial

    compilado = motor.compilar(servicio=_Servicio(), almacen=_Almacen())
    final = ejecutar(compilado, estado_inicial(_evento(source_ip="")))

    assert "sin_contexto" in motor._linea(_evento(source_ip=""), final)


# ---- la guardia de gasto ------------------------------------------------------------------------


def test_el_costo_estimado_usa_el_modelo_mas_caro() -> None:
    """Es un techo para el caso feliz, así el número no sorprende para abajo."""
    entrada, salida = motor.TOKENS_TIPICOS
    p_entrada, p_salida = PRECIOS[MODELO_POR_DEFECTO]
    esperado = (entrada * p_entrada + salida * p_salida) / 1_000_000

    assert motor.costo_estimado(1) == pytest.approx(esperado)
    assert motor.costo_estimado(0) == 0


def test_un_reprocesamiento_historico_supera_el_tope() -> None:
    """Un atraso de decenas de miles de mensajes no arranca sin pedirlo.

    Si alguien sube TOPE_SIN_CONFIRMAR por encima de eso, el `make triaje` sin argumentos vuelve a
    poder gastar decenas de dólares de una, que es exactamente lo que la guardia evita.
    """
    assert 50_000 > motor.TOPE_SIN_CONFIRMAR
    assert motor.costo_estimado(50_000) > 10


# ---- la cuota del proveedor ---------------------------------------------------------------------


def test_la_cuota_agotada_corta_la_corrida_y_no_persiste(sin_indice: None) -> None:
    """El motor traduce la cuota del proveedor a una parada del consumidor.

    Sin la traducción, el consumidor la trataría como una falla común del evento y seguiría con el
    siguiente, que va a fallar igual.
    """
    from honeyml.agent.adapters.inferencia import CuotaAgotadaError
    from honeyml.agent.consumer import DetenerConsumo

    almacen = _Almacen()
    servicio = _Servicio(falla=CuotaAgotadaError("sin cuota"))
    triar = motor.manejador(servicio=servicio, almacen=almacen)

    with pytest.raises(DetenerConsumo, match="sin cuota"):
        triar(_evento())
    assert almacen.escrituras == []


class _RedisFalso:
    """Lo mínimo de Redis que usa la estimación: el grupo, los mensajes y el repertorio."""

    def __init__(self, mensajes: list[tuple[str, dict[str, str]]], conocidas: set[str]) -> None:
        self.mensajes = mensajes
        self.conocidas = conocidas

    def xinfo_groups(self, _stream: str) -> list[dict[str, Any]]:
        return [{"name": "triaje", "last-delivered-id": "0-0"}]

    def xrange(self, _stream: str, **_kw: Any) -> list[tuple[str, dict[str, str]]]:
        return self.mensajes

    def exists(self, clave: str) -> int:
        return int(clave in self.conocidas)


def test_la_estimacion_con_reutilizacion_cuenta_conductas_y_no_mensajes() -> None:
    """Mil mensajes de la misma conducta son una sola llamada, y una conducta resuelta, ninguna."""
    from types import SimpleNamespace

    from honeyml.agent import firma
    from honeyml.agent.adapters.repertorio import PREFIJO

    uname = {"honeypot": "cowrie", "category": "process", "command": "uname -a"}
    ls = {"doc_id": "resuelto", "honeypot": "cowrie", "category": "process", "command": "ls"}
    mensajes = [(f"{i}-0", {**uname, "doc_id": str(i)}) for i in range(1000)] + [("2000-0", ls)]
    conocida = PREFIJO + firma.de_evento(EventoDelBus.desde_mensaje("0-0", ls))
    consumidor = SimpleNamespace(
        r=_RedisFalso(mensajes, {conocida}), stream="honeyml:events", grupo="triaje"
    )

    assert motor.firmas_nuevas(consumidor) == 1  # type: ignore[arg-type]
