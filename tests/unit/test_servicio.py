"""The inference boundary and its model-selection policy.

Lo que se fija acá es la política —barato primero, capaz al reintentar— y las dos formas en que
podría dejar de aplicarse sin que nadie se entere: que el modelo quede fijado por configuración sin
que se note, o que el desglose por modelo se pierda y ya no se pueda evaluar si conviene.
"""

from __future__ import annotations

from typing import Any

from honeyml.agent.adapters.config import (
    MODELO_ALTERNATIVO,
    MODELO_POR_DEFECTO,
    ConfigInferencia,
)
from honeyml.agent.adapters.inferencia import Respuesta
from honeyml.agent.adapters.servicio import (
    AdaptadorDeInferencia,
    ServicioDeInferencia,
    elegir_modelo,
)

CLAVE = "gsk_1234567890abcdefGHIJ"


class _ClienteFalso:
    """Registra con qué modelo se lo llamó. No toca la red."""

    def __init__(self, config: ConfigInferencia) -> None:
        self.config = config
        self.modelos: list[str] = []

    def completar(self, **kw: Any) -> Respuesta:
        modelo = kw["modelo"]
        self.modelos.append(modelo)
        return Respuesta(
            contenido="{}",
            tokens_entrada=100,
            tokens_salida=50,
            segundos=0.5,
            modelo=modelo,
        )


def _adaptador(modelo: str = MODELO_POR_DEFECTO) -> tuple[AdaptadorDeInferencia, _ClienteFalso]:
    config = ConfigInferencia(api_key=CLAVE, modelo=modelo)
    cliente = _ClienteFalso(config)
    return AdaptadorDeInferencia(cliente=cliente, config=config), cliente  # type: ignore[arg-type]


# ---- la política ----------------------------------------------------------------------------


def test_el_primer_intento_usa_el_modelo_economico() -> None:
    assert elegir_modelo(intento=0) == MODELO_ALTERNATIVO


def test_cualquier_reintento_escala_al_modelo_capaz() -> None:
    """Con temperatura 0, repetir con el que ya falló es la peor apuesta del presupuesto."""
    assert elegir_modelo(intento=1) == MODELO_POR_DEFECTO
    assert elegir_modelo(intento=2) == MODELO_POR_DEFECTO


def test_un_modelo_fijado_desactiva_la_politica() -> None:
    """El escape existe para medir un modelo contra el otro sobre el mismo corpus."""
    assert elegir_modelo(intento=0, fijado="otro/modelo") == "otro/modelo"
    assert elegir_modelo(intento=5, fijado="otro/modelo") == "otro/modelo"


def test_el_valor_por_defecto_no_cuenta_como_fijado() -> None:
    """Si contara, arrancar sin HONEYML_MODELO clavaría el modelo capaz y la política moriría.

    Y moriría en silencio, que es la peor forma: todo seguiría funcionando, más caro.
    """
    adaptador, _ = _adaptador(MODELO_POR_DEFECTO)
    assert adaptador.modelo_fijado is None

    fijado, _ = _adaptador("otro/modelo")
    assert fijado.modelo_fijado == "otro/modelo"


# ---- el adaptador ---------------------------------------------------------------------------


def test_el_ciclo_correctivo_escala_de_modelo() -> None:
    adaptador, cliente = _adaptador()
    for intento in range(3):
        adaptador.completar("s", "u", {"type": "object"}, intento=intento)

    assert cliente.modelos == [MODELO_ALTERNATIVO, MODELO_POR_DEFECTO, MODELO_POR_DEFECTO]


def test_con_modelo_fijado_no_escala_nunca() -> None:
    adaptador, cliente = _adaptador("otro/modelo")
    for intento in range(3):
        adaptador.completar("s", "u", {"type": "object"}, intento=intento)

    assert cliente.modelos == ["otro/modelo"] * 3


def test_el_consumo_se_lleva_separado_por_modelo() -> None:
    """Sin el desglose no hay forma de saber si la política ahorra algo."""
    adaptador, _ = _adaptador()
    adaptador.completar("s", "u", {}, intento=0)
    adaptador.completar("s", "u", {}, intento=0)
    adaptador.completar("s", "u", {}, intento=1)

    assert adaptador.por_modelo[MODELO_ALTERNATIVO].llamadas == 2
    assert adaptador.por_modelo[MODELO_POR_DEFECTO].llamadas == 1
    assert "66.7 %" in adaptador.resumen()


def test_sin_llamadas_el_resumen_no_miente() -> None:
    adaptador, _ = _adaptador()
    assert adaptador.resumen() == "sin llamadas"


def test_el_adaptador_satisface_la_frontera() -> None:
    """El nodo de inferencia depende del protocolo, no de esta clase."""
    adaptador, _ = _adaptador()
    servicio: ServicioDeInferencia = adaptador
    assert servicio.completar("s", "u", {}, intento=0).modelo == MODELO_ALTERNATIVO
