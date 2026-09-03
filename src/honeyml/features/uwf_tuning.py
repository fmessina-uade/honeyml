"""Optimización de hiperparámetros del clasificador que ganó la comparación de modelos.

La comparación eligió la familia: potenciación por gradiente con histograma, en valores más o menos
por defecto. Este módulo responde lo que quedaba pendiente, si esa configuración era buena, y lo
hace sobre la misma partición, el mismo preprocesamiento y las mismas métricas, así los dos
resultados se pueden leer uno al lado del otro.

Se busca por halving sucesivo y no por grilla exhaustiva. Con 1,42 millones de filas de
entrenamiento, un solo ajuste cuesta unos 35 segundos, así que una grilla de cien combinaciones
sobre tres particiones correría durante horas. El halving gasta poco en muchos candidatos, se queda
con el mejor tercio y les da más datos, de modo que el presupuesto va a donde todavía puede cambiar
la respuesta.

Lo que no se busca es el balanceo de clases, que queda fijo en "balanced". Acá no es un
hiperparámetro sino una decisión ya tomada y justificada: sin él el modelo ignora las clases raras,
que son las que vale la pena detectar. Dejarlo dentro de la búsqueda permitiría que el proceso
negocie justamente aquello para lo que el modelo existe.

Un límite que conviene declarar. Exfiltration tiene 559 observaciones en todo el conjunto, el
0,029 %. Tras la partición quedan unas 419 para entrenar y 140 para medir, así que cualquier F1
sobre esa clase se calcula sobre esos 140 casos y diferencias de centésimas son ruido y no mejora.
La búsqueda optimiza el promedio macro e informa la clase débil, en vez de perseguirla.

Uso:
    python -m honeyml.features.uwf_tuning --rapido    # búsqueda corta, para validar el armado
    python -m honeyml.features.uwf_tuning             # búsqueda completa, para el resultado final
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

# Este import no se usa: habilita el buscador por halving, que sklearn todavía marca como
# experimental. Tiene que ejecutarse ANTES del import de model_selection de abajo, cosa que el
# orden alfabético ya garantiza (experimental < model_selection). Si alguna vez se reordenan a
# mano, este es el par que no se puede invertir.
from sklearn.experimental import enable_halving_search_cv  # noqa: F401
from sklearn.metrics import classification_report, f1_score
from sklearn.model_selection import HalvingRandomSearchCV, StratifiedKFold
from sklearn.pipeline import Pipeline

from .uwf_comparison import RANDOM_STATE, WEAK_CLASS, _preprocessor, cargar_y_partir

OUT_FILE = Path("data/processed/uwf_tuning.json")

# La configuración que usó la comparación, que queda como punto de referencia. Todo número que
# informa este módulo se dice contra estos, así "mejoró" siempre significa algo concreto.
BASE = {"max_iter": 150, "learning_rate": 0.1}

# Espacio de búsqueda. Los rangos son anchos a propósito en las dos perillas que gobiernan cuánta
# estructura puede aprender el modelo (la profundidad de cada árbol y cuánto aporta cada uno) y más
# angostos en regularización, que sobre este conjunto mueve el resultado mucho menos que las otras.
ESPACIO: dict[str, list[Any]] = {
    "clf__learning_rate": [0.03, 0.05, 0.1, 0.2, 0.3],
    "clf__max_iter": [100, 200, 300, 500],
    "clf__max_leaf_nodes": [15, 31, 63, 127],
    "clf__min_samples_leaf": [20, 50, 100, 200],
    "clf__l2_regularization": [0.0, 0.1, 1.0],
}


def _modelo(**kw: Any) -> HistGradientBoostingClassifier:
    """El clasificador elegido, con todo lo que no está bajo búsqueda fijo."""
    # Todo lo que no está bajo búsqueda queda en su valor por defecto, a propósito. Así
    # `_modelo(**BASE)` reproduce exactamente el candidato de la comparación, incluido el corte
    # temprano que sklearn activa solo por encima de 10.000 filas, y el ajustado difiere de él
    # únicamente en los parámetros buscados. Fijar acá cualquier otra cosa metería una segunda
    # diferencia entre los dos, y ya no se sabría a cuál atribuir el cambio.
    return HistGradientBoostingClassifier(
        class_weight="balanced",
        random_state=RANDOM_STATE,
        **kw,
    )


def _metricas(y_true: pd.Series, y_pred: Any) -> dict[str, float]:
    report = classification_report(y_true, y_pred, zero_division=0, output_dict=True)
    weak = report.get(WEAK_CLASS, {})
    return {
        "f1_macro": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
        "f1_ponderado": float(f1_score(y_true, y_pred, average="weighted", zero_division=0)),
        "exactitud": float(report["accuracy"]),
        "f1_clase_debil": float(weak.get("f1-score", 0.0)),
        "precision_clase_debil": float(weak.get("precision", 0.0)),
        "recall_clase_debil": float(weak.get("recall", 0.0)),
    }


def evaluar(
    modelo: HistGradientBoostingClassifier,
    x_tr: pd.DataFrame,
    y_tr: pd.Series,
    x_te: pd.DataFrame,
    y_te: pd.Series,
) -> tuple[dict[str, float], float]:
    """Entrena sobre la mitad de entrenamiento y mide sobre la reservada.

    Nunca sobre las particiones de la búsqueda.

    El puntaje de validación cruzada guió la búsqueda y por eso es optimista respecto de ella. El
    número que se informa tiene que salir de datos que la búsqueda nunca vio.
    """
    pipe = Pipeline([("prep", _preprocessor(scale=False)), ("clf", modelo)])
    inicio = time.monotonic()
    pipe.fit(x_tr, y_tr)
    segundos = time.monotonic() - inicio
    return _metricas(y_te, pipe.predict(x_te)), segundos


def main() -> None:
    ap = argparse.ArgumentParser(description="Ajuste de hiperparámetros del modelo elegido.")
    ap.add_argument(
        "--rapido",
        action="store_true",
        help="búsqueda corta sobre menos datos: sirve para validar que corre, no para el resultado",
    )
    args = ap.parse_args()

    x_tr, x_te, y_tr, y_te = cargar_y_partir()
    print(f"Entrenamiento: {len(x_tr):,}  |  Prueba: {len(x_te):,}".replace(",", "."))
    n_debil_te = int((y_te == WEAK_CLASS).sum())
    print(f"Clases: {y_tr.nunique()}  |  {WEAK_CLASS} en prueba: {n_debil_te} casos\n")

    # "exhaust" en lugar de un piso fijo, y no es un detalle.
    #
    # Con un piso elegido a mano, la progresión geométrica casi nunca cae justo sobre el total: con
    # 200.000 y factor 3 daba 200k → 600k → 1,8M, y como 1,8M excede las 1.423.959 filas
    # disponibles, sklearn cortaba en 600k. El ganador quedaba elegido sobre el 42 % de los datos
    # (pasó, y la auditoría de rondas de más abajo fue lo que lo destapó).
    #
    # Con "exhaust", sklearn calcula el piso hacia atrás desde el total, de modo que la última
    # ronda use todas las filas. Las primeras rondas quedan más chicas y por lo tanto más ruidosas,
    # pero eso es un descarte grueso: la decisión final se toma sobre el conjunto entero, que es
    # donde tiene que tomarse.
    candidatos = 12 if args.rapido else 36
    if args.rapido:
        print("  MODO RÁPIDO: búsqueda recortada, resultados solo orientativos\n")

    busqueda = HalvingRandomSearchCV(
        Pipeline([("prep", _preprocessor(scale=False)), ("clf", _modelo())]),
        ESPACIO,
        n_candidates=candidatos,
        factor=3,
        resource="n_samples",
        min_resources="exhaust",
        scoring="f1_macro",
        cv=StratifiedKFold(n_splits=3, shuffle=True, random_state=RANDOM_STATE),
        random_state=RANDOM_STATE,
        n_jobs=1,  # el propio clasificador ya usa todos los núcleos; anidar los degrada
        refit=False,
        verbose=1,
    )

    print("  buscando…", flush=True)
    inicio = time.monotonic()
    busqueda.fit(x_tr, y_tr)
    minutos = (time.monotonic() - inicio) / 60
    print(f"  búsqueda terminada en {minutos:.1f} minutos")

    # Auditoría de la búsqueda. Lo que importa es la última ronda: si no llegó al total del
    # entrenamiento, el ganador se eligió sobre datos parciales y su ventaja puede no sobrevivir al
    # conjunto entero. Ya pasó una vez, con un piso fijo la progresión cortaba en el 42 % de las
    # filas, y esta comprobación es lo que lo destapó.
    rondas = list(zip(busqueda.n_candidates_, busqueda.n_resources_, strict=True))
    print(
        "  rondas (candidatos × filas):",
        "  ".join(f"{c}×{r:,}" for c, r in rondas).replace(",", "."),
    )
    # Con tolerancia y no con `<` a secas: la progresión geométrica deja un resto de unas pocas
    # filas (1.423.953 de 1.423.959 en una corrida) y avisar por eso sería ruido que enseña a
    # ignorar el aviso. Lo que hay que detectar es una ronda final materialmente más chica.
    completa = rondas[-1][1] >= len(x_tr) * 0.99
    if not completa:
        faltante = 100 - rondas[-1][1] / len(x_tr) * 100
        print(
            f"  ATENCIÓN: la última ronda usó {rondas[-1][1]:,} de {len(x_tr):,} filas "
            f"({faltante:.0f} % menos). El ganador no se midió sobre el total.".replace(",", ".")
        )
    print()

    mejores = {k.replace("clf__", ""): v for k, v in busqueda.best_params_.items()}

    # Los dos se entrenan acá, sobre la mitad de entrenamiento completa, así la comparación es
    # entre dos modelos ajustados en las mismas condiciones y medidos sobre el mismo conjunto.
    print("  entrenando el ajustado sobre el total…", end="", flush=True)
    m_ajustado, s_ajustado = evaluar(_modelo(**mejores), x_tr, y_tr, x_te, y_te)
    print(f" {s_ajustado:.0f}s")

    print("  entrenando el de referencia sobre el total…", end="", flush=True)
    m_base, s_base = evaluar(_modelo(**BASE), x_tr, y_tr, x_te, y_te)
    print(f" {s_base:.0f}s\n")

    print("  hiperparámetros elegidos")
    for k, v in sorted(mejores.items()):
        marca = "  (era " + str(BASE[k]) + ")" if k in BASE and BASE[k] != v else ""
        print(f"    {k:24} {v}{marca}")

    filas = [
        ("F1 macro", "f1_macro"),
        ("F1 ponderado", "f1_ponderado"),
        ("Exactitud", "exactitud"),
        (f"F1 {WEAK_CLASS}", "f1_clase_debil"),
        (f"Precisión {WEAK_CLASS}", "precision_clase_debil"),
        (f"Recall {WEAK_CLASS}", "recall_clase_debil"),
    ]
    print(f"\n  {'métrica':<26}{'referencia':>12}{'ajustado':>12}{'cambio':>12}")
    print("  " + "-" * 62)
    for etiqueta, clave in filas:
        antes, despues = m_base[clave], m_ajustado[clave]
        print(f"  {etiqueta:<26}{antes:>12.4f}{despues:>12.4f}{despues - antes:>+12.4f}")

    mejora = m_ajustado["f1_macro"] - m_base["f1_macro"]
    print()
    if mejora > 0.005:
        print(f"  El ajuste mejora el F1 macro en {mejora:+.4f}. Conviene adoptarlo.")
    elif mejora > 0:
        print(f"  La mejora es de {mejora:+.4f}: demasiado chica para justificar el cambio.")
        print("  Los valores por defecto ya estaban bien para este problema, que también es")
        print("  un resultado: dice que el margen no está en los hiperparámetros.")
    else:
        print(f"  El ajuste NO mejora ({mejora:+.4f}). Se mantiene la configuración de referencia.")

    print(
        f"\n  Recordatorio: el F1 de {WEAK_CLASS} se calcula sobre {n_debil_te} casos. "
        "Diferencias de centésimas ahí son ruido."
    )

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(
        json.dumps(
            {
                "modo": "rapido" if args.rapido else "completo",
                "minutos_busqueda": round(minutos, 1),
                "candidatos_evaluados": candidatos,
                "recurso_minimo": int(busqueda.min_resources_),
                "recurso_maximo": int(busqueda.max_resources_),
                "ultima_ronda_uso_el_total": completa,
                "rondas": [{"candidatos": c, "filas": r} for c, r in rondas],
                "espacio": {k.replace("clf__", ""): v for k, v in ESPACIO.items()},
                "mejores_hiperparametros": mejores,
                "hiperparametros_referencia": BASE,
                "metricas_ajustado": m_ajustado,
                "metricas_referencia": m_base,
                "mejora_f1_macro": mejora,
                "casos_clase_debil_en_prueba": n_debil_te,
                "n_entrenamiento": len(x_tr),
                "n_prueba": len(x_te),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\n  Resultado -> {OUT_FILE}")


if __name__ == "__main__":
    main()
