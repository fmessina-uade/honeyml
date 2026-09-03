"""Carga eventos normalizados a ECS desde Elasticsearch a un DataFrame de pandas.

Usa la API de scroll sobre urllib, sin el cliente de elasticsearch, para no quedar atados a su
versión, y aplana los campos anidados de ECS en columnas sueltas listas para el análisis.

Corrido como módulo, escribe la tabla consolidada en disco. Ese archivo es el primer eslabón de la
cadena de artefactos derivados: lo leen el análisis exploratorio, las características por dirección
y la codificación de comandos, así que tiene que poder reproducirse con un comando y no desde una
sesión improvisada.

Uso:
    python -m honeyml.eda.es_loader
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Any

import pandas as pd

OUT_FILE = Path("data/processed/honeypot_events.parquet")

# Los campos ECS que se traen por evento. Se piden explícitos para no arrastrar cargas pesadas.
DEFAULT_FIELDS = [
    "@timestamp",
    "honeypot",
    "observer.vendor",
    "event.category",
    "event.action",
    "event.outcome",
    "event.dataset",
    "network.protocol",
    "network.transport",
    "source.ip",
    "source.port",
    "destination.port",
    "user.name",
    "process.command_line",
    "cowrie.session",
    "cowrie.password",
    "event.duration",
]


def _post(url: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
    req = urllib.request.Request(
        f"{url}{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        result: dict[str, Any] = json.load(resp)
        return result


def _first(value: Any) -> Any:
    """ECS admite arreglos (event.category=[network,authentication]); se toma el primer valor."""
    if isinstance(value, list):
        return value[0] if value else None
    return value


def load_events(
    es_url: str = "http://localhost:9200",
    index: str = "honeypot-*",
    fields: list[str] | None = None,
    page_size: int = 5000,
    max_docs: int | None = None,
) -> pd.DataFrame:
    """Trae todos los eventos del índice a un DataFrame con las columnas ECS aplanadas.

    Parámetros
    ----------
    es_url : URL base de Elasticsearch.
    index : patrón de índice (honeypot-*, honeypot-cowrie-*, ...).
    fields : campos ECS a traer; si no se pasan, DEFAULT_FIELDS.
    page_size : tamaño de página del scroll.
    max_docs : tope opcional de documentos, cómodo para pruebas rápidas.
    """
    url = es_url.rstrip("/")
    fields = fields or DEFAULT_FIELDS

    body = {"size": page_size, "_source": fields, "query": {"match_all": {}}}
    res = _post(url, f"/{index}/_search?scroll=2m", body)
    scroll_id = res.get("_scroll_id")
    rows: list[dict[str, Any]] = []

    while True:
        hits = res["hits"]["hits"]
        if not hits:
            break
        for h in hits:
            src = h["_source"]
            row = {}
            for f in fields:
                # recorre la ruta con puntos (event.category -> src["event"]["category"])
                node = src
                for part in f.split("."):
                    if isinstance(node, dict):
                        node = node.get(part)
                    else:
                        node = None
                        break
                row[f] = _first(node)
            rows.append(row)
        if max_docs and len(rows) >= max_docs:
            rows = rows[:max_docs]
            break
        res = _post(url, "/_search/scroll", {"scroll": "2m", "scroll_id": scroll_id})
        scroll_id = res.get("_scroll_id")

    # libera el contexto del scroll
    if scroll_id:
        try:
            req = urllib.request.Request(
                f"{url}/_search/scroll",
                data=json.dumps({"scroll_id": scroll_id}).encode(),
                headers={"Content-Type": "application/json"},
                method="DELETE",
            )
            urllib.request.urlopen(req, timeout=30)
        except Exception:
            pass

    df = pd.DataFrame(rows, columns=fields)
    if "@timestamp" in df.columns:
        df["@timestamp"] = pd.to_datetime(df["@timestamp"], errors="coerce", utc=True)
    return df


def main() -> None:
    df = load_events()
    if df.empty:
        raise SystemExit("No se recuperó ningún evento. ¿Está levantado Elasticsearch?")

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT_FILE, index=False)

    size_mb = OUT_FILE.stat().st_size / 1024 / 1024
    print(f"Telemetría consolidada -> {OUT_FILE} ({size_mb:.0f} MB)")
    print(f"  {len(df):,} eventos, {len(df.columns)} columnas".replace(",", "."))
    if "@timestamp" in df.columns:
        print(f"  ventana {df['@timestamp'].min():%Y-%m-%d} a {df['@timestamp'].max():%Y-%m-%d}")
    if "honeypot" in df.columns:
        for sensor, n in df["honeypot"].value_counts().items():
            print(f"  {sensor}: {n:,}".replace(",", "."))


if __name__ == "__main__":
    main()
