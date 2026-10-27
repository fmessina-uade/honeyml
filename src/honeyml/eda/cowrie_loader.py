"""Carga los registros JSON crudos de Cowrie en un DataFrame de pandas.

Lee los archivos cowrie.json* que escribe el honeypot (un evento JSON por línea) sin necesidad de
tener el Elastic Stack arriba. Es la fuente de verdad para el análisis exploratorio sin conexión.
"""

from __future__ import annotations

import glob
import json
from pathlib import Path
from typing import Any

import pandas as pd

from .. import redes

# Los campos de Cowrie que nos interesan; el resto se descarta para no cargar memoria de más.
FIELDS = [
    "eventid",
    "timestamp",
    "src_ip",
    "src_port",
    "dst_port",
    "session",
    "protocol",
    "username",
    "password",
    "input",
    "url",
    "shasum",
    "duration",
    "sensor",
]


def load_cowrie(
    logs_dir: str | Path = "data/logs/cowrie",
    pattern: str = "cowrie.json*",
    drop_local: bool = True,
) -> pd.DataFrame:
    """Lee los archivos de `logs_dir` que coinciden con `pattern` y los junta en un DataFrame.

    Con `drop_local` se descartan los eventos de direcciones internas (los healthcheck del
    contenedor y las pruebas propias), que no son ataques.
    """
    logs_dir = Path(logs_dir)
    rows: list[dict[str, Any]] = []
    for path in sorted(glob.glob(str(logs_dir / pattern))):
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rows.append({f: obj.get(f) for f in FIELDS})

    df = pd.DataFrame(rows, columns=FIELDS)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
    if drop_local:
        df = df[redes.mascara_externa(df["src_ip"])].reset_index(drop=True)
    return df


if __name__ == "__main__":
    df = load_cowrie()
    print(f"Eventos externos cargados: {len(df):,}")
    print(f"Rango temporal: {df['timestamp'].min()} a {df['timestamp'].max()}")
    print(f"Direcciones únicas: {df['src_ip'].nunique():,}")
    print(df["eventid"].value_counts().head(10))
