"""TF-IDF encoding of the commands attackers run in Cowrie.

Each source IP becomes a "document" with all the commands it ran concatenated; TF-IDF turns that
into a numeric vector that captures which tools and patterns each attacker uses. Complements the
binary flags from build_features with a dense representation for the model.

Usage:
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
    """Tokenize shell commands: split on spaces/symbols, keep flags and short paths."""
    tokens = []
    for raw in text.replace("|", " ").replace(";", " ").replace("&", " ").split():
        tok = raw.strip("\"'`()").lower()
        if tok and not tok.isdigit():
            tokens.append(tok)
    return tokens


def commands_by_ip(df: pd.DataFrame) -> pd.Series:
    """One document of concatenated commands per source IP.

    Only command-input (commands actually typed); command-failed carries the
    "Command not found: ..." text that would pollute the vocabulary.
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

    # most informative terms (highest mean TF-IDF weight across the corpus)
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
