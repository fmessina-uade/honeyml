"""Una instalación nueva, antes de que llegue un evento de afuera, sin Elasticsearch.

Hay dos momentos así. Sin ningún índice de los sensores, Elasticsearch contesta sin agregaciones;
con índice pero solo con ataques desde la propia máquina, el filtro de orígenes internos deja cero
eventos y la portada se queda sin fechas. En los dos el panel tiene que decir qué pasa en lugar de
romperse con un 500.
"""

from __future__ import annotations

import io
import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from honeyml.api import main, queries
from honeyml.api.main import app


@pytest.fixture
def sin_cache() -> Iterator[None]:
    main._snapshot.update(momento=0.0, datos=None)
    yield
    main._snapshot.update(momento=0.0, datos=None)


def test_un_patron_sin_indices_avisa_que_no_hay_eventos(monkeypatch: pytest.MonkeyPatch) -> None:
    respuesta = {"hits": {"total": {"value": 0}, "hits": []}, "_shards": {"total": 0}}
    monkeypatch.setattr(
        queries.urllib.request,
        "urlopen",
        lambda req, timeout=0: io.BytesIO(json.dumps(respuesta).encode()),
    )

    with pytest.raises(queries.SinEventosError):
        queries._search({"size": 0, "aggs": {"x": {"terms": {"field": "honeypot"}}}})
    # sin agregaciones pedidas, la misma respuesta es válida
    assert queries._search({"size": 0}) == respuesta


def test_la_portada_sin_eventos_externos_no_tiene_fechas(monkeypatch: pytest.MonkeyPatch) -> None:
    def falso(body: dict[str, Any], es_url: str = "") -> dict[str, Any]:
        if "c" in body.get("aggs", {}):
            return {"aggregations": {"c": {"buckets": []}}}
        return {
            "hits": {"total": {"value": 0}},
            "aggregations": {
                "sensors": {"buckets": []},
                "logins": {"doc_count": 0},
                "logins_ok": {"doc_count": 0},
                "commands": {"doc_count": 0},
                # así contesta Elasticsearch un `stats` sobre cero documentos
                "window": {"count": 0, "min": None, "max": None, "avg": None, "sum": 0.0},
            },
        }

    monkeypatch.setattr(queries, "_search", falso)

    portada = queries.overview()

    assert portada["events"] == 0
    assert (portada["first_event"], portada["last_event"]) == (None, None)


def test_la_salud_sin_eventos_sigue_en_vivo(monkeypatch: pytest.MonkeyPatch) -> None:
    def vacio() -> None:
        raise queries.SinEventosError("sin índices")

    monkeypatch.setattr(queries, "overview", vacio)

    r = TestClient(app).get("/api/health")

    assert r.status_code == 200
    assert r.json() == {"status": "ok", "mode": "live"}


@pytest.mark.usefixtures("como_invitado", "sin_cache")
def test_el_panel_sin_eventos_dice_que_falta(monkeypatch: pytest.MonkeyPatch) -> None:
    def vacio() -> None:
        raise queries.SinEventosError("sin índices")

    monkeypatch.setattr(queries, "snapshot", vacio)

    r = TestClient(app).get("/api/snapshot")

    assert r.status_code == 503
    assert r.json()["detail"] == main.SIN_EVENTOS
