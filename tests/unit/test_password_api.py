"""El resumen del índice de contraseñas que usa el panel, sin el índice real."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from honeyml.api.main import app
from honeyml.education import password_index


def test_el_resumen_da_las_cifras_y_ningun_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    indice = {"prefix_len": 5, "distinct": 3, "attempts": 10, "buckets": {"abcde": [["f0", 7]]}}
    monkeypatch.setattr(password_index, "load", lambda: indice)

    r = TestClient(app).get("/api/password-check/resumen")

    assert r.status_code == 200
    assert r.json() == {"distintas": 3, "intentos": 10}


def test_sin_indice_el_resumen_avisa_como_generarlo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(password_index, "load", lambda: None)

    r = TestClient(app).get("/api/password-check/resumen")

    assert r.status_code == 503
    assert "make passwords" in r.json()["detail"]
