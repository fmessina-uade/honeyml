"""La regla de las credenciales en las rutas que las muestran: sesiones grabadas y detalle."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.error import URLError

import pytest
from fastapi.testclient import TestClient

from honeyml.api import main, privacidad, queries
from honeyml.api.main import app

SESIONES = [
    {"attacker": "attacker-1", "credentials": {"user": "root", "password": "123456"}},
    {"attacker": "attacker-2", "credentials": {"user": "admin", "password": "unica"}},
]


@pytest.fixture
def sesiones_grabadas(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archivo = tmp_path / "replay_sessions.json"
    archivo.write_text(json.dumps(SESIONES), encoding="utf-8")
    monkeypatch.setattr(main, "REPLAY_FILE", archivo)


@pytest.mark.usefixtures("como_invitado", "sesiones_grabadas")
def test_las_sesiones_muestran_solo_las_credenciales_que_pasan_la_regla(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pedidos: list[dict[str, Any]] = []

    def falso(body: dict[str, Any], es_url: str = "") -> dict[str, Any]:
        pedidos.append(body)
        return {
            "aggregations": {
                "u": {
                    "buckets": [
                        {"key": "root", "doc_count": 900, "origenes": {"value": 300}},
                        {"key": "admin", "doc_count": 400, "origenes": {"value": 90}},
                    ]
                },
                "p": {
                    "buckets": [
                        {"key": "123456", "doc_count": 700, "origenes": {"value": 200}},
                        {"key": "unica", "doc_count": 3, "origenes": {"value": 1}},
                    ]
                },
            }
        }

    monkeypatch.setattr(queries, "_search", falso)
    r = TestClient(app).get("/api/replays")
    assert r.status_code == 200
    credenciales = [s["credentials"] for s in r.json()]
    assert credenciales[0] == {"user": "root", "password": "123456"}
    assert credenciales[1] == {"user": "admin", "password": privacidad.CREDENCIAL_TAPADA}
    # se pregunta solo por los valores de las sesiones
    assert pedidos[0]["aggs"]["p"]["terms"]["include"] == ["123456", "unica"]


@pytest.mark.usefixtures("como_invitado", "sesiones_grabadas")
def test_sin_indice_las_sesiones_tapan_todas_las_credenciales(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def caido(body: dict[str, Any], es_url: str = "") -> dict[str, Any]:
        raise URLError("sin Elasticsearch")

    monkeypatch.setattr(queries, "_search", caido)
    r = TestClient(app).get("/api/replays")
    assert r.status_code == 200
    for sesion in r.json():
        assert sesion["credentials"] == {
            "user": privacidad.CREDENCIAL_TAPADA,
            "password": privacidad.CREDENCIAL_TAPADA,
        }


def _detalle(monkeypatch: pytest.MonkeyPatch) -> None:
    evento = {"user.name": "root", "cowrie.password": "123456", "source.ip": "203.0.113.9"}
    monkeypatch.setattr(
        main.decisiones,
        "detalle",
        lambda doc_id: {"doc_id": doc_id, "decision": {}, "evento": evento},
    )


@pytest.mark.usefixtures("como_invitado")
def test_el_invitado_no_ve_la_contrasena_del_evento(monkeypatch: pytest.MonkeyPatch) -> None:
    _detalle(monkeypatch)
    evento = TestClient(app).get("/api/decisiones/d1").json()["evento"]
    assert evento["cowrie.password"] == privacidad.CONTRASENA_OCULTA
    assert evento["source.ip"] == privacidad.TAPADA


@pytest.mark.usefixtures("como_analista")
def test_el_analista_ve_el_evento_como_llego(monkeypatch: pytest.MonkeyPatch) -> None:
    _detalle(monkeypatch)
    evento = TestClient(app).get("/api/decisiones/d1").json()["evento"]
    assert evento["cowrie.password"] == "123456"
