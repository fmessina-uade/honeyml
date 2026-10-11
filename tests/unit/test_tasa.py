"""Las tasas de falsos positivos y negativos, con un caso calculado a mano."""

from __future__ import annotations

from typing import Any

import pytest

from honeyml.medicion import tasa

POBLACION = {
    "escalada_con_transferencia": (10, 100),
    "escalada_sin_transferencia": (4, 40),
    "alto_con_transferencia": (2, 20),
    "alto_sin_transferencia": (20, 200),
}
# por estrato: cuántas se revisaron y cuántas marcó críticas el analista
REVISION = {
    "escalada_con_transferencia": (5, 4),
    "escalada_sin_transferencia": (4, 1),
    "alto_con_transferencia": (2, 2),
    "alto_sin_transferencia": (5, 1),
}


def _caso() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    muestra: dict[str, Any] = {
        "generada": "2026-10-05T21:18:00+00:00",
        "estratos": {
            e: {"conductas": c, "decisiones": d, "en_la_muestra": REVISION[e][0]}
            for e, (c, d) in POBLACION.items()
        },
        "conductas": [],
    }
    revisiones = []
    for estrato, (n, criticas) in REVISION.items():
        motor = "critico" if estrato.startswith("escalada") else "alto"
        for i in range(n):
            doc_id = f"{estrato}-{i}"
            muestra["conductas"].append({"doc_id": doc_id, "estrato": estrato, "firma": doc_id})
            revisiones.append(
                {
                    "doc_id": doc_id,
                    "a_ciegas": True,
                    "severidad": "critico" if i < criticas else "alto",
                    "tactica_mitre": "Ejecución",
                    "motor": {
                        "severidad": motor,
                        "tactica_mitre": "Ejecución" if i % 2 else "Descubrimiento",
                    },
                }
            )
    # una revisión común no entra en la cuenta
    revisiones.append(
        {"doc_id": "escalada_con_transferencia-0", "a_ciegas": False, "severidad": "alto"}
    )
    return muestra, revisiones


def test_la_regla_cuenta_sobre_toda_la_poblacion() -> None:
    r = tasa.calcular(*_caso())
    assert r["regla"]["conductas"]["falsos_positivos"] == pytest.approx(4 / 24)
    assert r["regla"]["conductas"]["falsos_negativos"] == pytest.approx(2 / 12)
    assert r["regla"]["decisiones"]["falsos_positivos"] == pytest.approx(40 / 240)


def test_el_analista_se_estima_pesando_cada_estrato() -> None:
    r = tasa.calcular(*_caso())
    # 10 x 0,2 + 4 x 0,75 = 5 falsos positivos contra 20 x 0,8 = 16 verdaderos negativos
    assert r["analista"]["conductas"]["falsos_positivos"]["tasa"] == pytest.approx(5 / 21)
    # 2 x 1 + 20 x 0,2 = 6 falsos negativos contra 10 x 0,8 + 4 x 0,25 = 9 verdaderos positivos
    assert r["analista"]["conductas"]["falsos_negativos"]["tasa"] == pytest.approx(6 / 15)
    bajo, alto = r["analista"]["conductas"]["falsos_positivos"]["intervalo_95"]
    assert bajo <= 5 / 21 <= alto


def test_coincidencias_y_lo_que_se_deja_afuera() -> None:
    r = tasa.calcular(*_caso())
    assert r["revisadas"] == 16
    assert r["regla_contra_analista"]["coinciden"] == 4 + 3 + 2 + 4
    assert r["tactica"]["coinciden"] == 7
    assert r["motor_cambio_de_lado"] == 0
    assert r["por_estrato"]["alto_con_transferencia"]["proporcion_critica"] == 1


def test_wilson_en_los_extremos() -> None:
    assert tasa.wilson(0, 10)[0] == 0
    assert tasa.wilson(10, 10)[1] == 1
    assert tasa.wilson(0, 0) is None


def test_el_informe_se_lee() -> None:
    lineas = tasa.informe(tasa.calcular(*_caso()))
    texto = "\n".join(lineas)
    assert "16 de 16 conductas revisadas a ciegas" in texto
    assert "falsos positivos 16,7 %" in texto
    assert "kappa" in texto
