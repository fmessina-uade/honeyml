"""Decision threshold for the weakest class, as an explicit operating point.

Tuning the hyperparameters did not move this model: the defaults were already right, and the
search closed that question with a negative result. What *does* move is where the decision is cut.

A classifier predicts whichever class scores highest. That rule is not neutral — it happens to
minimise the overall error rate, which on a dataset where two classes hold 96 % of the observations
is close to saying "err on the side of the majority". For a class with 559 examples in 1,9 million,
that default quietly favours missing it.

So the cut becomes a choice, and this module makes it one: it sweeps the probability threshold for
Exfiltration, measures the precision/recall frontier, and reports what each point costs elsewhere.

WHERE THE THRESHOLD IS CHOSEN
On a validation slice carved out of the training half, never on the test half. Picking it on the
same data used to report would be choosing the answer and then measuring it: the number would look
better and mean less. The test half stays untouched until the operating point is already fixed.

Usage:
    python -m honeyml.features.uwf_umbral
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import f1_score, precision_recall_fscore_support
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

from .uwf_comparison import RANDOM_STATE, WEAK_CLASS, _preprocessor, cargar_y_partir
from .uwf_tuning import BASE, _modelo

OUT_FILE = Path("data/processed/uwf_umbral.json")

# Below 0,05 the class floods everything; above 0,60 it stops firing on a class this rare. The
# range is wide on purpose: the point is to show the frontier, not to defend one value.
UMBRALES = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.60]


def _predecir_con_umbral(
    proba: np.ndarray, clases: np.ndarray, indice_debil: int, umbral: float
) -> np.ndarray:
    """Assign the weak class whenever it clears the threshold; otherwise the usual winner.

    Only the weak class gets a threshold. Giving one to every class would need a tie-break rule
    between them, and would change the behaviour of five classes to fix one.
    """
    ganador = clases[proba.argmax(axis=1)]
    supera = proba[:, indice_debil] >= umbral
    return np.where(supera, clases[indice_debil], ganador)


def _fila(y_true: pd.Series, y_pred: np.ndarray, umbral: float | None) -> dict[str, Any]:
    p, r, f, _ = precision_recall_fscore_support(
        y_true, y_pred, labels=[WEAK_CLASS], average=None, zero_division=0
    )
    alertas = int((y_pred == WEAK_CLASS).sum())
    return {
        "umbral": umbral,
        "precision_debil": float(p[0]),
        "recall_debil": float(r[0]),
        "f1_debil": float(f[0]),
        "f1_macro": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
        "alertas_emitidas": alertas,
    }


def main() -> None:
    x_tr_completo, x_te, y_tr_completo, y_te = cargar_y_partir()

    # La validación sale del entrenamiento, no de la prueba. Ver el encabezado.
    x_tr, x_val, y_tr, y_val = train_test_split(
        x_tr_completo,
        y_tr_completo,
        test_size=0.2,
        stratify=y_tr_completo,
        random_state=RANDOM_STATE,
    )
    print(f"Entrenamiento: {len(x_tr):,}  |  Validación: {len(x_val):,}".replace(",", "."))
    print(
        f"Prueba: {len(x_te):,}  |  {WEAK_CLASS} en prueba: {(y_te == WEAK_CLASS).sum()}".replace(
            ",", "."
        )
    )
    print()

    pipe = Pipeline([("prep", _preprocessor(scale=False)), ("clf", _modelo(**BASE))])
    print("  entrenando…", end="", flush=True)
    pipe.fit(x_tr, y_tr)
    print(" listo\n")

    clases = pipe.classes_
    indice_debil = int(np.where(clases == WEAK_CLASS)[0][0])

    proba_val = pipe.predict_proba(x_val)
    base_val = _fila(y_val, clases[proba_val.argmax(axis=1)], None)

    print(f"  frontera sobre validación ({WEAK_CLASS})")
    print(
        f"    {'umbral':>8}{'precisión':>11}{'recall':>9}{'F1':>8}{'F1 macro':>11}{'alertas':>10}"
    )
    print("    " + "-" * 57)
    b = base_val
    print(
        f"    {'defecto':>8}{b['precision_debil']:>11.4f}{b['recall_debil']:>9.4f}"
        f"{b['f1_debil']:>8.4f}{b['f1_macro']:>11.4f}{b['alertas_emitidas']:>10}"
    )

    frontera = []
    for u in UMBRALES:
        fila = _fila(y_val, _predecir_con_umbral(proba_val, clases, indice_debil, u), u)
        frontera.append(fila)
        print(
            f"    {u:>8.2f}{fila['precision_debil']:>11.4f}{fila['recall_debil']:>9.4f}"
            f"{fila['f1_debil']:>8.4f}{fila['f1_macro']:>11.4f}{fila['alertas_emitidas']:>10}"
        )

    # Criterio explícito: el mejor F1 macro sobre validación. No se elige "el que más recall da"
    # porque eso siempre lleva al umbral más bajo, que dispara sobre todo y deja de informar.
    mejor = max(frontera, key=lambda f: f["f1_macro"])
    mejora_val = mejor["f1_macro"] - base_val["f1_macro"]
    print(f"\n  elegido en validación: umbral {mejor['umbral']:.2f} (F1 macro {mejora_val:+.4f})")

    # Recién ahora se toca la prueba, con el umbral ya fijado.
    proba_te = pipe.predict_proba(x_te)
    base_te = _fila(y_te, clases[proba_te.argmax(axis=1)], None)
    ajustado_te = _fila(
        y_te, _predecir_con_umbral(proba_te, clases, indice_debil, mejor["umbral"]), mejor["umbral"]
    )

    print("\n  sobre prueba, con el umbral ya elegido")
    print(f"    {'métrica':<26}{'por defecto':>13}{'con umbral':>13}{'cambio':>11}")
    print("    " + "-" * 63)
    for etiqueta, clave in [
        ("F1 macro", "f1_macro"),
        (f"F1 {WEAK_CLASS}", "f1_debil"),
        (f"Precisión {WEAK_CLASS}", "precision_debil"),
        (f"Recall {WEAK_CLASS}", "recall_debil"),
    ]:
        a, b = base_te[clave], ajustado_te[clave]
        print(f"    {etiqueta:<26}{a:>13.4f}{b:>13.4f}{b - a:>+11.4f}")
    print(
        f"    {'Alertas emitidas':<26}{base_te['alertas_emitidas']:>13}"
        f"{ajustado_te['alertas_emitidas']:>13}"
        f"{ajustado_te['alertas_emitidas'] - base_te['alertas_emitidas']:>+11}"
    )

    diferencia = ajustado_te["f1_macro"] - base_te["f1_macro"]
    print()
    if diferencia > 0.002:
        print(f"  El umbral mejora el F1 macro en {diferencia:+.4f} sobre datos no vistos.")
    elif diferencia > -0.002:
        print(f"  El cambio es de {diferencia:+.4f}: el umbral por defecto ya estaba bien ubicado.")
        print("  El valor de esto no es la mejora sino la frontera: muestra qué se puede comprar")
        print("  y a qué precio, en lugar de dejar el punto de operación como algo dado.")
    else:
        print(f"  El umbral elegido NO se sostiene fuera de validación ({diferencia:+.4f}).")
        print("  Señal de que la validación tiene muy pocos casos de la clase para decidir.")

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(
        json.dumps(
            {
                "clase": WEAK_CLASS,
                "hiperparametros": BASE,
                "umbral_elegido": mejor["umbral"],
                "criterio": "mejor F1 macro sobre validación, separada del entrenamiento",
                "frontera_validacion": frontera,
                "referencia_validacion": base_val,
                "prueba_por_defecto": base_te,
                "prueba_con_umbral": ajustado_te,
                "n_entrenamiento": len(x_tr),
                "n_validacion": len(x_val),
                "n_prueba": len(x_te),
                "casos_clase_debil_en_prueba": int((y_te == WEAK_CLASS).sum()),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\n  Resultado -> {OUT_FILE}")


if __name__ == "__main__":
    main()
