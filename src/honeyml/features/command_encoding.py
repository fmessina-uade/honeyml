"""Codificación TF-IDF de los comandos que los atacantes ejecutan en Cowrie.

Cada dirección de origen se vuelve un "documento" con todos sus comandos concatenados, y TF-IDF lo
convierte en un vector numérico que captura qué herramientas y qué patrones usa cada atacante.
Complementa las banderas binarias de build_features con una representación densa para el modelo.

Uso:
    python -m src.honeyml.features.command_encoding
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from scipy.sparse import csr_matrix
from sklearn.feature_extraction.text import TfidfVectorizer

PARQUET_IN = Path("data/processed/honeypot_events.parquet")
MATRIX_OUT = Path("data/processed/command_tfidf.parquet")
LOCAL_IP = "127.0.0.1"


def _tokenizer(text: str) -> list[str]:
    """Tokeniza comandos: parte por espacios y símbolos, y conserva flags y rutas cortas."""
    tokens = []
    for raw in text.replace("|", " ").replace(";", " ").replace("&", " ").split():
        tok = raw.strip("\"'`()").lower()
        if tok and not tok.isdigit():
            tokens.append(tok)
    return tokens


def commands_by_ip(df: pd.DataFrame) -> pd.Series:
    """Un documento de comandos concatenados por dirección de origen.

    Solo command-input, que son los comandos efectivamente tipeados. command-failed trae el texto
    "Command not found: ..." que ensuciaría el vocabulario.
    """
    mask = df["event.action"].eq("command-input")
    cmds = df.loc[mask & (df["source.ip"] != LOCAL_IP), ["source.ip", "process.command_line"]]
    cmds = cmds.dropna()
    return cmds.groupby("source.ip")["process.command_line"].apply(lambda s: " ".join(s))


def encode(docs: pd.Series, max_features: int = 200) -> tuple[csr_matrix, TfidfVectorizer]:
    vectorizer = TfidfVectorizer(
        tokenizer=_tokenizer,
        token_pattern=None,
        max_features=max_features,
        min_df=2,  # drop terms that show up in a single IP (noise)
    )
    matrix = vectorizer.fit_transform(docs)
    return matrix, vectorizer


def main() -> None:
    if not PARQUET_IN.exists():
        raise SystemExit(f"Falta {PARQUET_IN}. Extraé primero con es_loader (ES levantado).")
    df = pd.read_parquet(PARQUET_IN)
    docs = commands_by_ip(df)
    if docs.empty:
        raise SystemExit("No hay comandos para codificar.")

    matrix, vectorizer = encode(docs)
    terms = vectorizer.get_feature_names_out()
    print(f"IPs con comandos:    {len(docs):,}")
    print(f"Vocabulario TF-IDF:  {len(terms)} términos")

    # los términos más informativos: mayor peso TF-IDF promedio sobre todo el corpus
    weights = pd.Series(matrix.mean(axis=0).A1, index=terms).sort_values(ascending=False)
    print("\nTop 20 términos por peso TF-IDF medio:")
    for term, w in weights.head(20).items():
        print(f"  {w:.4f}  {term}")

    out = pd.DataFrame(matrix.toarray(), index=docs.index, columns=[f"tfidf_{t}" for t in terms])
    MATRIX_OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(MATRIX_OUT)
    print(f"\nMatriz TF-IDF: {out.shape[0]} IPs x {out.shape[1]} términos -> {MATRIX_OUT}")


if __name__ == "__main__":
    main()
