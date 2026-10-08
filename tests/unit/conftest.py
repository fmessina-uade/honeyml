"""Una sesión de prueba para las pruebas de rutas que no son sobre el ingreso.

Lo que hace cada ruta se prueba sin pasar por el ingreso ni por Elasticsearch: el ingreso y los
roles se prueban aparte, en `test_acceso.py`. La auditoría queda en una lista, para poder mirar qué
se anotó.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from honeyml.api import acceso, auditoria
from honeyml.api.main import app


def _sesion_de(rol: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[list[dict[str, Any]]]:
    anotado: list[dict[str, Any]] = []

    def registrar(usuario: str, rol: str | None, accion: str, **resto: Any) -> None:
        anotado.append({"usuario": usuario, "rol": rol, "accion": accion, **resto})

    monkeypatch.setattr(auditoria, "registrar", registrar)
    app.dependency_overrides[acceso.sesion_actual] = lambda: acceso.Sesion("prueba", rol)
    app.dependency_overrides[acceso.proteger] = lambda: None
    yield anotado
    app.dependency_overrides.clear()


@pytest.fixture
def como_analista(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[dict[str, Any]]]:
    yield from _sesion_de("analista", monkeypatch)


@pytest.fixture
def como_invitado(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[dict[str, Any]]]:
    yield from _sesion_de("invitado", monkeypatch)
