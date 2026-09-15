"""Selección supervisada de características sobre UWF-ZeekData24, para el clasificador MITRE.

Anti fuga por diseño: primero se parte (estratificado) y recién después todo lo demás (imputación,
codificación, el modelo) se ajusta solo con la partición de entrenamiento, dentro de un Pipeline de
sklearn. Ordena las características de conexión de Zeek por importancia del bosque aleatorio e
imprime un informe rápido de clasificación sobre la partición de prueba.

Uso:
    python -m src.honeyml.features.uwf_selection
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
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
    """ColumnTransformer + RandomForest. Todo el estado se ajusta solo con entrenamiento."""
    prep = ColumnTransformer(
        [
            ("num", SimpleImputer(strategy="constant", fill_value=0), NUMERIC),
            ("cat", OneHotEncoder(handle_unknown="ignore", min_frequency=50), CATEGORICAL),
        ]
    )
    clf = RandomForestClassifier(
        n_estimators=120,
        max_depth=None,
        max_samples=0.3,  # el bootstrap mantiene el ajuste manejable sobre 1,9 millones de filas
        class_weight="balanced_subsample",  # muy desbalanceadas: none 50 % contra 0,03 %
        n_jobs=-1,
        random_state=42,
    )
    return Pipeline([("prep", prep), ("clf", clf)])


def main() -> None:
    df = load_uwf()
    x, y = features_target(df)
    # se dejan solo las columnas que se modelan; los booleanos pasan a enteros para el imputador
    x = x[NUMERIC + CATEGORICAL].copy()
    for c in ("local_orig", "local_resp"):
        x[c] = x[c].astype(int)

    # se parte ANTES de ajustar cualquier cosa, para que no haya fuga
    x_tr, x_te, y_tr, y_te = train_test_split(x, y, test_size=0.25, stratify=y, random_state=42)
    print(f"Train: {len(x_tr):,}  |  Test: {len(x_te):,}  |  clases: {y.nunique()}")

    pipe = build_pipeline()
    pipe.fit(x_tr, y_tr)  # se ajusta solo con entrenamiento

    # las importancias, devueltas a los nombres de las características
    prep = pipe.named_steps["prep"]
    names = prep.get_feature_names_out()
    importances = pipe.named_steps["clf"].feature_importances_
    ranking = pd.Series(importances, index=names).sort_values(ascending=False)

    print("\nTop 20 features por importancia (Random Forest):")
    for name, imp in ranking.head(20).items():
        print(f"  {imp:.4f}  {name}")

    y_pred = pipe.predict(x_te)
    print("\nReporte de clasificación (test held-out):")
    report = classification_report(y_te, y_pred, zero_division=0)
    print(report)

    print("Matriz de confusión (filas = real, columnas = predicho):")
    labels = sorted(y.unique())
    cm = confusion_matrix(y_te, y_pred, labels=labels)
    ancho = max(len(str(name)) for name in labels) + 2
    print(" " * ancho + "".join(f"{str(name)[:10]:>12}" for name in labels))
    for name, fila in zip(labels, cm):
        print(f"{str(name):<{ancho}}" + "".join(f"{v:>12,}".replace(",", ".") for v in fila))

    # se persiste para poder citar los números sin rehacer toda la selección
    metrics = {
        "accuracy": float(accuracy_score(y_te, y_pred)),
        "report": classification_report(y_te, y_pred, zero_division=0, output_dict=True),
        "confusion_matrix": {"labels": [str(x) for x in labels], "matrix": cm.tolist()},
        "n_train": int(len(x_tr)),
        "n_test": int(len(x_te)),
        "n_features": int(len(ranking)),
    }
    Path("data/processed/uwf_metrics.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("\n-> métricas: data/processed/uwf_metrics.json")

    ranking.to_frame("importance").to_parquet("data/processed/uwf_feature_ranking.parquet")
    print("-> ranking: data/processed/uwf_feature_ranking.parquet")


if __name__ == "__main__":
    main()
