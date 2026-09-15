"""La recolección de contraseñas del índice, que tiene que aguantar el crecimiento del corpus.

Un `terms` de una sola consulta no alcanza: Elasticsearch no crea más de 65.536 cubos en un
agregado y a partir de ahí devuelve 400, con lo que `make refresh` corta entero en este paso, y
las contraseñas distintas ya superan ese techo.

Lo que se fija acá es que la recolección pagine de verdad, porque es lo único que la vuelve inmune
al crecimiento. Un `terms` de una sola consulta vuelve a pasar las dos primeras pruebas si alguien
lo reintroduce, así que la tercera mira que el cursor viaje.
"""

from __future__ import annotations

from typing import Any

import pytest

from honeyml.education import password_index


def _pagina(claves: list[tuple[str, int]], after: str | None) -> dict[str, Any]:
    """Una respuesta del agregado compuesto con la forma que devuelve Elasticsearch."""
    cubos = [{"key": {"clave": k}, "doc_count": n} for k, n in claves]
    salida: dict[str, Any] = {"buckets": cubos}
    if after is not None:
        salida["after_key"] = {"clave": after}
    return salida


@pytest.fixture
def paginado(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any] | None]:
    """Tres páginas encadenadas, y el registro de los cursores que se pidieron."""
    pedidos: list[dict[str, Any] | None] = []
    respuestas = [
        _pagina([("123456", 400), ("admin", 300)], after="admin"),
        _pagina([("root", 200), ("toor", 100)], after="toor"),
        _pagina([("qwerty", 50)], after=None),
    ]

    def falsa(es_url: str, despues: dict[str, Any] | None) -> dict[str, Any]:
        pedidos.append(despues)
        return respuestas[len(pedidos) - 1]

    monkeypatch.setattr(password_index, "_pagina", falsa)
    return pedidos


def test_junta_todas_las_paginas(paginado: list[dict[str, Any] | None]) -> None:
    """Las cinco contraseñas salen, no solo las de la primera página."""
    assert password_index.fetch_passwords() == [
        ("123456", 400),
        ("admin", 300),
        ("root", 200),
        ("toor", 100),
        ("qwerty", 50),
    ]


def test_corta_cuando_no_hay_after_key(paginado: list[dict[str, Any] | None]) -> None:
    """La página sin `after_key` es la última: no se pide una cuarta."""
    password_index.fetch_passwords()
    assert len(paginado) == 3


def test_arrastra_el_cursor(paginado: list[dict[str, Any] | None]) -> None:
    """Cada página pide desde donde terminó la anterior.

    Sin esto la paginación giraría sobre la primera página para siempre, o traería duplicados.
    """
    password_index.fetch_passwords()
    assert paginado == [None, {"clave": "admin"}, {"clave": "toor"}]


def test_el_tope_de_paginas_frena(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un proveedor que nunca deja de mandar `after_key` no cuelga el proceso."""
    monkeypatch.setattr(password_index, "MAX_PAGINAS", 4)
    monkeypatch.setattr(
        password_index,
        "_pagina",
        lambda es_url, despues: _pagina([("x", 1)], after="x"),
    )
    assert len(password_index.fetch_passwords()) == 4


def test_agrupa_por_prefijo_del_resumen(paginado: list[dict[str, Any] | None]) -> None:
    """El índice publicado guarda el resto del hash, nunca la contraseña.

    Es la propiedad de la que depende el diseño de privacidad entero, así que va fijada: si alguien
    guardara el texto plano por comodidad, esta prueba lo frena.
    """
    indice = password_index.build()
    assert indice["distinct"] == 5
    assert indice["attempts"] == 1050
    for prefijo, entradas in indice["buckets"].items():
        assert len(prefijo) == password_index.PREFIX_LEN
        for resto, _ in entradas:
            assert len(resto) == 64 - password_index.PREFIX_LEN
    plano = str(indice["buckets"])
    assert "123456" not in plano
    assert "qwerty" not in plano
