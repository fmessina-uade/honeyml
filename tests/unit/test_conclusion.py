"""El tiempo de conclusión: el desglose entre copiadas y razonadas, y lo que se deja afuera."""

from __future__ import annotations

from typing import Any

import pytest

from honeyml import redes
from honeyml.medicion import conclusion


def _respuesta() -> dict[str, Any]:
    """Lo que devolvería Elasticsearch: 100 decisiones, 90 copiadas y 10 razonadas."""
    return {
        "hits": {"total": {"value": 100}},
        "aggregations": {
            "total": {
                "percentiles": {"values": {"50.0": 7800.0, "90.0": 11800.0}},
                "media": {"value": 8600.0},
            },
            "copiadas": {
                "doc_count": 90,
                "percentiles": {"values": {"50.0": 500.0, "90.0": 900.0}},
                "media": {"value": 600.0},
            },
            "razonadas": {
                "doc_count": 10,
                "percentiles": {"values": {"50.0": 9000.0, "90.0": 13000.0}},
                "media": {"value": 9500.0},
                "modelo_s": {"value": 1200.0},
            },
        },
    }


def test_el_desglose_separa_copiadas_de_razonadas(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(conclusion.queries, "_search", lambda *a, **k: _respuesta())
    r = conclusion.calcular("now-7d")

    assert (r["decisiones"], r["copiadas"], r["razonadas"]) == (100, 90, 10)
    assert r["total"]["media_s"] == 8.6
    assert r["copiadas_detalle"]["media_s"] == 0.6
    assert r["razonadas_detalle"]["media_s"] == 9.5
    assert r["razonadas_detalle"]["modelo_s"] == 1.2


def test_la_consulta_excluye_retriaje_y_origen_interno(monkeypatch: pytest.MonkeyPatch) -> None:
    capturado: dict[str, Any] = {}

    def espia(cuerpo: dict[str, Any], es_url: str = "", index: str = "") -> dict[str, Any]:
        capturado["cuerpo"] = cuerpo
        return _respuesta()

    monkeypatch.setattr(conclusion.queries, "_search", espia)
    conclusion.calcular("now-30d")

    must_not = capturado["cuerpo"]["query"]["bool"]["must_not"]
    assert {"term": {"ciclo.retriaje": True}} in must_not
    assert {"term": {"evento.origen": redes.INTERNAS[0]}} in must_not
    assert capturado["cuerpo"]["query"]["bool"]["filter"][0]["range"]["@timestamp"]["gte"] == (
        "now-30d"
    )


def test_el_informe_nombra_los_dos_caminos() -> None:
    texto = "\n".join(conclusion.informe(_resultado()))
    assert "Copiadas del repertorio" in texto
    assert "Razonadas con el modelo" in texto
    assert "la llamada al modelo" in texto


def _resultado() -> dict[str, Any]:
    return {
        "desde": "now-7d",
        "decisiones": 100,
        "copiadas": 90,
        "razonadas": 10,
        "total": {"media_s": 8.6, "mediana_s": 7.8, "p90_s": 11.8},
        "copiadas_detalle": {"media_s": 0.6, "mediana_s": 0.5, "p90_s": 0.9},
        "razonadas_detalle": {
            "media_s": 9.5,
            "mediana_s": 9.0,
            "p90_s": 13.0,
            "modelo_s": 1.2,
        },
    }
