"""El nodo de persistencia: qué queda guardado, y qué pasa si el almacén no está.

Es el último nodo, así que lo que se fija acá es lo que el panel y quien audite van a poder leer
meses después. Cuatro cosas que se rompen sin hacer ruido:

- que un evento sin decisión igual quede registrado, en vez de desaparecer entre el bus y el panel
- que `concluyente` lo escriba el motor y no el modelo, porque describe el ciclo y no el evento
- que el documento se pueda leer solo, sin una segunda consulta al índice de telemetría
- que una falla del almacén levante, para que el consumidor no confirme un evento que no se guardó
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from honeyml.agent.adapters import almacen as almacen_mod
from honeyml.agent.adapters.almacen import (
    MAX_REINTENTOS,
    AlmacenElastic,
    AlmacenNoDisponibleError,
)
from honeyml.agent.consumer import EventoDelBus
from honeyml.agent.nodes import persistencia as nodo
from honeyml.agent.state import Contexto, Decision


class _AlmacenFalso:
    """Guarda en memoria lo que se le pidió indexar. No toca la red."""

    def __init__(self) -> None:
        self.escrituras: list[tuple[str, dict[str, Any]]] = []

    def guardar(self, doc_id: str, documento: dict[str, Any]) -> bool:
        self.escrituras.append((doc_id, documento))
        return True


class _AlmacenCaido:
    def guardar(self, doc_id: str, documento: dict[str, Any]) -> bool:
        raise AlmacenNoDisponibleError("Elasticsearch no responde")


def _evento(**kw: Any) -> EventoDelBus:
    base = {
        "entry_id": "1-0",
        "doc_id": "abc123",
        "timestamp": "2026-08-20T10:00:00Z",
        "honeypot": "cowrie",
        "category": "process",
        "action": "command-input",
        "protocol": "ssh",
        "source_ip": "203.0.113.7",
        "session": "s1",
        "command": "uname -a",
    }
    base.update(kw)
    return EventoDelBus(**base)  # type: ignore[arg-type]


def _decision(**kw: Any) -> Decision:
    base: dict[str, Any] = {
        "severidad": "alto",
        "confianza": 0.85,
        "tactica_mitre": "Descubrimiento",
        "justificacion": "Ejecutó un comando de reconocimiento dentro del señuelo.",
        "evidencia": ["comando ejecutado: uname -a"],
    }
    base.update(kw)
    return Decision(**base)


def _estado(**kw: Any) -> Any:
    base: dict[str, Any] = {
        "evento": _evento(),
        "contexto": Contexto(doc_id="abc123", resumen="cowrie/process 203.0.113.7 ssh: uname -a"),
        "decision": _decision(),
        "intentos": 1,
        "rechazos": 0,
        "reproches": [],
        "consumo": {
            "nombre": "openai/gpt-oss-20b",
            "tokens_entrada": 1200,
            "tokens_salida": 180,
            "segundos": 0.9,
            "costo_usd": 0.000144,
        },
    }
    base.update(kw)
    return base


# El camino que funciona


def test_guarda_bajo_el_doc_id_del_evento() -> None:
    """El identificador es lo que hace idempotente al reintento: reescribe en vez de duplicar."""
    almacen = _AlmacenFalso()
    nodo.guardar(_estado(), almacen=almacen)

    doc_id, _ = almacen.escrituras[0]
    assert doc_id == "abc123"
    assert len(almacen.escrituras) == 1


def test_el_documento_se_lee_solo() -> None:
    """Sin esto el panel necesita una consulta al índice de telemetría por cada decisión listada."""
    doc = nodo.documento(_estado())

    assert doc["evento"]["origen"] == "203.0.113.7"
    assert doc["evento"]["sensor"] == "cowrie"
    assert doc["evento"]["protocolo"] == "ssh"
    assert doc["evento"]["momento"] == "2026-08-20T10:00:00Z"
    assert "uname -a" in doc["evento"]["resumen"]


def test_guarda_la_justificacion_y_la_evidencia() -> None:
    """Una decisión de triaje que no se puede releer es una opinión."""
    doc = nodo.documento(_estado())

    assert doc["decision"]["justificacion"].startswith("Ejecutó")
    assert doc["decision"]["evidencia"] == ["comando ejecutado: uname -a"]


def test_guarda_los_limites_que_la_escala_calculo() -> None:
    """Así quien audita verifica que el nivel era defendible sin recalcular la escala."""
    doc = nodo.documento(_estado())

    assert doc["decision"]["piso"] == "alto"  # el evento es de categoría process
    assert doc["decision"]["techo"] == "critico"  # piso más el margen de un nivel
    assert doc["decision"]["severidad"] == "alto"


def test_guarda_que_modelo_contesto_y_cuanto_costo() -> None:
    """Es la única forma de responder después si convino escalar recién al reintentar."""
    doc = nodo.documento(_estado())

    assert doc["modelo"]["nombre"] == "openai/gpt-oss-20b"
    assert doc["modelo"]["costo_usd"] == pytest.approx(0.000144)


def test_la_marca_temporal_de_la_decision_no_es_la_del_evento() -> None:
    """Una mide el atraso del motor y la otra ubica el ataque. Se necesitan las dos."""
    doc = nodo.documento(_estado())

    assert doc["@timestamp"] != doc["evento"]["momento"]
    assert doc["@timestamp"] > "2026-08-20"


# `concluyente` lo escribe el motor


def test_una_decision_valida_queda_concluyente() -> None:
    doc = nodo.documento(_estado())

    assert doc["decision"]["concluyente"] is True
    assert doc["ciclo"]["motivo_de_corte"] is None


def test_el_modelo_ni_siquiera_puede_opinar_sobre_concluyente() -> None:
    """El campo describe cómo terminó el ciclo, y eso el modelo no lo puede saber.

    No está en el esquema, así que si lo manda igual, `extra="forbid"` lo rechaza como cualquier
    campo inventado. Es más fuerte que pedírselo y sobrescribirlo: el modelo no llega a formarse
    una opinión que después haya que ignorar.
    """
    assert "concluyente" not in Decision.model_fields

    with pytest.raises(ValidationError):
        Decision(**{**_decision().model_dump(), "concluyente": False})


def test_el_modelo_no_puede_declararse_concluyente_si_el_ciclo_fallo() -> None:
    """El caso peligroso al revés: un corte por esquema inválido presentado como concluyente."""
    doc = nodo.documento(_estado(decision=None, motivo_de_corte="esquema_invalido"))

    assert doc["decision"]["concluyente"] is False
    assert doc["ciclo"]["motivo_de_corte"] == "esquema_invalido"


# Los caminos que no produjeron decisión


def test_un_evento_sin_decision_igual_queda_registrado() -> None:
    """Un evento que llegó al motor y no aparece en ningún lado no se puede ni contar."""
    almacen = _AlmacenFalso()
    nodo.guardar(_estado(decision=None, motivo_de_corte="sin_contexto"), almacen=almacen)

    _, doc = almacen.escrituras[0]
    assert doc["ciclo"]["motivo_de_corte"] == "sin_contexto"
    assert "severidad" not in doc["decision"]


def test_las_consultas_fallidas_quedan_y_mandan_a_revision() -> None:
    """Una decisión tomada sin parte del contexto la termina de decidir quien opera el panel."""
    contexto = Contexto(
        doc_id="abc123",
        resumen="x",
        hallazgos={"historial_falló": "KeyError: 'aggregations'", "sesion_falló": "timeout"},
    )
    doc = nodo.documento(_estado(contexto=contexto))

    assert doc["ciclo"]["consultas_fallidas"] == ["historial", "sesion"]
    assert doc["ciclo"]["requiere_revision"] is True
    assert doc["decision"]["concluyente"] is True  # concluyó, pero con el contexto incompleto


def test_una_decision_completa_no_va_a_revision() -> None:
    doc = nodo.documento(_estado())
    assert doc["ciclo"]["consultas_fallidas"] == []
    assert doc["ciclo"]["requiere_revision"] is False


def test_un_ciclo_que_no_concluye_va_a_revision() -> None:
    doc = nodo.documento(_estado(decision=None, motivo_de_corte="esquema_invalido"))
    assert doc["ciclo"]["requiere_revision"] is True


def test_una_decision_del_motor_en_vivo_no_es_retriaje() -> None:
    assert nodo.documento(_estado())["ciclo"]["retriaje"] is False


def test_una_decision_vuelta_a_triar_queda_marcada() -> None:
    """Su marca temporal no mide cuánto tardó el motor, y el tiempo de conclusión la descarta."""
    assert nodo.documento(_estado(retriaje=True))["ciclo"]["retriaje"] is True


def test_sin_decision_igual_se_guardan_los_limites() -> None:
    """Dicen qué se esperaba de ese evento, que es la mitad del diagnóstico."""
    doc = nodo.documento(_estado(decision=None, motivo_de_corte="esquema_invalido"))

    assert doc["decision"]["piso"] == "alto"
    assert doc["decision"]["techo"] == "critico"


def test_los_reproches_quedan_en_el_documento() -> None:
    """Cuentan si el modelo acertó de una o hubo que corregirlo, que es una métrica del motor."""
    doc = nodo.documento(
        _estado(reproches=["falta la evidencia", "severidad por debajo"], rechazos=2)
    )

    assert doc["ciclo"]["reproches"] == ["falta la evidencia", "severidad por debajo"]
    assert doc["ciclo"]["rechazos"] == 2


def test_los_reproches_tienen_tope() -> None:
    """Para que subir MAX_INTENTOS no infle el documento sin que nadie lo haya decidido."""
    doc = nodo.documento(_estado(reproches=[f"error {i}" for i in range(50)]))

    assert len(doc["ciclo"]["reproches"]) == nodo.MAX_REPROCHES_GUARDADOS


# Cuando el almacén no está


def test_si_el_almacen_no_responde_el_nodo_levanta() -> None:
    """Confirmar un evento cuya decisión no se guardó lo pierde para siempre, y en silencio."""
    with pytest.raises(AlmacenNoDisponibleError):
        nodo.guardar(_estado(), almacen=_AlmacenCaido())


def test_sin_evento_no_escribe_nada() -> None:
    """No hay identidad bajo la cual guardar, y un documento sin `doc_id` sería peor que ninguno."""
    almacen = _AlmacenFalso()

    assert nodo.guardar({}, almacen=almacen) == {}
    assert almacen.escrituras == []


# El documento contra el mapeo estricto


def _campos(objeto: Any, prefijo: str = "") -> set[str]:
    """Las rutas hoja de un diccionario anidado, en notación de puntos."""
    rutas: set[str] = set()
    for clave, valor in objeto.items():
        ruta = f"{prefijo}{clave}"
        if isinstance(valor, dict) and valor:
            rutas |= _campos(valor, f"{ruta}.")
        else:
            rutas.add(ruta)
    return rutas


def _declarados(propiedades: dict[str, Any], prefijo: str = "") -> set[str]:
    rutas: set[str] = set()
    for clave, definicion in propiedades.items():
        ruta = f"{prefijo}{clave}"
        if "properties" in definicion:
            rutas |= _declarados(definicion["properties"], f"{ruta}.")
        else:
            rutas.add(ruta)
    return rutas


def test_todo_campo_del_documento_esta_en_la_plantilla() -> None:
    """La plantilla es `dynamic: strict`, así que un campo no declarado hace fallar la escritura.

    Y falla en producción, contra un Elasticsearch de verdad, no acá. Esta prueba es lo único que
    hace que agregar un campo al documento y olvidarse de la plantilla salga en rojo antes.
    """
    plantilla = json.loads(
        Path("infra/elastic/templates/honeyml-decisiones-template.json").read_text(encoding="utf-8")
    )
    declarados = _declarados(plantilla["template"]["mappings"]["properties"])

    # Con decisión y sin ella: los dos caminos escriben, y no escriben lo mismo.
    usados = _campos(nodo.documento(_estado())) | _campos(
        nodo.documento(_estado(decision=None, motivo_de_corte="esquema_invalido"))
    )

    assert usados <= declarados, f"sin declarar en la plantilla: {sorted(usados - declarados)}"


def test_la_plantilla_es_estricta_y_de_un_solo_indice() -> None:
    """Dos decisiones de diseño que conviene que no se aflojen sin querer."""
    plantilla = json.loads(
        Path("infra/elastic/templates/honeyml-decisiones-template.json").read_text(encoding="utf-8")
    )

    assert plantilla["template"]["mappings"]["dynamic"] == "strict"
    # Un solo índice, sin comodín de fecha: es lo que sostiene la idempotencia por `doc_id`.
    assert plantilla["index_patterns"] == ["honeyml-decisiones"]


# El almacén: qué reintenta y qué no


class _Transporte:
    """Un transporte de mentira para `AlmacenElastic`, que cuenta los viajes y falla a pedido."""

    def __init__(self, fallas: list[Exception | None]) -> None:
        self.fallas = fallas
        self.viajes = 0

    def __call__(self, doc_id: str, documento: dict[str, Any]) -> bool:
        i = self.viajes
        self.viajes += 1
        falla = self.fallas[i] if i < len(self.fallas) else None
        if falla is not None:
            raise falla
        return True


@pytest.fixture(autouse=True)
def _sin_esperas(monkeypatch: pytest.MonkeyPatch) -> None:
    """La espera del retroceso no se cumple en las pruebas.

    Lo que se verifica es cuántos viajes hace, no cuánto duerme entre ellos. Sin esto, estas cuatro
    pruebas le agregaban dos segundos a cada corrida de la suite completa.
    """
    monkeypatch.setattr(almacen_mod.time, "sleep", lambda _segundos: None)


def _almacen(fallas: list[Exception | None]) -> tuple[AlmacenElastic, _Transporte]:
    almacen = AlmacenElastic()
    transporte = _Transporte(fallas)
    almacen._escribir = transporte  # type: ignore[method-assign]
    return almacen, transporte


def _pasajero() -> AlmacenNoDisponibleError:
    return AlmacenNoDisponibleError("el índice no responde", pasajero=True)


def _nuestro() -> AlmacenNoDisponibleError:
    return AlmacenNoDisponibleError("campo no declarado en el mapeo", pasajero=False)


def test_una_falla_pasajera_se_reintenta() -> None:
    """Sin esto, un parpadeo en el índice hace pagar de nuevo el ciclo de inferencia entero."""
    almacen, transporte = _almacen([_pasajero(), None])

    almacen.guardar("abc123", {"a": 1})

    assert transporte.viajes == 2


def test_los_reintentos_tienen_techo() -> None:
    almacen, transporte = _almacen([_pasajero()] * 10)

    with pytest.raises(AlmacenNoDisponibleError):
        almacen.guardar("abc123", {"a": 1})

    assert transporte.viajes == MAX_REINTENTOS


def test_un_defecto_nuestro_no_se_reintenta() -> None:
    """Un campo que el mapeo estricto rechaza da lo mismo tres veces: solo demora el diagnóstico."""
    almacen, transporte = _almacen([_nuestro(), None])

    with pytest.raises(AlmacenNoDisponibleError, match="mapeo"):
        almacen.guardar("abc123", {"a": 1})

    assert transporte.viajes == 1


def test_sin_doc_id_no_intenta_escribir() -> None:
    """La URL quedaría en `/_doc/` y Elasticsearch contesta un 405 que no dice nada del problema."""
    almacen, transporte = _almacen([None])

    with pytest.raises(AlmacenNoDisponibleError, match="doc_id"):
        almacen.guardar("", {"a": 1})

    assert transporte.viajes == 0
