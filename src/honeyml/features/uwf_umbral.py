"""Umbral de decisión para la clase más débil, como punto de operación explícito.

Ajustar los hiperparámetros no mueve este modelo: los valores por defecto son los adecuados, y la
búsqueda cierra esa pregunta con un resultado negativo. Lo que sí lo mueve es dónde se corta la
decisión.

Un clasificador predice la clase de mayor puntaje. Esa regla no es neutral: minimiza el error
global, que sobre un conjunto donde dos clases se llevan el 96 % de las observaciones es casi lo
mismo que decir "errá para el lado de la mayoría". Para una clase con 559 ejemplos en 1,9 millones,
ese valor por defecto favorece perderla, y lo hace en silencio.

Entonces el corte pasa a ser una elección, y este módulo lo convierte en eso: barre el umbral de
probabilidad de Exfiltration, mide la frontera de precisión y exhaustividad, y reporta qué cuesta
cada punto en el resto.

Dónde se elige el umbral: sobre una porción de validación recortada de la mitad de entrenamiento,
nunca sobre la de prueba. Elegirlo sobre los mismos datos con los que después se reporta sería
elegir la respuesta y recién ahí medirla, y el número quedaría mejor y significaría menos. La mitad
de prueba no se toca hasta que el punto de operación ya está fijado.

Uso:
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

# Por debajo de 0,05 la clase inunda todo; por encima de 0,60 deja de dispararse en una clase tan
# rara. El rango es ancho a propósito: la idea es mostrar la frontera, no defender un valor.
UMBRALES = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.60]


def _predecir_con_umbral(
    proba: np.ndarray, clases: np.ndarray, indice_debil: int, umbral: float
) -> np.ndarray:
    """Asigna la clase débil cuando supera el umbral; si no, el ganador de siempre.

    El umbral es solo para la clase débil. Darle uno a cada clase pediría además una regla de
    desempate entre ellas, y cambiaría el comportamiento de cinco clases para arreglar una.
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
