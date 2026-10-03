"""La tabla consolidada que arma `es_loader`, sin Elasticsearch.

Se fija que el armado por tramos dé la misma tabla que daría juntar todo de una vez: mismas filas,
mismo orden, el esquema de siempre y los casos que trae ECS (arreglos, campos ausentes, puertos que
llegan como texto).
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import pyarrow as pa
import pytest

from honeyml.eda import es_loader

EVENTOS = [
    {
        "@timestamp": "2026-09-01T10:00:00.123Z",
        "honeypot": "cowrie",
        "event": {"category": ["authentication", "network"], "action": "login"},
        "source": {"ip": "203.0.113.5", "port": 51000},
        "destination": {"port": 2222},
        "user": {"name": "root"},
    },
    {
        "@timestamp": "2026-09-01T10:00:01Z",
        "honeypot": "dionaea",
        "network": {"protocol": "smbd"},
        "source": {"ip": "198.51.100.7", "port": "445"},
        "event": {"duration": 1.5},
    },
    {"@timestamp": "2026-09-01T10:00:02Z", "honeypot": "cowrie", "event": {"category": []}},
]


@pytest.fixture
def scroll(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Un scroll falso que entrega los eventos de a dos y registra lo que se le pidió."""
    pedidos: list[dict[str, Any]] = []
    paginas = [EVENTOS[0:2], EVENTOS[2:3], []]

    def falso(url: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
        pedidos.append({"path": path, "body": body})
        hits = [{"_source": e} for e in paginas.pop(0)]
        return {"_scroll_id": "s1", "hits": {"hits": hits}}

    monkeypatch.setattr(es_loader, "_post", falso)
    monkeypatch.setattr(es_loader.urllib.request, "urlopen", lambda *a, **k: None)
    monkeypatch.setattr(es_loader, "TRAMO", 2)
    return pedidos


def test_la_tabla_tiene_el_esquema_de_siempre(scroll: list[dict[str, Any]]) -> None:
    tabla = es_loader.load_table()

    assert tabla.num_rows == 3
    assert tabla.schema.field("@timestamp").type == pa.timestamp("us", tz="UTC")
    assert tabla.schema.field("source.port").type == pa.float64()
    assert tabla.schema.field("user.name").type == pa.large_string()
    assert tabla.column_names == es_loader.DEFAULT_FIELDS


def test_los_valores_salen_aplanados_y_en_orden(scroll: list[dict[str, Any]]) -> None:
    df = es_loader.load_events()

    assert list(df["honeypot"]) == ["cowrie", "dionaea", "cowrie"]
    # de un arreglo se toma el primer valor, y uno vacío queda como faltante
    assert df.loc[0, "event.category"] == "authentication"
    assert pd.isna(df.loc[2, "event.category"])
    # un puerto que llega como texto queda numérico, igual que el resto
    assert df["source.port"].tolist()[:2] == [51000.0, 445.0]
    assert df.loc[1, "event.duration"] == 1.5
    assert df.loc[0, "@timestamp"].microsecond == 123000
    assert str(df["@timestamp"].dt.tz) == "UTC"


def test_el_tope_de_documentos_corta_a_tiempo(scroll: list[dict[str, Any]]) -> None:
    assert es_loader.load_table(max_docs=1).num_rows == 1
