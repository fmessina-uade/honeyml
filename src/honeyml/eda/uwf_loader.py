"""Carga y limpia UWF-ZeekData24, el conjunto de referencia etiquetado con MITRE ATT&CK.

Concatena las particiones parquet semanales, descarta las filas que el propio conjunto marca como
duplicadas y devuelve un DataFrame prolijo. Son registros de conexión de Zeek etiquetados con
label_tactic, que es la variable objetivo del modelo supervisado.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import sys
from pathlib import Path

import pandas as pd

RAW_DIR = Path("data/raw/uwf_zeekdata24")

# La copia con la que se entrenó y se evaluó el modelo informado: un parquet por semana, con su
# resumen SHA-256. Si la universidad publica una versión nueva, el entrenamiento corre igual pero
# las métricas dejan de ser comparables, y esto es lo que lo avisa.
HUELLAS = {
    "2024-02-25 - 2024-03-03": "4d833656b31d4d360691c2178c5c4d1b3c31f01db12c59f6779a08d55e5f0cc7",
    "2024-03-03 - 2024-03-10": "5a085f2749556f2c711af6f9c2bca9d43b3f19bb43696ef9194869f4ea69eb21",
    "2024-03-10 - 2024-03-17": "47bceaf2dd16aee21bd774513fa4549616c066bbe4a20e42f55378f688d9b414",
    "2024-03-17 - 2024-03-24": "97dda852f7240375ec76afcfc96964b4edcda3516ebc0f45a9cd92ae60319f63",
    "2024-03-24 - 2024-03-31": "f7e557a250502782c60b10b955e6d87724730be519006ce30418511bc5ecf512",
    "2024-10-27 - 2024-11-03": "cadcaf2084ab599d31a530a8cd5f93e010804b9e91ca1e3f8f2631a45ece2575",
    "2024-11-03 - 2024-11-10": "0a61b52c3527e6e2e2a5f277778752d89a8ab2bb03147da5aee5d923055ccb7a",
}

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


def verificar(raw_dir: str | Path = RAW_DIR) -> list[str]:
    """Las diferencias entre la copia local y la de referencia; ninguna si es la misma."""
    diferencias = []
    vistas = set()
    for archivo in sorted(Path(raw_dir).glob("*/*.parquet")):
        semana = archivo.parent.name
        vistas.add(semana)
        with archivo.open("rb") as f:
            resumen = hashlib.file_digest(f, "sha256").hexdigest()
        if semana not in HUELLAS:
            diferencias.append(f"{semana}: no es parte de la copia de referencia")
        elif resumen != HUELLAS[semana]:
            diferencias.append(f"{semana}: el contenido es distinto")
    diferencias += [f"{semana}: falta" for semana in sorted(HUELLAS.keys() - vistas)]
    return diferencias


def load_uwf(raw_dir: str | Path = RAW_DIR, drop_duplicates: bool = True) -> pd.DataFrame:
    """Lee las particiones parquet semanales de `raw_dir` en un solo DataFrame.

    Con `drop_duplicates` se descartan las filas que el propio conjunto marca como Duplicate en
    label_binary.
    """
    files = sorted(glob.glob(str(Path(raw_dir) / "*" / "*.parquet")))
    if not files:
        raise SystemExit(f"No hay parquet en {raw_dir}. Descargá UWF-ZeekData24 primero.")
    diferencias = verificar(raw_dir)
    if diferencias:
        print(
            "Esta copia de UWF-ZeekData24 no es la de referencia, así que las métricas pueden "
            "no coincidir con las de la tarjeta del modelo.",
            *diferencias,
            sep="\n  ",
            file=sys.stderr,
        )
    df = pd.concat((pd.read_parquet(f) for f in files), ignore_index=True)

    if drop_duplicates and "label_binary" in df.columns:
        df = df[df["label_binary"] != "Duplicate"].reset_index(drop=True)
    return df


def features_target(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Parte el DataFrame en las características del modelo (X) y el objetivo (y = label_tactic)."""
    y = df["label_tactic"]
    x = df.drop(columns=[c for c in [*DROP_COLS, "label_tactic"] if c in df.columns])
    return x, y


def main() -> None:
    ap = argparse.ArgumentParser(description="Filas y clases de UWF-ZeekData24.")
    ap.add_argument(
        "--verificar", action="store_true", help="solo compara la copia local con la de referencia"
    )
    if ap.parse_args().verificar:
        diferencias = verificar()
        if diferencias:
            print("La copia local no es la de referencia:", *diferencias, sep="\n  ")
            raise SystemExit(1)
        print(f"La copia local es la de referencia: {len(HUELLAS)} semanas con el mismo SHA-256.")
        return
    df = load_uwf()
    print(f"Filas: {len(df):,}  |  columnas: {df.shape[1]}")
    print("\nDistribución de clases (label_tactic):")
    print(df["label_tactic"].value_counts().to_string())


if __name__ == "__main__":
    main()
