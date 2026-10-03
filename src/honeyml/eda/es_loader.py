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
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

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

# Los campos numéricos; el resto es texto, salvo la marca de tiempo.
NUMERICOS = {"source.port", "destination.port", "event.duration"}

# Cuántas filas se juntan antes de pasarlas al formato columnar. Como filas sueltas de Python, cada
# evento repite sus cadenas y pesa cientos de bytes; en columnas, el corpus entero entra holgado. El
# tramo acota lo que vive en el formato caro.
TRAMO = 250_000


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


def _valor(src: dict[str, Any], campo: str) -> Any:
    """Recorre la ruta con puntos: event.category se lee de src["event"]["category"]."""
    node: Any = src
    for part in campo.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return _first(node)


def _esquema(fields: list[str]) -> pa.Schema:
    tipos = []
    for f in fields:
        if f == "@timestamp":
            tipos.append(pa.field(f, pa.timestamp("us", tz="UTC")))
        elif f in NUMERICOS:
            tipos.append(pa.field(f, pa.float64()))
        else:
            tipos.append(pa.field(f, pa.large_string()))
    return pa.schema(tipos)


def _a_tabla(columnas: dict[str, list[Any]], esquema: pa.Schema) -> pa.Table:
    arreglos = []
    for campo in esquema:
        valores = columnas[campo.name]
        if campo.name == "@timestamp":
            marcas = pd.to_datetime(pd.Series(valores, dtype=object), errors="coerce", utc=True)
            arreglos.append(pa.array(marcas.dt.as_unit("us"), type=campo.type))
        elif campo.name in NUMERICOS:
            arreglos.append(
                pa.array([float(v) if v is not None else None for v in valores], type=campo.type)
            )
        else:
            arreglos.append(
                pa.array([str(v) if v is not None else None for v in valores], type=campo.type)
            )
    return pa.Table.from_arrays(arreglos, schema=esquema)


def _tramos(
    url: str, index: str, fields: list[str], page_size: int, max_docs: int | None
) -> Iterator[pa.Table]:
    """Recorre el índice con scroll y entrega la telemetría en tablas de a TRAMO filas."""
    esquema = _esquema(fields)
    body = {"size": page_size, "_source": fields, "query": {"match_all": {}}}
    res = _post(url, f"/{index}/_search?scroll=2m", body)
    scroll_id = res.get("_scroll_id")
    columnas: dict[str, list[Any]] = {f: [] for f in fields}
    leidas = 0
    try:
        while True:
            hits = res["hits"]["hits"]
            if not hits:
                break
            for h in hits:
                if max_docs and leidas >= max_docs:
                    break
                for f in fields:
                    columnas[f].append(_valor(h["_source"], f))
                leidas += 1
            if len(columnas[fields[0]]) >= TRAMO:
                yield _a_tabla(columnas, esquema)
                columnas = {f: [] for f in fields}
            if max_docs and leidas >= max_docs:
                break
            res = _post(url, "/_search/scroll", {"scroll": "2m", "scroll_id": scroll_id})
            scroll_id = res.get("_scroll_id")
        if columnas[fields[0]]:
            yield _a_tabla(columnas, esquema)
    finally:
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


def load_table(
    es_url: str = "http://localhost:9200",
    index: str = "honeypot-*",
    fields: list[str] | None = None,
    page_size: int = 5000,
    max_docs: int | None = None,
) -> pa.Table:
    """Trae todos los eventos del índice a una tabla columnar, con los campos ECS aplanados."""
    fields = fields or DEFAULT_FIELDS
    tablas = list(_tramos(es_url.rstrip("/"), index, fields, page_size, max_docs))
    if not tablas:
        return _esquema(fields).empty_table()
    return pa.concat_tables(tablas)


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
    df: pd.DataFrame = load_table(es_url, index, fields, page_size, max_docs).to_pandas()
    return df


def main() -> None:
    tabla = load_table()
    if tabla.num_rows == 0:
        raise SystemExit("No se recuperó ningún evento. ¿Está levantado Elasticsearch?")

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(tabla, OUT_FILE)

    size_mb = OUT_FILE.stat().st_size / 1024 / 1024
    print(f"Telemetría consolidada -> {OUT_FILE} ({size_mb:.0f} MB)")
    print(f"  {tabla.num_rows:,} eventos, {tabla.num_columns} columnas".replace(",", "."))
    marcas = tabla.column("@timestamp").to_pandas()
    print(f"  ventana {marcas.min():%Y-%m-%d} a {marcas.max():%Y-%m-%d}")
    for sensor, n in tabla.column("honeypot").to_pandas().value_counts().items():
        print(f"  {sensor}: {n:,}".replace(",", "."))


if __name__ == "__main__":
    main()
