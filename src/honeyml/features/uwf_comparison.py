"""Compare candidate classifiers on the reference dataset, under identical conditions.

The project already reports metrics for one model. This module answers the question that leaves
open: was that the right choice? It trains several families on the same split, with the same
preprocessing, and ranks them by the metric that actually matters here.

That metric is the macro average of the F1 score, not accuracy. Two of the six classes hold 96 %
of the observations, so accuracy rewards a classifier that ignores the rest. The macro average
weighs every class equally, which is what a security use case needs: the rare tactic is the one
worth detecting.

The comparison pays particular attention to the weakest class, exfiltration, whose F1 sat at 0,11
with the baseline. A candidate that lifts it matters more than one that shaves a decimal off the
aggregate.

Usage:
    python -m honeyml.features.uwf_comparison
    python -m honeyml.features.uwf_comparison --rapido    # subsample, for iterating
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import pandas as pd
from sklearn.base import BaseEstimator
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import (
    ExtraTreesClassifier,
    HistGradientBoostingClassifier,
    RandomForestClassifier,
)
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, f1_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from ..eda.uwf_loader import features_target, load_uwf
from .uwf_selection import CATEGORICAL, NUMERIC

OUT_FILE = Path("data/processed/uwf_comparison.json")
# the class the baseline handles worst; tracked separately because the aggregate hides it
WEAK_CLASS = "Exfiltration"
RANDOM_STATE = 42


def _preprocessor(scale: bool) -> ColumnTransformer:
    """Shared preprocessing. Only the linear model needs its features scaled."""
    numeric: list[Any] = [SimpleImputer(strategy="constant", fill_value=0)]
    if scale:
        numeric.append(StandardScaler())
    num_step = Pipeline([(f"s{i}", s) for i, s in enumerate(numeric)])
    return ColumnTransformer(
        [
            ("num", num_step, NUMERIC),
            ("cat", OneHotEncoder(handle_unknown="ignore", min_frequency=50), CATEGORICAL),
        ]
    )


def candidates() -> dict[str, tuple[BaseEstimator, bool]]:
    """Each candidate with whether it needs scaled features.

    Every one that supports it carries class balancing, so the comparison isolates the effect of
    the model family rather than re-measuring the imbalance.
    """
    return {
        "bosque_aleatorio": (
            RandomForestClassifier(
                n_estimators=120,
                max_samples=0.3,
                class_weight="balanced_subsample",
                n_jobs=-1,
                random_state=RANDOM_STATE,
            ),
            False,
        ),
        "arboles_extra": (
            ExtraTreesClassifier(
                n_estimators=120,
                max_samples=0.3,
                bootstrap=True,
                class_weight="balanced_subsample",
                n_jobs=-1,
                random_state=RANDOM_STATE,
            ),
            False,
        ),
        "potenciacion_por_histograma": (
            HistGradientBoostingClassifier(
                max_iter=150,
                learning_rate=0.1,
                class_weight="balanced",
                random_state=RANDOM_STATE,
            ),
            False,
        ),
        "regresion_logistica": (
            LogisticRegression(
                max_iter=300,
                class_weight="balanced",
                n_jobs=-1,
                random_state=RANDOM_STATE,
            ),
            True,
        ),
    }


def evaluate(
    name: str,
    model: BaseEstimator,
    scale: bool,
    x_tr: pd.DataFrame,
    y_tr: pd.Series,
    x_te: pd.DataFrame,
    y_te: pd.Series,
) -> dict[str, Any]:
    pipe = Pipeline([("prep", _preprocessor(scale)), ("clf", model)])

    started = time.monotonic()
    pipe.fit(x_tr, y_tr)
    fit_seconds = time.monotonic() - started

    y_pred = pipe.predict(x_te)
    report = classification_report(y_te, y_pred, zero_division=0, output_dict=True)
    weak = report.get(WEAK_CLASS, {})

    return {
        "modelo": name,
        "f1_macro": float(f1_score(y_te, y_pred, average="macro", zero_division=0)),
        "f1_ponderado": float(f1_score(y_te, y_pred, average="weighted", zero_division=0)),
        "exactitud": float(report["accuracy"]),
        "f1_clase_debil": float(weak.get("f1-score", 0.0)),
        "precision_clase_debil": float(weak.get("precision", 0.0)),
        "recall_clase_debil": float(weak.get("recall", 0.0)),
        "segundos_entrenamiento": round(fit_seconds, 1),
        "reporte": report,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--rapido",
        action="store_true",
        help="submuestrea el entrenamiento para iterar rápido; no usar para el resultado final",
    )
    args = ap.parse_args()

    df = load_uwf()
    x, y = features_target(df)
    x = x[NUMERIC + CATEGORICAL].copy()
    for c in ("local_orig", "local_resp"):
        if c in x.columns:
            x[c] = x[c].astype(int)

    x_tr, x_te, y_tr, y_te = train_test_split(
        x, y, test_size=0.25, stratify=y, random_state=RANDOM_STATE
    )

    if args.rapido:
        # stratified subsample so every class survives, including the rare ones
        x_tr, _, y_tr, _ = train_test_split(
            x_tr, y_tr, train_size=0.15, stratify=y_tr, random_state=RANDOM_STATE
        )
        print("  MODO RÁPIDO: entrenamiento submuestreado, resultados solo orientativos\n")

    print(f"Entrenamiento: {len(x_tr):,}  |  Prueba: {len(x_te):,}".replace(",", "."))
    print(f"Clases: {y.nunique()}  |  Características: {len(x.columns)}\n")

    resultados = []
    for name, (model, scale) in candidates().items():
        print(f"  entrenando {name}…", end="", flush=True)
        try:
            res = evaluate(name, model, scale, x_tr, y_tr, x_te, y_te)
        except Exception as exc:  # a candidate failing must not sink the comparison
            print(f" falló: {type(exc).__name__}: {exc}")
            continue
        resultados.append(res)
        print(f" {res['segundos_entrenamiento']}s")

    if not resultados:
        raise SystemExit("Ningún candidato completó el entrenamiento.")

    resultados.sort(key=lambda r: r["f1_macro"], reverse=True)

    print(f"\n{'modelo':<30}{'F1 macro':>10}{'F1 pond.':>10}{'exactitud':>11}", end="")
    print(f"{'F1 ' + WEAK_CLASS:>18}{'seg':>7}")
    print("-" * 86)
    for r in resultados:
        print(
            f"{r['modelo']:<30}{r['f1_macro']:>10.4f}{r['f1_ponderado']:>10.4f}"
            f"{r['exactitud']:>11.4f}{r['f1_clase_debil']:>18.4f}"
            f"{r['segundos_entrenamiento']:>7.0f}"
        )

    mejor = resultados[0]
    print(f"\nMejor por F1 macro: {mejor['modelo']} ({mejor['f1_macro']:.4f})")

    mejor_debil = max(resultados, key=lambda r: r["f1_clase_debil"])
    if mejor_debil["modelo"] != mejor["modelo"]:
        print(
            f"Mejor sobre {WEAK_CLASS}: {mejor_debil['modelo']} "
            f"({mejor_debil['f1_clase_debil']:.4f} frente a {mejor['f1_clase_debil']:.4f})"
        )
        print("  Los dos criterios no coinciden: la elección final es una decisión, no un cálculo.")

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(
        json.dumps(
            {
                "submuestreado": args.rapido,
                "n_entrenamiento": int(len(x_tr)),
                "n_prueba": int(len(x_te)),
                "clase_debil": WEAK_CLASS,
                "resultados": resultados,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\n-> {OUT_FILE}")


if __name__ == "__main__":
    main()
