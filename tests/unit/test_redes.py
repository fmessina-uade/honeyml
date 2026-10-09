"""Qué orígenes cuentan como internos, en Elasticsearch y en pandas por igual."""

from __future__ import annotations

import pytest

from honeyml import redes
from honeyml.api import queries


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",
        "127.0.0.11",
        "::1",
        "10.1.2.3",
        "172.17.0.1",
        "172.31.255.254",
        "192.168.1.5",
        "100.64.0.1",
        "169.254.169.254",
        "fd00::1",
        "fe80::1",
    ],
)
def test_loopback_y_redes_privadas_son_internas(ip: str) -> None:
    assert redes.es_interna(ip)


@pytest.mark.parametrize(
    "ip",
    # los rangos de documentación son los atacantes de las pruebas: no pueden caer en el filtro
    [
        "203.0.113.62",
        "198.51.100.77",
        "192.0.2.1",
        "172.32.0.1",
        "8.8.8.8",
        "2001:db8::1",
        "",
        None,
        float("nan"),
        "no es una dirección",
    ],
)
def test_lo_demas_no_es_interno(ip: object) -> None:
    assert not redes.es_interna(ip)


def test_la_mascara_coincide_fila_por_fila_con_la_funcion() -> None:
    pd = pytest.importorskip("pandas")
    origenes = pd.Series(["203.0.113.7", "127.0.0.1", None, "10.0.0.8", "203.0.113.7"])
    assert redes.mascara_externa(origenes).tolist() == [True, False, True, False, True]


def test_las_consultas_del_panel_excluyen_todas_las_redes_internas() -> None:
    excluidas = {t["term"]["source.ip"] for t in queries.NOT_LOCAL["bool"]["must_not"]}
    assert excluidas == set(redes.INTERNAS)
    filtro = queries._filtrado("cowrie")
    assert filtro["bool"]["must_not"] == redes.TERMINOS
