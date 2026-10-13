"""Que los conteos del panel salgan exactos y no estimados, sin Elasticsearch."""

from __future__ import annotations

from typing import Any

import pytest

from honeyml.api import queries


def _paginas(cantidades: list[int]) -> tuple[list[dict[str, Any]], Any]:
    """Un _search falso que contesta la agregación compuesta con páginas de esos tamaños."""
    pedidos: list[dict[str, Any]] = []
    restantes = list(cantidades)

    def falso(body: dict[str, Any], es_url: str = "") -> dict[str, Any]:
        pedidos.append(body)
        if "c" not in body.get("aggs", {}):
            return {
                "hits": {"total": {"value": 0}},
                "aggregations": {
                    "sensors": {"buckets": []},
                    "logins": {"doc_count": 0},
                    "logins_ok": {"doc_count": 0},
                    "commands": {"doc_count": 0},
                    "window": {"min_as_string": None, "max_as_string": None},
                },
            }
        n = restantes.pop(0)
        hechas = len(pedidos)
        agg: dict[str, Any] = {"buckets": [{"key": {"ip": f"x{i}"}} for i in range(n)]}
        if n:
            agg["after_key"] = {"ip": f"p{hechas}"}
        return {"aggregations": {"c": agg}}

    return pedidos, falso


def test_recorre_todas_las_paginas_y_suma(monkeypatch: pytest.MonkeyPatch) -> None:
    pedidos, falso = _paginas([10_000, 10_000, 7_592])
    monkeypatch.setattr(queries, "_search", falso)

    assert queries._direcciones_exactas(queries.NOT_LOCAL) == 27_592
    assert len(pedidos) == 3
    # cada página arranca donde terminó la anterior
    assert "after" not in pedidos[0]["aggs"]["c"]["composite"]
    assert pedidos[1]["aggs"]["c"]["composite"]["after"] == {"ip": "p1"}


def test_una_pagina_justa_pide_una_mas_y_corta(monkeypatch: pytest.MonkeyPatch) -> None:
    pedidos, falso = _paginas([10_000, 0])
    monkeypatch.setattr(queries, "_search", falso)

    assert queries._direcciones_exactas(queries.NOT_LOCAL) == 10_000
    assert len(pedidos) == 2


def test_la_portada_usa_el_conteo_exacto(monkeypatch: pytest.MonkeyPatch) -> None:
    _, falso = _paginas([3])
    monkeypatch.setattr(queries, "_search", falso)

    assert queries.overview()["unique_ips"] == 3


def test_los_rankings_piden_un_recorte_amplio(monkeypatch: pytest.MonkeyPatch) -> None:
    pedidos: list[dict[str, Any]] = []

    def falso(body: dict[str, Any], es_url: str = "") -> dict[str, Any]:
        pedidos.append(body)
        return {"aggregations": {"t": {"buckets": [{"key": "root", "doc_count": 5}]}}}

    monkeypatch.setattr(queries, "_search", falso)

    assert queries.top_credentials(size=12)["users"] == [{"key": "root", "count": 5}]
    for body in pedidos:
        terms = body["aggs"]["t"]["terms"]
        assert terms["shard_size"] >= 2_000
        # Se piden seis de más: después se descartan las que parecen una dirección.
        assert terms["size"] == 18


def test_las_credenciales_con_forma_de_direccion_no_salen(monkeypatch: pytest.MonkeyPatch) -> None:
    """Una de las más probadas es un fragmento de la dirección del servidor: no tiene que aparecer
    en el ranking que devuelve la API."""

    def falso(body: dict[str, Any], es_url: str = "") -> dict[str, Any]:
        return {
            "aggregations": {
                "t": {
                    "buckets": [
                        {"key": "root", "doc_count": 9},
                        {"key": "203.0.113", "doc_count": 7},
                        {"key": "admin", "doc_count": 5},
                    ]
                }
            }
        }

    monkeypatch.setattr(queries, "_search", falso)
    usuarios = queries.top_credentials(size=2)["users"]
    claves = [c["key"] for c in usuarios]
    assert claves == ["root", "admin"]
    assert "203.0.113" not in claves


def test_las_direcciones_por_grupo_usan_el_umbral_maximo() -> None:
    assert queries._distintas("source.ip") == {
        "cardinality": {"field": "source.ip", "precision_threshold": 40_000}
    }
