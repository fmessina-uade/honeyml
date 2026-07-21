"""Load and clean UWF-ZeekData24, the MITRE ATT&CK labeled benchmark for the supervised model.

Concatenates the weekly parquet partitions, drops the rows the dataset itself flags as duplicates,
and returns a tidy DataFrame. Zeek connection records labeled with label_tactic (the target).
"""

from __future__ import annotations

import glob
from pathlib import Path

import pandas as pd

RAW_DIR = Path("data/raw/uwf_zeekdata24")

# columns we never feed the model: identifiers (leak / don't generalize) and the other label columns
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
    """Read every UWF-ZeekData24 parquet into one DataFrame.

    Parameters
    ----------
    raw_dir : dir holding the weekly parquet partitions.
    drop_duplicates : if True, drop the rows the dataset flags as Duplicate (in label_binary).
    """
    files = sorted(glob.glob(str(Path(raw_dir) / "*" / "*.parquet")))
    if not files:
        raise SystemExit(f"No hay parquet en {raw_dir}. Descargá UWF-ZeekData24 primero.")
    df = pd.concat((pd.read_parquet(f) for f in files), ignore_index=True)

    if drop_duplicates and "label_binary" in df.columns:
        df = df[df["label_binary"] != "Duplicate"].reset_index(drop=True)
    return df


def features_target(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Split the frame into the model features (X) and the target (y = label_tactic)."""
    y = df["label_tactic"]
    x = df.drop(columns=[c for c in [*DROP_COLS, "label_tactic"] if c in df.columns])
    return x, y


if __name__ == "__main__":
    df = load_uwf()
    print(f"Filas: {len(df):,}  |  columnas: {df.shape[1]}")
    print("\nDistribución de clases (label_tactic):")
    print(df["label_tactic"].value_counts().to_string())
