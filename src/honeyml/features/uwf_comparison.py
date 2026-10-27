"""Compara clasificadores candidatos sobre el conjunto de referencia, en igualdad de condiciones.

Sirve para saber si el modelo que se informa es la elección correcta. Entrena varias familias
sobre la misma partición, con el mismo preprocesamiento, y las ordena por la métrica que acá
importa: el promedio macro del F1. Dos de las seis clases se llevan casi todas las observaciones,
así que la exactitud premia a un clasificador que ignore al resto, mientras que el promedio macro
pesa todas las clases igual, que es lo que necesita un caso de uso de seguridad: la táctica rara es
justamente la que vale la pena detectar.

La comparación sigue aparte la clase más débil, exfiltración, que la configuración base apenas
detecta. Un candidato que la levante importa más que uno que le rasque una décima al agregado.

Se corre con `python -m honeyml.features.uwf_comparison`. Con `--rapido` submuestrea el
entrenamiento para iterar, y con `--mostrar` imprime la tabla de la última comparación guardada sin
volver a entrenar, que es lo que se usa para mostrarla.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, cast

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
# la clase que peor maneja la configuración de partida; va aparte porque el agregado la tapa
WEAK_CLASS = "Exfiltration"
RANDOM_STATE = 42


def _preprocessor(scale: bool) -> ColumnTransformer:
    """El preprocesamiento común. Solo el modelo lineal necesita las características escaladas."""
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
    """Cada candidato, y si necesita o no las características escaladas.

    Todos los que lo admiten llevan balanceo de clases, así la comparación aísla el efecto de la
    familia del modelo en vez de volver a medir el desbalance.
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


def cargar() -> tuple[pd.DataFrame, pd.Series]:
    """El conjunto de referencia con las columnas que se modelan, todavía sin partir.

    Se separó de `cargar_y_partir` para el análisis de dispersión, que necesita repartir el mismo
    conjunto con varias semillas. Leer los parquet una vez por semilla sería tiempo tirado.
    """
    df = load_uwf()
    x, y = features_target(df)
    x = x[NUMERIC + CATEGORICAL].copy()
    for c in ("local_orig", "local_resp"):
        if c in x.columns:
            x[c] = x[c].astype(int)
    return x, y


def partir(
    x: pd.DataFrame, y: pd.Series, semilla: int = RANDOM_STATE
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    """Parte estratificado, un cuarto para prueba.

    La semilla es parámetro solo para medir cuánto se mueve el resultado al cambiarla. Todo lo que
    informa métricas usa la de siempre, o dejarían de ser comparables entre módulos.
    """
    # train_test_split no está tipada: devuelve una lista sin anotar. El cast declara la forma que
    # el llamador puede confiar (cuatro objetos, en el orden entrenamiento/prueba de x y después de
    # y) en lugar de dejar que se propague un Any por todo el módulo de ajuste.
    partes = train_test_split(x, y, test_size=0.25, stratify=y, random_state=semilla)
    return cast("tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]", tuple(partes))


def cargar_y_partir() -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    """Carga el conjunto de referencia y lo parte, siempre de la misma forma.

    Se extrajo acá para que el ajuste de hiperparámetros entrene y mida sobre exactamente la misma
    partición que esta comparación. Si cada módulo armara la suya, una mejora aparente podría ser
    nada más una partición de prueba más fácil, y desde los números no habría manera de notarlo.
    """
    return partir(*cargar())


def imprimir(resultados: list[dict[str, Any]]) -> None:
    """La tabla de la comparación, ordenada por F1 macro, y qué gana con cada criterio."""
    resultados = sorted(resultados, key=lambda r: r["f1_macro"], reverse=True)
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


def mostrar_guardada() -> None:
    guardada = json.loads(OUT_FILE.read_text(encoding="utf-8"))
    if guardada["submuestreado"]:
        print("  La comparación guardada se hizo en modo rápido, con datos submuestreados.")
    entrenamiento = f"{guardada['n_entrenamiento']:,}".replace(",", ".")
    prueba = f"{guardada['n_prueba']:,}".replace(",", ".")
    print(f"Comparación guardada en {OUT_FILE}")
    print(f"Entrenamiento: {entrenamiento}  |  Prueba: {prueba}")
    imprimir(guardada["resultados"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--rapido",
        action="store_true",
        help="submuestrea el entrenamiento para iterar rápido; no usar para el resultado final",
    )
    ap.add_argument(
        "--mostrar",
        action="store_true",
        help="imprime la última comparación guardada, sin volver a entrenar",
    )
    args = ap.parse_args()
    if args.mostrar:
        mostrar_guardada()
        return

    x_tr, x_te, y_tr, y_te = cargar_y_partir()
    x = pd.concat([x_tr, x_te])
    y = pd.concat([y_tr, y_te])

    if args.rapido:
        # submuestreo estratificado, así sobreviven todas las clases, incluidas las raras
        x_tr, _, y_tr, _ = train_test_split(
            x_tr, y_tr, train_size=0.15, stratify=y_tr, random_state=RANDOM_STATE
        )
        print("  Modo rápido: entrenamiento submuestreado, resultados solo orientativos\n")

    print(f"Entrenamiento: {len(x_tr):,}  |  Prueba: {len(x_te):,}".replace(",", "."))
    print(f"Clases: {y.nunique()}  |  Características: {len(x.columns)}\n")

    resultados = []
    for name, (model, scale) in candidates().items():
        print(f"  entrenando {name}:", end="", flush=True)
        try:
            res = evaluate(name, model, scale, x_tr, y_tr, x_te, y_te)
        except Exception as exc:  # que falle un candidato no puede hundir la comparación
            print(f" falló: {type(exc).__name__}: {exc}")
            continue
        resultados.append(res)
        print(f" {res['segundos_entrenamiento']}s")

    if not resultados:
        raise SystemExit("Ningún candidato completó el entrenamiento.")

    resultados.sort(key=lambda r: r["f1_macro"], reverse=True)
    imprimir(resultados)

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
    print(f"\nGuardado en {OUT_FILE}")


if __name__ == "__main__":
    main()
