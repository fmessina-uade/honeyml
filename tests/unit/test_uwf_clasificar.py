"""La demostración del clasificador, sin el conjunto de referencia ni el modelo exportado.

Lo que se fija es lo que volvería engañosa a una demostración si se rompiera: que la muestra deje
afuera a la clase débil, que prediga con otro punto de operación que el de la tarjeta, o que el
error que muestra no sea un error.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from honeyml.features import uwf_clasificar as demo


class _Pipeline:
    """Devuelve las probabilidades que se le indiquen, en el orden de clases de sklearn."""

    classes_ = np.array(["Exfiltration", "Reconnaissance", "none"])

    def __init__(self, proba: list[list[float]]) -> None:
        self.proba = np.array(proba)

    def predict_proba(self, x: pd.DataFrame) -> np.ndarray:
        return self.proba


def _tarjeta(umbral: float) -> dict[str, Any]:
    return {"punto_de_operacion": {"clase": "Exfiltration", "umbral": umbral}}


def test_la_muestra_incluye_la_clase_debil_aunque_sea_rara() -> None:
    """Al azar sobre toda la prueba, una clase del 0,03 % no aparecería nunca."""
    y = pd.Series(["none"] * 1000 + ["Exfiltration"] * 3 + ["Reconnaissance"] * 50)
    clases = y.iloc[demo.muestra_por_clase(y, por_clase=2, semilla=1)]
    assert (clases == "Exfiltration").sum() == 2
    assert set(clases) == {"none", "Exfiltration", "Reconnaissance"}


def test_una_clase_con_menos_casos_aporta_los_que_tiene() -> None:
    y = pd.Series(["none"] * 10 + ["Exfiltration"])
    assert len(demo.muestra_por_clase(y, por_clase=3, semilla=1)) == 4


def test_con_la_misma_semilla_la_muestra_es_la_misma() -> None:
    """Es lo que permite ensayar una demostración y que en vivo salga lo mismo."""
    y = pd.Series(["none"] * 500 + ["Reconnaissance"] * 500)
    assert demo.muestra_por_clase(y, 2, 7) == demo.muestra_por_clase(y, 2, 7)


def test_predice_con_el_umbral_de_la_tarjeta() -> None:
    """Con 0,35 para la clase débil y 0,60 para otra, decide el umbral y no el máximo."""
    pipe = _Pipeline([[0.35, 0.60, 0.05]])
    x = pd.DataFrame({"a": [0]})

    alcanza, probabilidad = demo.predecir(pipe, x, _tarjeta(0.30))
    no_alcanza, _ = demo.predecir(pipe, x, _tarjeta(0.40))

    assert alcanza[0] == "Exfiltration"
    assert probabilidad[0] == 0.35
    assert no_alcanza[0] == "Reconnaissance"


def test_la_probabilidad_es_la_de_la_clase_predicha() -> None:
    pipe = _Pipeline([[0.05, 0.15, 0.80], [0.10, 0.70, 0.20]])
    predicha, probabilidad = demo.predecir(pipe, pd.DataFrame({"a": [0, 1]}), _tarjeta(0.30))
    assert list(predicha) == ["none", "Reconnaissance"]
    assert list(probabilidad) == [0.80, 0.70]


def test_el_error_que_muestra_es_un_error() -> None:
    real = np.array(["none", "none", "Exfiltration", "none"])
    predicha = np.array(["none", "Exfiltration", "Exfiltration", "none"])
    assert demo.un_error(real, predicha, semilla=3) == 1


def test_sin_errores_no_inventa_uno() -> None:
    real = np.array(["none", "Exfiltration"])
    assert demo.un_error(real, real.copy(), semilla=3) is None
