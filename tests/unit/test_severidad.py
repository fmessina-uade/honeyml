"""La escala de severidad: sus pisos, sus límites y el reparto que produce sobre tráfico real.

La escala existe para que la pueda comprobar alguien que no le cree al motor, así que estas pruebas
son las que hacen cierta esa afirmación. Dos merecen mención aparte.

`test_nunca_por_debajo_de_lo_que_prueba_el_registro` es la baranda sobre la que se apoya el nodo
de validación. `test_el_reparto_sobre_el_bus_real_no_es_degenerado` es la que agarraría una
redefinición que suena razonable aislada y termina aplastando el corpus en un solo nivel.
"""

from __future__ import annotations

import pytest

from honeyml.agent.consumer import EventoDelBus
from honeyml.agent.severidad import (
    CRITERIOS,
    LLEGAN_POR_EL_BUS,
    MARGEN_DE_ESCALADA,
    ORDEN,
    Severidad,
    dentro_de_limites,
    para_el_proveedor,
    piso,
    reproche,
    techo,
)

# Reparto real del bus al 25/08/2026, sensor · categoría · resultado · mensajes. Es el mismo cuadro
# que figura en el encabezado de `severidad.py`.
BUS_REAL = [
    ("cowrie", "process", "unknown", 30_334),
    ("cowrie", "authentication", "success", 11_712),
    ("dionaea", "authentication", "unknown", 4_245),
    ("dionaea", "authentication", "success", 2_159),
    ("cowrie", "process", "success", 2_055),
    ("cowrie", "process", "failure", 1_112),
    ("cowrie", "file", "unknown", 500),
    ("cowrie", "file", "failure", 48),
]


def _evento(categoria: str, outcome: str = "unknown", sensor: str = "cowrie") -> EventoDelBus:
    return EventoDelBus(
        entry_id="1-0",
        doc_id="abc",
        honeypot=sensor,
        category=categoria,
        outcome=outcome,
        source_ip="203.0.113.7",
    )


# ---- pisos ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("categoria", "outcome", "esperado"),
    [
        ("file", "unknown", Severidad.CRITICO),
        ("file", "failure", Severidad.CRITICO),
        ("process", "unknown", Severidad.ALTO),
        ("process", "failure", Severidad.ALTO),
        ("authentication", "success", Severidad.MEDIO),
        ("authentication", "unknown", Severidad.BAJO),
        ("authentication", "failure", Severidad.BAJO),
        ("network", "unknown", Severidad.INFORMATIVO),
    ],
)
def test_el_piso_sale_de_la_evidencia(categoria: str, outcome: str, esperado: Severidad) -> None:
    assert piso(_evento(categoria, outcome)) is esperado


def test_un_comando_fallido_sigue_siendo_una_intrusion() -> None:
    """Que el comando falle no baja el nivel: para haberlo escrito ya había que estar adentro."""
    assert piso(_evento("process", "failure")) is Severidad.ALTO


def test_dionaea_sin_resultado_no_se_asume_exitoso() -> None:
    """Mismo criterio que aplica el pipeline al inferir resultados: mejor no saber que suponer.

    MySQL y MSSQL no registran actividad posterior, así que el sensor no puede observar si la
    credencial sirvió. Tratar ese desconocido como acceso inflaría un cuarto del bus.
    """
    assert piso(_evento("authentication", "unknown", sensor="dionaea")) is Severidad.BAJO
    assert piso(_evento("authentication", "success", sensor="dionaea")) is Severidad.MEDIO


# ---- límites -------------------------------------------------------------------------------


def test_nunca_por_debajo_de_lo_que_prueba_el_registro() -> None:
    """La guarda sobre la que se apoya el nodo de validación del grafo."""
    evento = _evento("file")
    for nivel in (Severidad.INFORMATIVO, Severidad.BAJO, Severidad.MEDIO, Severidad.ALTO):
        assert not dentro_de_limites(nivel, evento)
    assert dentro_de_limites(Severidad.CRITICO, evento)


def test_se_admite_subir_exactamente_un_nivel() -> None:
    evento = _evento("authentication", "success")  # piso medio
    assert dentro_de_limites(Severidad.MEDIO, evento)
    assert dentro_de_limites(Severidad.ALTO, evento)
    assert not dentro_de_limites(Severidad.CRITICO, evento)


def test_el_techo_no_se_pasa_del_final_de_la_escala() -> None:
    """Con piso crítico, sumar el margen no puede salirse del índice."""
    assert techo(_evento("file")) is Severidad.CRITICO


def test_el_margen_declarado_es_el_que_se_aplica() -> None:
    """Si alguien cambia la constante, el techo tiene que moverse con ella y no quedar clavado."""
    evento = _evento("authentication", "unknown")
    assert ORDEN.index(techo(evento)) - ORDEN.index(piso(evento)) == MARGEN_DE_ESCALADA


# ---- reproches -----------------------------------------------------------------------------


def test_un_nivel_valido_no_genera_reproche() -> None:
    assert reproche(Severidad.ALTO, _evento("process")) is None


def test_el_reproche_por_debajo_nombra_la_evidencia() -> None:
    """El texto vuelve al proveedor: tiene que ser corregible, no un número de regla."""
    texto = reproche(Severidad.BAJO, _evento("file"))
    assert texto is not None
    assert CRITERIOS[Severidad.CRITICO].evidencia in texto
    assert "critico" in texto


def test_el_reproche_por_encima_dice_hasta_donde_se_puede() -> None:
    texto = reproche(Severidad.CRITICO, _evento("authentication", "unknown"))
    assert texto is not None
    assert "supera" in texto
    assert "medio" in texto  # el techo admitido


# ---- la escala como conjunto ---------------------------------------------------------------


def test_todos_los_niveles_tienen_criterio() -> None:
    """Un nivel sin criterio no se puede ni verificar ni explicar en el panel."""
    assert set(CRITERIOS) == set(ORDEN)
    assert len(ORDEN) == len(set(ORDEN))


def test_el_texto_para_el_proveedor_lista_la_escala_completa() -> None:
    """Se genera desde CRITERIOS: dos copias de una escala se desincronizan."""
    texto = para_el_proveedor()
    for nivel in ORDEN:
        assert nivel.value in texto
        assert CRITERIOS[nivel].evidencia in texto


def test_el_reparto_sobre_el_bus_real_no_es_degenerado() -> None:
    """Una escala donde todo cae en un nivel no ordena nada, y el defecto no se ve de otra forma.

    Los umbrales son deliberadamente flojos: la prueba está para atrapar un colapso, no para
    congelar los porcentajes de un corpus que sigue creciendo.
    """
    conteo: dict[Severidad, int] = {}
    for sensor, categoria, outcome, n in BUS_REAL:
        nivel = piso(_evento(categoria, outcome, sensor))
        conteo[nivel] = conteo.get(nivel, 0) + n

    total = sum(conteo.values())
    assert total == 52_165

    # Cuatro niveles distintos sobre el tráfico que realmente llega.
    assert set(conteo) == LLEGAN_POR_EL_BUS
    # Ninguno se come el corpus entero, y el crítico existe sin ser ruido.
    assert max(conteo.values()) / total < 0.80
    assert 0.001 < conteo[Severidad.CRITICO] / total < 0.10


def test_el_reconocimiento_no_llega_por_el_bus() -> None:
    """Está en la escala a propósito, pero declarar que llega sería falso: lo filtra el bus."""
    assert Severidad.INFORMATIVO not in LLEGAN_POR_EL_BUS
    assert Severidad.INFORMATIVO in ORDEN
