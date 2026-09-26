"""Qué eventos vuelve a triar `retriaje`, sin Redis ni Elasticsearch.

Lo que se fija es la lectura del bus: que recorra el stream entero aunque tenga más de una página,
que se quede solo con la categoría pedida y que no decida dos veces el mismo evento.
"""

from __future__ import annotations

from typing import Any

import pytest

from honeyml.agent import retriaje


class _RedisFalso:
    """Un stream en memoria que contesta `xrange` con las mismas reglas que Redis."""

    def __init__(self, mensajes: list[tuple[str, dict[str, str]]]) -> None:
        self.mensajes = mensajes
        self.pedidos = 0

    def xrange(self, stream: str, min: str = "-", count: int | None = None) -> Any:
        self.pedidos += 1
        excluyente = min.startswith("(")
        desde = min.lstrip("(")
        salida = [
            m
            for m in self.mensajes
            if desde == "-" or (m[0] > desde if excluyente else m[0] >= desde)
        ]
        return salida[:count]


def _mensaje(i: int, categoria: str, doc_id: str | None = None) -> tuple[str, dict[str, str]]:
    return (f"{i:010d}-0", {"doc_id": doc_id or f"doc-{i}", "category": categoria})


def test_recorre_el_stream_entero_de_a_paginas(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(retriaje, "PAGINA", 3)
    r = _RedisFalso([_mensaje(i, "authentication") for i in range(8)])

    eventos = retriaje.eventos_de(r, "s", "authentication")  # type: ignore[arg-type]
    assert [e.doc_id for e in eventos] == [f"doc-{i}" for i in range(8)]
    assert r.pedidos == 3


def test_se_queda_solo_con_la_categoria_pedida() -> None:
    r = _RedisFalso([_mensaje(1, "authentication"), _mensaje(2, "process")])
    eventos = retriaje.eventos_de(r, "s", "authentication")  # type: ignore[arg-type]
    assert [e.doc_id for e in eventos] == ["doc-1"]


def test_un_evento_publicado_dos_veces_se_decide_una() -> None:
    """Una relectura puede haberlo publicado de nuevo; reescribirlo dos veces no aporta nada."""
    r = _RedisFalso([_mensaje(1, "authentication", "x"), _mensaje(2, "authentication", "x")])
    eventos = retriaje.eventos_de(r, "s", "authentication")  # type: ignore[arg-type]
    assert [e.entry_id for e in eventos] == ["0000000001-0"]
