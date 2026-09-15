"""Ajusta el clasificador final una vez y lo persiste con todo lo necesario para confiar en él.

Los módulos de comparación y de ajuste entrenan el modelo y lo descartan en cada corrida. Eso está
bien mientras la pregunta es cuál modelo, y deja de servir cuando la respuesta es este modelo: el
motor de triaje no puede reentrenar en cada evento, y un número que nadie puede reproducir es una
afirmación, no un resultado.

El módulo produce dos archivos que viajan juntos:

    models/uwf_tactica.joblib   el pipeline ajustado, preprocesamiento y clasificador en un objeto
    models/uwf_tactica.json     la tarjeta: con qué se entrenó, cuánto puntúa, qué necesita

Deja resueltas tres cosas que el joblib no puede decir por sí solo.

El punto de operación. El estudio del umbral (`uwf_umbral`) recorta la validación de la mitad de
entrenamiento, lo que le cuesta el 20 % de los datos y deja su línea base (0,8741) por debajo de la
del modelo completo (0,8782), una salvedad que habría que explicar cada vez que se los pone lado a
lado. Acá el umbral sale de probabilidades fuera de muestra sobre la mitad de entrenamiento entera,
así que el modelo exportado se entrena con toda ella y el umbral sigue sin ver una fila con la que
se ajustó.

El ranking de características. Importancia por permutación sobre las quince columnas originales,
medida sobre el modelo que efectivamente se despliega, y no la del bosque aleatorio que se descarta
en la comparación, que responde qué le importa a un clasificador que nadie corre.

Y la procedencia. Versiones de las bibliotecas, orden de clases, lista de columnas, tamaños de
partición y el resumen criptográfico del propio artefacto. Un objeto de sklearn cargado bajo otra
versión falla de formas que parecen un problema de datos, y la tarjeta convierte eso en un
diagnóstico de una línea.

Uso:
    python -m honeyml.features.uwf_export
    python -m honeyml.features.uwf_export --sin-permutacion   # omite el paso más lento
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.inspection import permutation_importance
from sklearn.metrics import classification_report, f1_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import Pipeline

from .uwf_comparison import RANDOM_STATE, WEAK_CLASS, _preprocessor, cargar_y_partir
from .uwf_selection import CATEGORICAL, NUMERIC
from .uwf_tuning import BASE, _modelo
from .uwf_umbral import UMBRALES, _fila, _predecir_con_umbral

MODEL_FILE = Path("models/uwf_tactica.joblib")
CARD_FILE = Path("models/uwf_tactica.json")

# Tres particiones y no cinco. Cada una es un entrenamiento completo sobre 950.000 filas, y lo que
# se busca acá es una probabilidad honesta por fila, no una estimación fina del error: cinco
# particiones cuestan casi el doble y mueven el umbral elegido menos que el paso de la grilla.
PARTICIONES = 3

# La importancia por permutación reentrena nada pero predice n_repeticiones × n_columnas veces.
# Sobre las 474.654 filas de prueba serían 75 pasadas completas; sobre una submuestra estratificada
# el ranking es el mismo y la corrida baja de media hora a medio minuto.
MUESTRA_PERMUTACION = 60_000
REPETICIONES_PERMUTACION = 5


def _digest(path: Path) -> str:
    """SHA-256 del artefacto, para que la tarjeta no se despegue en silencio del archivo."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def _umbral_fuera_de_muestra(
    x_tr: pd.DataFrame, y_tr: pd.Series, clases: np.ndarray, indice_debil: int
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    """Barre el umbral sobre probabilidades fuera de muestra, en toda la mitad de entrenamiento.

    Cada fila recibe su probabilidad de un modelo que no la vio, que es la propiedad que hace
    honesto el barrido. A diferencia de reservar una porción, no cuesta datos de entrenamiento, así
    que el modelo que se publica se ajusta sobre toda la mitad.
    """
    print(f"  probabilidades fuera de muestra ({PARTICIONES} particiones)…", end="", flush=True)
    comenzado = time.monotonic()
    proba = cross_val_predict(
        Pipeline([("prep", _preprocessor(scale=False)), ("clf", _modelo(**BASE))]),
        x_tr,
        y_tr,
        cv=StratifiedKFold(PARTICIONES, shuffle=True, random_state=RANDOM_STATE),
        method="predict_proba",
        n_jobs=1,  # cada partición ya usa todos los núcleos internamente
    )
    print(f" {time.monotonic() - comenzado:.0f}s")

    referencia = _fila(y_tr, clases[proba.argmax(axis=1)], None)
    frontera = [
        _fila(y_tr, _predecir_con_umbral(proba, clases, indice_debil, u), u) for u in UMBRALES
    ]

    # Mismo criterio que la búsqueda de hiperparámetros: mejor F1 macro. Elegir "el de más recall"
    # siempre lleva al umbral más bajo, que dispara sobre casi todo y deja de informar.
    elegido = max(frontera, key=lambda f: f["f1_macro"])
    return elegido, frontera, referencia


# Banda dentro de la cual una diferencia de F1 macro no distingue dos puntos de operación. La clase
# débil aporta 140 casos de prueba: un solo acierto mueve su recall casi un punto y el F1 macro unas
# milésimas, así que por debajo de esto se está leyendo ruido de muestreo.
BANDA_RUIDO = 0.005


def _veredicto(defecto: dict[str, Any], con_umbral: dict[str, Any]) -> dict[str, Any]:
    """Dice sin vueltas qué compró el umbral sobre datos no vistos, y qué costó.

    El umbral se elige sobre probabilidades fuera de muestra, donde cada modelo se ajusta con dos
    tercios de la mitad de entrenamiento y por eso puntúa por debajo del que se publica. Esa
    superficie es la correcta para elegir, porque nunca ve una fila con la que se ajustó, pero es
    sistemáticamente pesimista sobre la regla por defecto, así que un umbral puede ganar ahí y
    perder acá. Decirlo es el punto de este bloque: la alternativa es una tarjeta que informa la
    elección sin informar su precio.
    """
    d_macro = con_umbral["f1_macro"] - defecto["f1_macro"]
    d_recall = con_umbral["recall_debil"] - defecto["recall_debil"]

    if d_macro > BANDA_RUIDO:
        return {
            "resultado": "mejora",
            "titulo": f"El umbral se sostiene fuera de muestra: F1 macro {d_macro:+.4f}.",
            "detalle": [f"Además, el recall sobre {WEAK_CLASS} sube {d_recall:+.4f}."],
            "delta_f1_macro": d_macro,
            "delta_recall_debil": d_recall,
        }

    if d_macro < -BANDA_RUIDO:
        return {
            "resultado": "no_se_sostiene",
            "titulo": f"El umbral NO se sostiene sobre prueba: F1 macro {d_macro:+.4f}.",
            "detalle": [
                "Se exporta igual, pero el punto de operación por defecto es el que hay que citar.",
                "Señal de que la validación fuera de muestra tiene muy pocos casos para decidir.",
            ],
            "delta_f1_macro": d_macro,
            "delta_recall_debil": d_recall,
        }

    return {
        "resultado": "permuta_declarada",
        "titulo": (
            f"El umbral no mejora el agregado ({d_macro:+.4f}): es una permuta, no una mejora."
        ),
        "detalle": [
            f"Compra {d_recall:+.4f} de recall sobre {WEAK_CLASS} pagando precisión y",
            f"{abs(d_macro):.4f} de F1 macro, que está dentro del ruido de {BANDA_RUIDO}.",
            "Se adopta por el mismo criterio con que se eligió la familia del modelo: un falso",
            "positivo cuesta una revisión y un falso negativo cuesta una intrusión no detectada.",
            "Enunciarlo como permuta y no como mejora es lo que lo hace defendible.",
        ],
        "delta_f1_macro": d_macro,
        "delta_recall_debil": d_recall,
    }


def _importancia(pipe: Pipeline, x_te: pd.DataFrame, y_te: pd.Series) -> list[dict[str, Any]]:
    """Importancia por permutación sobre las columnas originales, en el modelo que se exporta."""
    if len(x_te) > MUESTRA_PERMUTACION:
        # Estratificada: con 140 casos de la clase débil en toda la prueba, un muestreo al azar
        # podría dejar fuera casi todos y el F1 macro pasaría a medir cinco clases.
        from sklearn.model_selection import train_test_split

        x_muestra, _, y_muestra, _ = train_test_split(
            x_te,
            y_te,
            train_size=MUESTRA_PERMUTACION,
            stratify=y_te,
            random_state=RANDOM_STATE,
        )
    else:
        x_muestra, y_muestra = x_te, y_te

    cuantas = f"{len(x_muestra):,}".replace(",", ".")
    print(f"  importancia por permutación sobre {cuantas} filas…", end="", flush=True)
    comenzado = time.monotonic()
    resultado = permutation_importance(
        pipe,
        x_muestra,
        y_muestra,
        scoring="f1_macro",
        n_repeats=REPETICIONES_PERMUTACION,
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )
    print(f" {time.monotonic() - comenzado:.0f}s")

    ranking = [
        {
            "caracteristica": col,
            "importancia": float(m),
            "desvio": float(s),
        }
        for col, m, s in zip(
            x_muestra.columns, resultado.importances_mean, resultado.importances_std, strict=True
        )
    ]
    ranking.sort(key=lambda r: r["importancia"], reverse=True)
    return ranking


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--sin-permutacion",
        action="store_true",
        help="omite el ranking por permutación; útil para reexportar rápido tras un cambio menor",
    )
    args = ap.parse_args()

    x_tr, x_te, y_tr, y_te = cargar_y_partir()
    print(f"Entrenamiento: {len(x_tr):,}  |  Prueba: {len(x_te):,}".replace(",", "."))
    print(f"Clases: {y_tr.nunique()}  |  Columnas: {len(x_tr.columns)}\n")

    print("  entrenando el modelo final sobre el entrenamiento completo…", end="", flush=True)
    comenzado = time.monotonic()
    pipe = Pipeline([("prep", _preprocessor(scale=False)), ("clf", _modelo(**BASE))])
    pipe.fit(x_tr, y_tr)
    segundos_ajuste = time.monotonic() - comenzado
    print(f" {segundos_ajuste:.0f}s")

    clases = pipe.classes_
    indice_debil = int(np.where(clases == WEAK_CLASS)[0][0])

    elegido, frontera, referencia_oof = _umbral_fuera_de_muestra(x_tr, y_tr, clases, indice_debil)
    umbral = float(elegido["umbral"])

    print(f"\n  frontera fuera de muestra ({WEAK_CLASS}, entrenamiento completo)")
    print(f"    {'umbral':>8}{'precisión':>11}{'recall':>9}{'F1':>8}{'F1 macro':>11}")
    print("    " + "-" * 47)
    print(
        f"    {'defecto':>8}{referencia_oof['precision_debil']:>11.4f}"
        f"{referencia_oof['recall_debil']:>9.4f}{referencia_oof['f1_debil']:>8.4f}"
        f"{referencia_oof['f1_macro']:>11.4f}"
    )
    for f in frontera:
        marca = "  <-" if f["umbral"] == umbral else ""
        print(
            f"    {f['umbral']:>8.2f}{f['precision_debil']:>11.4f}{f['recall_debil']:>9.4f}"
            f"{f['f1_debil']:>8.4f}{f['f1_macro']:>11.4f}{marca}"
        )
    print(f"\n  umbral elegido: {umbral:.2f}")

    # Recién ahora se toca la prueba, con el punto de operación ya fijado.
    proba_te = pipe.predict_proba(x_te)
    y_defecto = clases[proba_te.argmax(axis=1)]
    y_umbral = _predecir_con_umbral(proba_te, clases, indice_debil, umbral)

    prueba_defecto = _fila(y_te, y_defecto, None)
    prueba_umbral = _fila(y_te, y_umbral, umbral)
    reporte = classification_report(y_te, y_umbral, zero_division=0, output_dict=True)

    print("\n  sobre prueba no vista")
    print(f"    {'métrica':<26}{'por defecto':>13}{'con umbral':>13}{'cambio':>11}")
    print("    " + "-" * 63)
    for etiqueta, clave in [
        ("F1 macro", "f1_macro"),
        (f"F1 {WEAK_CLASS}", "f1_debil"),
        (f"Precisión {WEAK_CLASS}", "precision_debil"),
        (f"Recall {WEAK_CLASS}", "recall_debil"),
    ]:
        a, b = prueba_defecto[clave], prueba_umbral[clave]
        print(f"    {etiqueta:<26}{a:>13.4f}{b:>13.4f}{b - a:>+11.4f}")
    print(
        f"    {'Alertas emitidas':<26}{prueba_defecto['alertas_emitidas']:>13}"
        f"{prueba_umbral['alertas_emitidas']:>13}"
        f"{prueba_umbral['alertas_emitidas'] - prueba_defecto['alertas_emitidas']:>+11}"
    )

    veredicto = _veredicto(prueba_defecto, prueba_umbral)
    print(f"\n  {veredicto['titulo']}")
    for linea in veredicto["detalle"]:
        print(f"    {linea}")

    ranking = [] if args.sin_permutacion else _importancia(pipe, x_te, y_te)
    if ranking:
        print("\n  ranking por permutación (columnas originales)")
        for i, r in enumerate(ranking[:8], start=1):
            print(f"    {i:>2}. {r['caracteristica']:<20}{r['importancia']:>9.4f}")

    MODEL_FILE.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipe, MODEL_FILE, compress=3)
    digest = _digest(MODEL_FILE)

    tarjeta = {
        "nombre": "clasificador de táctica MITRE sobre UWF-ZeekData24",
        "archivo": MODEL_FILE.name,
        "sha256": digest,
        "exportado": datetime.now(UTC).isoformat(timespec="seconds"),
        # Sin esto, un joblib cargado bajo otra versión de sklearn falla de formas que parecen un
        # problema de datos. Con esto, el diagnóstico es una línea.
        "entorno": {
            "python": platform.python_version(),
            "scikit_learn": sklearn.__version__,
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "joblib": joblib.__version__,
        },
        "modelo": {
            "familia": "HistGradientBoostingClassifier",
            "hiperparametros": {**BASE, "class_weight": "balanced", "random_state": RANDOM_STATE},
            "eleccion": "elegida por F1 macro y por la clase débil; el ajuste no la mejoró",
        },
        "entrada": {
            "columnas_numericas": NUMERIC,
            "columnas_categoricas": CATEGORICAL,
            "orden_importa": False,
            "nota": "el preprocesamiento va dentro del pipeline: se pasa el DataFrame crudo",
        },
        "clases": [str(c) for c in clases],
        "punto_de_operacion": {
            "clase": WEAK_CLASS,
            "umbral": umbral,
            "criterio": (
                "mejor F1 macro sobre probabilidades fuera de muestra del entrenamiento completo"
            ),
            "particiones": PARTICIONES,
            "frontera": frontera,
            "referencia_sin_umbral": referencia_oof,
            "como_aplicarlo": (
                f"asignar '{WEAK_CLASS}' cuando su probabilidad supere el umbral; "
                "en caso contrario, la clase de mayor probabilidad"
            ),
        },
        "metricas_prueba": {
            "veredicto": veredicto,
            "por_defecto": prueba_defecto,
            "con_umbral": prueba_umbral,
            "f1_macro_con_umbral": float(
                f1_score(y_te, y_umbral, average="macro", zero_division=0)
            ),
            "reporte": reporte,
        },
        "datos": {
            "n_entrenamiento": int(len(x_tr)),
            "n_prueba": int(len(x_te)),
            "casos_clase_debil_en_prueba": int((y_te == WEAK_CLASS).sum()),
            "particion": f"train_test_split estratificado, test_size=0.25, semilla {RANDOM_STATE}",
            "nota": "misma partición que la comparación y el ajuste, para poder comparar métricas",
        },
        "importancia_por_permutacion": {
            "metodo": "permutation_importance sobre columnas originales, criterio F1 macro",
            "n_filas": min(MUESTRA_PERMUTACION, len(x_te)),
            "n_repeticiones": REPETICIONES_PERMUTACION,
            "ranking": ranking,
        }
        if ranking
        else None,
        "segundos_entrenamiento": round(segundos_ajuste, 1),
        "limitaciones_declaradas": [
            "dest_port_zeek se lleva 0,439 de la importancia por permutación, y entrenado con esa "
            "columna sola el modelo saca 0,634 de F1 macro contra 0,878 con las quince. Buena "
            "parte de eso es cómo estaba montado el laboratorio y no una regularidad del ataque: "
            "el puerto 4848 aporta 871.186 filas y todas son Credential Access, el 53 aporta "
            "943.766 y ninguna es maliciosa. Entre los dos son el 96 % del corpus. En una red "
            "donde esos puertos no signifiquen lo mismo, el número no se sostiene.",
            f"{WEAK_CLASS} tiene 559 observaciones en 1,9 millones (0,029 %). El techo lo pone la "
            "cantidad de ejemplos, no la configuración: la búsqueda de hiperparámetros lo confirmó "
            "con un resultado negativo.",
        ],
    }

    CARD_FILE.write_text(json.dumps(tarjeta, indent=2, ensure_ascii=False), encoding="utf-8")

    tamano = MODEL_FILE.stat().st_size / 1024
    print(f"\n  Modelo   -> {MODEL_FILE} ({tamano:.0f} KB)")
    print(f"  Tarjeta  -> {CARD_FILE}")
    print(f"  Digest   -> {digest[:16]}…")


def cargar_modelo() -> tuple[Pipeline, dict[str, Any]]:
    """Carga el modelo exportado y su tarjeta, y se niega a devolver un par que no coincide.

    El motor no tiene forma de notar que la tarjeta describe un archivo distinto del que acaba de
    cargar, porque el pipeline predice igual con el punto de operación equivocado. Comparar el
    resumen criptográfico acá convierte eso en un error al cargar, en vez de una respuesta
    equivocada al decidir.
    """
    if not MODEL_FILE.exists():
        raise FileNotFoundError(
            f"No hay modelo exportado en {MODEL_FILE}. "
            "Correr: python -m honeyml.features.uwf_export"
        )
    tarjeta: dict[str, Any] = json.loads(CARD_FILE.read_text(encoding="utf-8"))
    actual = _digest(MODEL_FILE)
    if actual != tarjeta.get("sha256"):
        raise ValueError(
            f"El modelo en {MODEL_FILE} no es el que describe {CARD_FILE}: "
            f"digest {actual[:16]}… frente a {str(tarjeta.get('sha256'))[:16]}…. "
            "Reexportar antes de usarlo."
        )
    pipe: Pipeline = joblib.load(MODEL_FILE)
    return pipe, tarjeta


if __name__ == "__main__":
    main()
