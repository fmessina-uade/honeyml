"""Demostración del clasificador exportado sobre flujos que no vio al ajustarse.

Toma flujos de la partición de prueba y muestra, para cada uno, la táctica verdadera, la que predice
el modelo y con qué probabilidad. Predice con el punto de operación de la tarjeta y con la misma
función que usa la exportación, así lo que se ve es el modelo que se informa y no una variante.

La muestra se arma por clase. Al azar sobre toda la prueba saldrían casi solo conexiones benignas y
de Credential Access, que son la gran mayoría, y la clase débil no aparecería nunca. Se suma además
un error real del modelo: una demostración que solo muestra aciertos esconde justo la limitación que
la evaluación documenta.

Antes de la muestra se recalcula el F1 macro sobre toda la prueba y se lo pone al lado del de la
tarjeta, para que el número informado se pueda comprobar en el momento.

Uso:
    python -m honeyml.features.uwf_clasificar
    python -m honeyml.features.uwf_clasificar --por-clase 4 --semilla 7
"""

from __future__ import annotations

import argparse
import time
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import f1_score

from .uwf_comparison import RANDOM_STATE, cargar_y_partir
from .uwf_export import CARD_FILE, MODEL_FILE, cargar_modelo
from .uwf_umbral import _predecir_con_umbral

# Dos flujos por clase alcanzan para ver cada táctica sin que la tabla deje de entrar en pantalla.
POR_CLASE = 2

# El modelo usa quince columnas. Estas cinco son las que un analista reconoce de un vistazo y
# alcanzan para entender de qué conexión se trata.
COLUMNAS_VISIBLES = ["dest_port_zeek", "proto", "service", "conn_state", "duration"]

# En el conjunto de referencia, "none" es tráfico sin ataque.
NOMBRE_VISIBLE = {"none": "benigno"}


def muestra_por_clase(y: pd.Series, por_clase: int, semilla: int) -> list[int]:
    """Posiciones de hasta `por_clase` flujos de cada clase, agrupadas por clase.

    Una clase con menos casos que `por_clase` aporta los que tenga en lugar de fallar.
    """
    generador = np.random.default_rng(semilla)
    posiciones = np.arange(len(y))
    elegidas: list[int] = []
    for clase in sorted(y.unique()):
        de_la_clase = posiciones[y.to_numpy() == clase]
        cuantas = min(por_clase, len(de_la_clase))
        elegidas.extend(int(p) for p in generador.choice(de_la_clase, size=cuantas, replace=False))
    return elegidas


def predecir(pipe: Any, x: pd.DataFrame, tarjeta: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    """La clase predicha con el punto de operación de la tarjeta, y la probabilidad de esa clase."""
    proba = np.asarray(pipe.predict_proba(x))
    clases = np.asarray(pipe.classes_)
    punto = tarjeta["punto_de_operacion"]
    indice_debil = int(np.flatnonzero(clases == punto["clase"])[0])
    predicha = _predecir_con_umbral(proba, clases, indice_debil, float(punto["umbral"]))
    columna_de = {clase: i for i, clase in enumerate(clases)}
    columnas = np.array([columna_de[c] for c in predicha])
    return predicha, proba[np.arange(len(predicha)), columnas]


def un_error(y_real: np.ndarray, y_predicha: np.ndarray, semilla: int) -> int | None:
    """La posición de un error del modelo, elegida al azar, o None si no se equivocó en ninguno."""
    errores = np.flatnonzero(y_real != y_predicha)
    if errores.size == 0:
        return None
    return int(np.random.default_rng(semilla).choice(errores))


def _nombre(clase: str) -> str:
    return NOMBRE_VISIBLE.get(clase, clase)


def _linea(x: pd.DataFrame, real: str, predicha: str, probabilidad: float) -> str:
    fila = x.iloc[0]
    servicio = fila["service"] if isinstance(fila["service"], str) and fila["service"] else "-"
    duracion = f"{fila['duration']:.2f}s" if pd.notna(fila["duration"]) else "-"
    marca = "✓" if real == predicha else "✗"
    return (
        f"  {marca} {int(fila['dest_port_zeek']):>6} {fila['proto']:<5} {servicio[:16]:<16} "
        f"{fila['conn_state']:<6} {duracion:>9}   {_nombre(real):<17} {_nombre(predicha):<17} "
        f"{probabilidad:>6.2f}"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Demostración del clasificador exportado.")
    ap.add_argument("--por-clase", type=int, default=POR_CLASE)
    ap.add_argument("--semilla", type=int, default=RANDOM_STATE)
    args = ap.parse_args()

    pipe, tarjeta = cargar_modelo()
    punto = tarjeta["punto_de_operacion"]
    print(f"Modelo : {tarjeta['modelo']['familia']}, exportado {tarjeta['exportado'][:10]}")
    print(f"Huella : {MODEL_FILE} coincide con {CARD_FILE}")
    print(f"Umbral : {punto['clase']} desde {punto['umbral']:.2f}\n")

    print("  cargando el conjunto de referencia y su partición…", end="", flush=True)
    comenzado = time.monotonic()
    _, x_prueba, _, y_prueba = cargar_y_partir()
    x_prueba = x_prueba.reset_index(drop=True)
    y_real = y_prueba.to_numpy()
    print(f" {time.monotonic() - comenzado:.0f}s")

    print("  prediciendo toda la prueba…", end="", flush=True)
    comenzado = time.monotonic()
    predicha, probabilidad = predecir(pipe, x_prueba, tarjeta)
    print(f" {time.monotonic() - comenzado:.0f}s\n")

    f1 = float(f1_score(y_real, predicha, average="macro", zero_division=0))
    informado = float(tarjeta["metricas_prueba"]["f1_macro_con_umbral"])
    total = f"{len(y_real):,}".replace(",", ".")
    print(f"  F1 macro sobre {total} flujos de prueba: {f1:.4f}   (tarjeta: {informado:.4f})\n")

    encabezado = (
        f"    {'puerto':>6} {'proto':<5} {'servicio':<16} {'estado':<6} {'duración':>9}   "
        f"{'táctica real':<17} {'predicha':<17} {'prob.':>6}"
    )
    print(encabezado)
    print("    " + "-" * (len(encabezado) - 4))
    filas = muestra_por_clase(pd.Series(y_real), args.por_clase, args.semilla)
    for i in filas:
        print(_linea(x_prueba.iloc[[i]], y_real[i], predicha[i], probabilidad[i]))
    aciertos = sum(1 for i in filas if y_real[i] == predicha[i])
    print(f"\n  en la muestra: {aciertos} de {len(filas)} bien")

    error = un_error(y_real, predicha, args.semilla)
    if error is None:
        print("  el modelo no se equivocó en ningún flujo de prueba")
    else:
        errores = int((y_real != predicha).sum())
        print(f"  un error real, de los {errores} que comete sobre toda la prueba:")
        print(_linea(x_prueba.iloc[[error]], y_real[error], predicha[error], probabilidad[error]))

    print("\n  límites declarados en la tarjeta")
    for texto in tarjeta["limitaciones_declaradas"]:
        print(f"    {texto.split('. ')[0].rstrip('.')}.")
    print(
        "\n  Clasifica flujos de Zeek del conjunto de referencia. Los sensores de HoneyML no"
        "\n  producen esos campos, así que el modelo es la línea base del proyecto y no clasifica"
        "\n  la telemetría capturada."
    )


if __name__ == "__main__":
    main()
