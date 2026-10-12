"""El nodo de validación: qué borradores pasan, cuáles no, y qué se le devuelve al proveedor.

Lo que se fija acá son las formas de fallar que el esquema solo no atrapa, porque son las que
después no se notan:

- un JSON impecable que no se apoya en ningún hecho
- una severidad que contradice lo que prueba el registro
- varios problemas a la vez, que tienen que salir juntos y no de a uno por intento

Y una propiedad del contrato con el grafo: nunca se devuelven `decision` y `reproches` al mismo
tiempo, porque `ruta_tras_validar` decide entre reintentar y persistir mirando exactamente eso.
"""

from __future__ import annotations

from typing import Any

from honeyml.agent.consumer import EventoDelBus
from honeyml.agent.nodes import validacion as nodo
from honeyml.agent.state import Decision
from honeyml.education.annotations import TACTICAS_OBSERVABLES


def _evento(**kw: Any) -> EventoDelBus:
    base = {
        "entry_id": "1-0",
        "doc_id": "abc123",
        "timestamp": "2026-08-20T10:00:00Z",
        "honeypot": "cowrie",
        "category": "process",
        "source_ip": "203.0.113.7",
        "session": "s1",
        "command": "uname -a",
    }
    base.update(kw)
    return EventoDelBus(**base)  # type: ignore[arg-type]


def _borrador(**kw: Any) -> dict[str, Any]:
    """Un borrador válido para `_evento()`, que es de categoría `process` y tiene piso 'alto'."""
    base: dict[str, Any] = {
        "severidad": "alto",
        "confianza": 0.8,
        "tactica_mitre": "Descubrimiento",
        "motivo_sin_tactica": None,
        "justificacion": "Ejecutó un comando de reconocimiento dentro del señuelo.",
        "evidencia": ["comando ejecutado: uname -a"],
    }
    base.update(kw)
    return base


def _estado(**kw: Any) -> Any:
    base: dict[str, Any] = {"evento": _evento(), "borrador": _borrador()}
    base.update(kw)
    return base


# El camino que funciona
def test_un_borrador_correcto_produce_una_decision() -> None:
    salida = nodo.validar(_estado())

    assert "decision" in salida
    assert "reproches" not in salida
    assert salida["decision"].severidad == "alto"


def test_la_tactica_puede_venir_nula() -> None:
    """Nulo es una respuesta válida: no todo evento corresponde a una táctica."""
    borrador = _borrador(tactica_mitre=None, motivo_sin_tactica="evidencia_insuficiente")
    salida = nodo.validar(_estado(borrador=borrador))

    assert salida["decision"].motivo_sin_tactica == "evidencia_insuficiente"


def test_una_tactica_nula_sin_motivo_se_rechaza() -> None:
    salida = nodo.validar(_estado(borrador=_borrador(tactica_mitre=None)))

    assert "decision" not in salida
    reproche = next(r for r in salida["reproches"] if "motivo_sin_tactica" in r)
    for motivo in ("sin_objetivo_tactico", "evidencia_insuficiente", "fuera_del_catalogo"):
        assert motivo in reproche


def test_una_tactica_con_motivo_de_ausencia_se_rechaza() -> None:
    borrador = _borrador(motivo_sin_tactica="fuera_del_catalogo")
    salida = nodo.validar(_estado(borrador=borrador))

    assert "decision" not in salida
    assert any("va nulo cuando hay una táctica" in r for r in salida["reproches"])


def test_un_motivo_inventado_lo_rechaza_el_esquema() -> None:
    borrador = _borrador(tactica_mitre=None, motivo_sin_tactica="no sé")
    salida = nodo.validar(_estado(borrador=borrador))

    assert "decision" not in salida
    assert any("motivo_sin_tactica" in r for r in salida["reproches"])


# Lo que el esquema atrapa
def test_un_campo_que_falta_se_nombra_en_el_reproche() -> None:
    borrador = _borrador()
    del borrador["justificacion"]
    salida = nodo.validar(_estado(borrador=borrador))

    assert "decision" not in salida
    assert any("justificacion" in r for r in salida["reproches"])


def test_una_severidad_inventada_no_pasa() -> None:
    salida = nodo.validar(_estado(borrador=_borrador(severidad="catastrofico")))

    assert "decision" not in salida
    assert any("severidad" in r for r in salida["reproches"])


def test_una_confianza_fuera_de_rango_no_pasa() -> None:
    salida = nodo.validar(_estado(borrador=_borrador(confianza=1.7)))

    assert "decision" not in salida
    assert any("confianza" in r for r in salida["reproches"])


def test_un_campo_de_mas_no_pasa() -> None:
    """`extra="forbid"` no es cosmético: un campo inventado que nadie lee es una alucinación."""
    salida = nodo.validar(_estado(borrador=_borrador(prioridad="urgente")))

    assert "decision" not in salida
    assert any("prioridad" in r for r in salida["reproches"])


def test_una_respuesta_que_no_era_json_pide_json() -> None:
    salida = nodo.validar(
        _estado(borrador={nodo.CLAVE_SIN_PARSEAR: "Severidad alta, táctica Ejecución"})
    )

    assert "decision" not in salida
    assert any("JSON" in r for r in salida["reproches"])


def test_el_reproche_no_arrastra_el_texto_crudo_de_pydantic() -> None:
    """Lo lee el modelo y también quien audite: "Field required" no le sirve a ninguno."""
    borrador = _borrador()
    del borrador["confianza"]
    salida = nodo.validar(_estado(borrador=borrador))

    texto = " ".join(salida["reproches"])
    assert "Field required" not in texto
    assert "Input should" not in texto
    assert "obligatorio" in texto


# Lo que el esquema no puede atrapar
def test_el_esquema_no_le_pide_el_identificador_al_modelo() -> None:
    """Es un SHA-256 de 64 caracteres que habría que copiar exacto.

    Cada carácter errado costaría un reproche y un reintento pago sobre una severidad que puede
    estar bien juzgada. Nadie lee ese campo: persistencia indexa bajo el `doc_id` que viene del bus.
    """
    assert "doc_id" not in Decision.model_fields
    # Y si el modelo lo manda igual, `extra="forbid"` lo rechaza como cualquier campo inventado.
    salida = nodo.validar(_estado(borrador=_borrador(doc_id="lo que sea")))
    assert any("doc_id" in r for r in salida["reproches"])


def test_una_decision_sin_evidencia_se_rechaza() -> None:
    salida = nodo.validar(_estado(borrador=_borrador(evidencia=[])))

    assert "decision" not in salida
    assert any("evidencia" in r for r in salida["reproches"])


def test_una_tactica_que_el_senuelo_no_observa_se_rechaza() -> None:
    """Si pasara, la matriz MITRE del panel no la enciende y el hueco no se explica solo."""
    salida = nodo.validar(_estado(borrador=_borrador(tactica_mitre="Movimiento lateral")))

    assert "decision" not in salida
    assert any("Movimiento lateral" in r for r in salida["reproches"])


def test_el_reproche_de_tactica_lista_las_admitidas() -> None:
    salida = nodo.validar(_estado(borrador=_borrador(tactica_mitre="Exfiltración de datos")))

    texto = " ".join(salida["reproches"])
    for tactica in TACTICAS_OBSERVABLES:
        assert tactica in texto


def test_una_severidad_por_debajo_del_piso_se_rechaza() -> None:
    """El evento documenta ejecución de comandos, así que 'bajo' contradice el registro."""
    salida = nodo.validar(_estado(borrador=_borrador(severidad="bajo")))

    assert "decision" not in salida
    assert any("por debajo" in r for r in salida["reproches"])


def test_una_severidad_inflada_se_rechaza() -> None:
    """Piso 'alto' y margen de un nivel: 'critico' entra, pero solo porque el margen es uno."""
    evento = _evento(category="authentication", outcome="failure")
    salida = nodo.validar({"evento": evento, "borrador": _borrador(severidad="critico")})

    assert "decision" not in salida
    assert any("supera" in r for r in salida["reproches"])


def test_la_escalada_dentro_del_margen_se_acepta() -> None:
    """Lo que el margen existe para permitir: un nivel por encima del piso, con justificación."""
    salida = nodo.validar(_estado(borrador=_borrador(severidad="critico")))

    assert "decision" in salida


# El contrato con el grafo
def test_los_problemas_salen_todos_juntos() -> None:
    """De a uno por intento, un borrador con tres problemas se come el presupuesto entero."""
    salida = nodo.validar(
        _estado(borrador=_borrador(evidencia=[], severidad="bajo", tactica_mitre="Impacto"))
    )

    assert len(salida["reproches"]) == 3


def test_un_rechazo_cuenta_una_ronda_sin_importar_cuantos_problemas() -> None:
    """Los reproches miden qué corregir; `rechazos` mide cuántos intentos quedan. No son lo mismo.

    Contando reproches, un borrador con cuatro problemas se leería como cuatro intentos gastados y
    el modelo se quedaría sin ninguna oportunidad de corregir.
    """
    salida = nodo.validar(
        _estado(borrador=_borrador(evidencia=[], severidad="bajo", tactica_mitre="Impacto"))
    )

    assert len(salida["reproches"]) == 3
    assert salida["rechazos"] == 1


def test_todo_rechazo_suma_una_ronda() -> None:
    """Si un camino de rechazo se olvidara de contarla, el ciclo giraría hasta el techo de pasos."""
    borrador_incompleto = _borrador()
    del borrador_incompleto["severidad"]

    for borrador in (
        {nodo.CLAVE_SIN_PARSEAR: "no era json"},  # ni siquiera parseó
        borrador_incompleto,  # no cumple el esquema
        _borrador(evidencia=[]),  # cumple el esquema, no el contenido
    ):
        assert nodo.validar(_estado(borrador=borrador))["rechazos"] == 1


def test_nunca_devuelve_decision_y_reproches_a_la_vez() -> None:
    for borrador in (_borrador(), _borrador(evidencia=[]), _borrador(severidad="bajo")):
        salida = nodo.validar(_estado(borrador=borrador))
        assert ("decision" in salida) != ("reproches" in salida)


def test_sin_borrador_no_deja_reproche() -> None:
    """Sin reproche, el ciclo lo lee como agotado y persiste. Con reproche, reintentaría en vano."""
    assert nodo.validar({"evento": _evento()}) == {}
    assert nodo.validar({"borrador": _borrador()}) == {}
