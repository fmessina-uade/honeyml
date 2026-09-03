"""Carga y limpia UWF-ZeekData24, el conjunto de referencia etiquetado con MITRE ATT&CK.

Concatena las particiones parquet semanales, descarta las filas que el propio conjunto marca como
duplicadas y devuelve un DataFrame prolijo. Son registros de conexión de Zeek etiquetados con
label_tactic, que es la variable objetivo del modelo supervisado.
"""

from __future__ import annotations

import glob
from pathlib import Path

import pandas as pd

RAW_DIR = Path("data/raw/uwf_zeekdata24")

# columnas que nunca entran al modelo: identificadores (filtran o no generalizan) y las otras
# columnas de etiqueta
DROP_COLS = [
    "uid",
    "community_id",
    "src_ip_zeek",
    "dest_ip_zeek",
    "ts",
    "datetime",
    "label_technique",
    "label_binary",
    "label_cve",
]


def load_uwf(raw_dir: str | Path = RAW_DIR, drop_duplicates: bool = True) -> pd.DataFrame:
    """Lee todos los parquet de UWF-ZeekData24 en un solo DataFrame.

    Parámetros
    ----------
    raw_dir : el directorio con las particiones parquet semanales.
    drop_duplicates : si es True, descarta las filas que el conjunto marca como Duplicate en
        label_binary.
    """
    files = sorted(glob.glob(str(Path(raw_dir) / "*" / "*.parquet")))
    if not files:
        raise SystemExit(f"No hay parquet en {raw_dir}. Descargá UWF-ZeekData24 primero.")
    df = pd.concat((pd.read_parquet(f) for f in files), ignore_index=True)

    if drop_duplicates and "label_binary" in df.columns:
        df = df[df["label_binary"] != "Duplicate"].reset_index(drop=True)
    return df


def features_target(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Parte el DataFrame en las características del modelo (X) y el objetivo (y = label_tactic)."""
    y = df["label_tactic"]
    x = df.drop(columns=[c for c in [*DROP_COLS, "label_tactic"] if c in df.columns])
    return x, y


if __name__ == "__main__":
    df = load_uwf()
    print(f"Filas: {len(df):,}  |  columnas: {df.shape[1]}")
    print("\nDistribución de clases (label_tactic):")
    print(df["label_tactic"].value_counts().to_string())
