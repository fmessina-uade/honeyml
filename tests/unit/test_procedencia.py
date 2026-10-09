"""El chequeo de procedencia del corpus: qué cuenta y que no muestra direcciones."""

from __future__ import annotations

import json
from typing import Any

from honeyml.medicion import procedencia


def _grupo(cantidad: int, conjuntos: dict[str, int], dias: list[str], direcciones: int) -> Any:
    return {
        "doc_count": cantidad,
        "conjuntos": {"buckets": [{"key": k, "doc_count": v} for k, v in conjuntos.items()]},
        "dias": {"buckets": [{"key_as_string": f"{d}T00:00:00.000Z"} for d in dias]},
        "direcciones": {"value": direcciones},
    }


RESPUESTA = {
    "hits": {"total": {"value": 1_000}},
    "aggregations": {
        "primero": {"value_as_string": "2026-05-29T23:23:11.679Z"},
        "ultimo": {"value_as_string": "2026-10-03T22:00:59.000Z"},
        "publica": {"doc_count": 900, "primero": {"value_as_string": "2026-05-30T06:17:10.490Z"}},
        "grupos": {
            "buckets": {
                "loopback": _grupo(60, {"dionaea.httpd": 30, "dionaea.smbd": 30}, [], 1),
                "privada": _grupo(2, {"cowrie.session.connect": 1}, ["2026-05-29"], 1),
                "sin_direccion": _grupo(38, {"dionaea.ftpdatalisten": 38}, [], 0),
            }
        },
        "marcas": {"buckets": [{"key": "_geo_sin_resultado", "doc_count": 5}]},
    },
}


def test_nunca_agrupa_por_direccion() -> None:
    """Una agregación de términos sobre una dirección la devolvería tal cual en la respuesta."""
    texto = json.dumps(procedencia.consulta())
    for campo in ("source.ip", "destination.ip"):
        assert f'"terms": {{"field": "{campo}"' not in texto


def test_el_informe_separa_cada_grupo_y_lo_que_no_tiene_conjunto() -> None:
    lineas = procedencia.informe(RESPUESTA)
    assert "Eventos: 1,000" in lineas
    assert "Desde direcciones públicas: 900" in lineas
    assert "privada: 2 eventos" in "\n".join(lineas)
    assert "  días: 2026-05-29" in lineas
    assert "  sin conjunto de datos: 1" in lineas
    assert "  _geo_sin_resultado: 5" in lineas
    # el grupo sin dirección no tiene direcciones que contar
    assert lineas.count("  direcciones distintas: 1") == 2
