"""Carga de los logs crudos JSON de Cowrie hacia un DataFrame de pandas.

Lee los archivos cowrie.json* capturados por el honeypot (un evento JSON por línea) sin depender
de que el stack de Elasticsearch esté corriendo. Es la fuente ground-truth para el EDA offline.
"""

from __future__ import annotations

import glob
import json
from pathlib import Path
from typing import Any

import pandas as pd

# Campos relevantes de Cowrie para el análisis (el resto se descarta para no inflar memoria).
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
    """Lee todos los cowrie.json* de un directorio a un DataFrame.

    Parameters
    ----------
    logs_dir : directorio con los archivos cowrie.json*.
    pattern : glob de archivos a leer.
    drop_local : si True, descarta eventos de 127.0.0.1 (healthchecks del contenedor).
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
        df = df[df["src_ip"] != "127.0.0.1"].reset_index(drop=True)
    return df


if __name__ == "__main__":
    df = load_cowrie()
    print(f"Eventos externos cargados: {len(df):,}")
    print(f"Rango temporal: {df['timestamp'].min()}  ->  {df['timestamp'].max()}")
    print(f"IPs únicas: {df['src_ip'].nunique():,}")
    print(df["eventid"].value_counts().head(10))
