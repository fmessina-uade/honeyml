"""Supervised feature selection on UWF-ZeekData24 for the MITRE tactic classifier.

Anti-leakage by design: split first (stratified), then everything (imputation, encoding, the model)
is fit on the train split only, inside an sklearn Pipeline. Ranks the Zeek connection features by
random-forest importance and prints a quick classification report on the held-out test set.

Usage:
    python -m src.honeyml.features.uwf_selection
"""

from __future__ import annotations

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from ..eda.uwf_loader import features_target, load_uwf

NUMERIC = [
    "duration",
    "missed_bytes",
    "orig_bytes",
    "orig_ip_bytes",
    "orig_pkts",
    "resp_bytes",
    "resp_ip_bytes",
    "resp_pkts",
    "src_port_zeek",
    "dest_port_zeek",
    "local_orig",
    "local_resp",
]
CATEGORICAL = ["proto", "conn_state", "service"]


def build_pipeline() -> Pipeline:
    """ColumnTransformer + RandomForest. All state is fit on train only when .fit() runs."""
    prep = ColumnTransformer(
        [
            ("num", SimpleImputer(strategy="constant", fill_value=0), NUMERIC),
            ("cat", OneHotEncoder(handle_unknown="ignore", min_frequency=50), CATEGORICAL),
        ]
    )
    clf = RandomForestClassifier(
        n_estimators=120,
        max_depth=None,
        max_samples=0.3,  # bootstrap subsample keeps the fit tractable on ~1.9M rows
        class_weight="balanced_subsample",  # the classes are wildly imbalanced (none 50% vs 0.03%)
        n_jobs=-1,
        random_state=42,
    )
    return Pipeline([("prep", prep), ("clf", clf)])


def main() -> None:
    df = load_uwf()
    x, y = features_target(df)
    # keep only the columns we model; bools become ints for the imputer
    x = x[NUMERIC + CATEGORICAL].copy()
    for c in ("local_orig", "local_resp"):
        x[c] = x[c].astype(int)

    # split BEFORE fitting anything (no leakage)
    x_tr, x_te, y_tr, y_te = train_test_split(x, y, test_size=0.25, stratify=y, random_state=42)
    print(f"Train: {len(x_tr):,}  |  Test: {len(x_te):,}  |  clases: {y.nunique()}")

    pipe = build_pipeline()
    pipe.fit(x_tr, y_tr)  # fit on train only

    # feature importances mapped back to names
    prep = pipe.named_steps["prep"]
    names = prep.get_feature_names_out()
    importances = pipe.named_steps["clf"].feature_importances_
    ranking = pd.Series(importances, index=names).sort_values(ascending=False)

    print("\nTop 20 features por importancia (Random Forest):")
    for name, imp in ranking.head(20).items():
        print(f"  {imp:.4f}  {name}")

    print("\nReporte de clasificación (test held-out):")
    print(classification_report(y_te, pipe.predict(x_te), zero_division=0))

    ranking.to_frame("importance").to_parquet("data/processed/uwf_feature_ranking.parquet")
    print("-> ranking: data/processed/uwf_feature_ranking.parquet")


if __name__ == "__main__":
    main()
