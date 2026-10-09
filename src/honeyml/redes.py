"""Las direcciones de origen que no son de terceros.

Desde loopback llegan los healthcheck de los contenedores, y a una red privada solo se llega desde
el anfitrión o desde otro contenedor, así que lo que viene de ahí son pruebas propias. Ningún
atacante entra por ese camino: todo eso sale de las cifras de actividad externa. La lista es una
sola para Elasticsearch, que acepta rangos en un campo `ip`, y para lo que se calcula en pandas.

Los rangos de documentación (192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24) no están, a propósito:
son los que usan las pruebas como si fueran atacantes.
"""

from __future__ import annotations

import ipaddress
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pandas as pd

LOOPBACK = ("127.0.0.0/8", "::1/128")
PRIVADAS = (
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "100.64.0.0/10",
    "169.254.0.0/16",
    "fc00::/7",
    "fe80::/10",
)
INTERNAS = LOOPBACK + PRIVADAS

_REDES = tuple(ipaddress.ip_network(r) for r in INTERNAS)

# para el must_not de una consulta
TERMINOS: list[dict[str, Any]] = [{"term": {"source.ip": r}} for r in INTERNAS]
EXTERNA: dict[str, Any] = {"bool": {"must_not": TERMINOS}}


def es_interna(ip: object) -> bool:
    """Un origen vacío o que no es una dirección no cuenta como interno: no se filtra por esto."""
    if not isinstance(ip, str):
        return False
    try:
        direccion = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(direccion in red for red in _REDES)


def mascara_externa(origenes: pd.Series) -> pd.Series:
    """Verdadero en las filas que no vienen de una dirección interna.

    Clasifica cada dirección distinta una sola vez: son decenas de miles contra millones de filas.
    """
    internas = [ip for ip in origenes.dropna().unique() if es_interna(ip)]
    return ~origenes.isin(internas)
