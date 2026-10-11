"""El instante tope para recontar un corte: que llegue a todas las consultas y se pueda quitar."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from honeyml import redes
from honeyml.api import queries

TOPE = {"range": {"@timestamp": {"lte": "2026-10-03T22:00:59Z"}}}


@pytest.fixture
def con_tope() -> Iterator[None]:
    queries.fijar_tope("2026-10-03T22:00:59Z")
    try:
        yield
    finally:
        queries.fijar_tope(None)


@pytest.mark.usefixtures("con_tope")
def test_el_tope_llega_a_la_base_al_filtro_y_al_detalle_por_protocolo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert queries.NOT_LOCAL["bool"]["filter"] == [TOPE]
    assert queries.NOT_LOCAL["bool"]["must_not"] == redes.TERMINOS
    assert TOPE in queries._filtrado("cowrie")["bool"]["must"]

    pedidos: list[dict[str, Any]] = []

    def falso(body: dict[str, Any], es_url: str = "") -> dict[str, Any]:
        pedidos.append(body)
        return {"aggregations": {"p": {"buckets": []}}}

    monkeypatch.setattr(queries, "_search", falso)
    queries.protocol_detail()
    assert TOPE in pedidos[0]["query"]["bool"]["must"]


def test_sin_tope_las_consultas_quedan_como_siempre() -> None:
    queries.fijar_tope("2026-10-03T22:00:59Z")
    queries.fijar_tope(None)
    assert queries.NOT_LOCAL is redes.EXTERNA
    assert queries._filtrado("cowrie")["bool"]["must"] == [{"term": {"honeypot": "cowrie"}}]
