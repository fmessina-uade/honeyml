"""Qué tan bueno es el clasificador, qué tan seguros estamos de ese número y de dónde sale.

La comparación eligió familia y el ajuste confirmó que los valores por defecto ya estaban bien.
Ninguno de los dos contesta las cuatro preguntas que un lector escéptico hace primero, y este
módulo existe para eso.

La primera es si el modelo aprendió algo. La exactitud da 0,9978, pero dos de las seis clases se
llevan el 96 % del conjunto, así que un clasificador que responda siempre la mayoritaria también va
a sacar un número enorme. Sin esa referencia al lado, el 0,9978 no demuestra nada.

La segunda es adónde se equivoca. Exfiltration tiene precisión 0,24: de cada cuatro alertas, tres
son falsas. Saber de qué clase vienen esas tres cambia la lectura, porque no es lo mismo confundirla
con reconocimiento que con acceso inicial.

La tercera es cuánto se mueve el resultado. Todo lo que informamos sale de una sola partición con
una sola semilla, y Exfiltration queda con unas 140 filas en la mitad de prueba. Con esa cantidad,
un F1 de 0,376 puede ser bastante distinto con otro sorteo, y hasta ahora no teníamos con qué
responder cuánto.

La cuarta la trajo la discusión sobre para qué sirve el modelo. La importancia por permutación le
da al puerto de destino 0,439 y a la que le sigue 0,065, y con esa distancia hay que saber cuánto
del acierto es esa columna sola y qué trae cada puerto detrás. De ahí sale hasta dónde se puede
afirmar algo del clasificador fuera del banco de pruebas donde se grabó el corpus.

Uso:
    python -m honeyml.features.uwf_evaluacion
    python -m honeyml.features.uwf_evaluacion --rapido    # submuestreado, para validar el armado
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import confusion_matrix, f1_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

from .uwf_comparison import RANDOM_STATE, WEAK_CLASS, _preprocessor, cargar, partir
from .uwf_tuning import BASE, _modelo

OUT_FILE = Path("data/processed/uwf_evaluacion.json")

# La columna que se lleva 0,439 de importancia por permutación, contra 0,065 de la segunda.
PUERTO = "dest_port_zeek"

# Cuántos puertos se miran de cerca. Los diez primeros se llevan casi todas las filas del corpus y
# el resto son colas de unas pocas observaciones, que no cambian la lectura.
PUERTOS_A_MIRAR = 10

# Los eventos que capturaron nuestros propios sensores. Se leen para contrastar contra los puertos
# de los que depende el modelo: si no coinciden, el clasificador no tiene de dónde agarrarse acá.
EVENTOS_PROPIOS = Path("data/processed/honeypot_events.parquet")

# Las semillas del análisis de dispersión. Cinco alcanzan para ver si el número se mueve poco o
# mucho, y no pretenden ser una estimación fina: con 140 casos de la clase débil por partición, más
# repeticiones darían una media más prolija sobre una muestra que sigue siendo chica.
#
# Se cambia la semilla de la partición y no la del modelo. Lo que se quiere medir es cuánto depende
# el resultado de qué filas cayeron en prueba, que con una clase de 559 observaciones es la fuente
# de variación que domina.
SEMILLAS = (42, 7, 123, 2024, 31337)


def _ajustar(x_tr: pd.DataFrame, y_tr: pd.Series) -> Pipeline:
    """El modelo que efectivamente se despliega, con los valores de la comparación."""
    pipe = Pipeline([("prep", _preprocessor(scale=False)), ("clf", _modelo(**BASE))])
    pipe.fit(x_tr, y_tr)
    return pipe


def linea_base(
    x_tr: pd.DataFrame, y_tr: pd.Series, x_te: pd.DataFrame, y_te: pd.Series, f1_modelo: float
) -> dict[str, Any]:
    """Cuánto sacan dos clasificadores que no miran las características.

    `most_frequent` responde siempre la clase mayoritaria y `stratified` sortea respetando las
    proporciones. Los dos son el piso de lo que se puede sacar sin aprender nada, y la distancia
    contra ellos es lo que convierte la exactitud en un argumento.
    """
    resultados: list[dict[str, Any]] = []
    for estrategia in ("most_frequent", "stratified", "prior"):
        tonto = DummyClassifier(strategy=estrategia, random_state=RANDOM_STATE)
        tonto.fit(x_tr, y_tr)
        pred = tonto.predict(x_te)
        resultados.append(
            {
                "estrategia": estrategia,
                "f1_macro": float(f1_score(y_te, pred, average="macro", zero_division=0)),
                "exactitud": float((pred == y_te.to_numpy()).mean()),
            }
        )

    mejor = max(float(r["f1_macro"]) for r in resultados)
    return {
        "triviales": resultados,
        "f1_macro_modelo": f1_modelo,
        "ventaja_sobre_el_mejor_trivial": f1_modelo - mejor,
    }


def confusion(pipe: Pipeline, x_te: pd.DataFrame, y_te: pd.Series) -> dict[str, Any]:
    """La matriz completa, y de dónde salen los falsos positivos de la clase débil.

    La matriz sola es difícil de leer con seis clases y proporciones tan distintas. Lo que se busca
    acá es concreto: cuando el modelo grita Exfiltration y se equivoca, qué era en realidad.
    """
    clases = sorted(y_te.unique())
    pred = pipe.predict(x_te)
    matriz = confusion_matrix(y_te, pred, labels=clases)

    i_debil = clases.index(WEAK_CLASS)
    columna = matriz[:, i_debil]
    falsos: dict[str, int] = {
        str(clases[i]): int(columna[i])
        for i in range(len(clases))
        if i != i_debil and columna[i] > 0
    }
    total_falsos = sum(falsos.values())

    return {
        "clases": clases,
        "matriz": matriz.tolist(),
        "clase_debil": WEAK_CLASS,
        "verdaderos_positivos": int(matriz[i_debil, i_debil]),
        "falsos_positivos": total_falsos,
        "origen_de_los_falsos_positivos": dict(sorted(falsos.items(), key=lambda kv: -kv[1])),
        "se_le_escapan_a": {
            str(clases[j]): int(matriz[i_debil, j])
            for j in range(len(clases))
            if j != i_debil and matriz[i_debil, j] > 0
        },
    }


def dispersion(
    x: pd.DataFrame, y: pd.Series, semillas: tuple[int, ...] = SEMILLAS
) -> dict[str, Any]:
    """Cuánto se mueve el resultado al cambiar qué filas caen en prueba.

    Es la respuesta a "¿ese 0,8782 cuánto vale?". Un rango angosto dice que el número es del modelo;
    uno ancho, que es de la partición, y ahí conviene informar el promedio y no una corrida.
    """
    corridas: list[dict[str, Any]] = []
    for semilla in semillas:
        x_tr, x_te, y_tr, y_te = partir(x, y, semilla=semilla)
        comenzado = time.monotonic()
        pipe = _ajustar(x_tr, y_tr)
        pred = pipe.predict(x_te)
        corridas.append(
            {
                "semilla": semilla,
                "f1_macro": float(f1_score(y_te, pred, average="macro", zero_division=0)),
                "f1_clase_debil": float(
                    f1_score(y_te, pred, labels=[WEAK_CLASS], average="macro", zero_division=0)
                ),
                "casos_debiles_en_prueba": int((y_te == WEAK_CLASS).sum()),
                "segundos": round(time.monotonic() - comenzado, 1),
            }
        )
        print(f"    semilla {semilla:<6} F1 macro {corridas[-1]['f1_macro']:.4f}", flush=True)

    macros = np.array([c["f1_macro"] for c in corridas])
    debiles = np.array([c["f1_clase_debil"] for c in corridas])
    return {
        "corridas": corridas,
        "f1_macro": {
            "media": float(macros.mean()),
            "desvio": float(macros.std(ddof=1)),
            "minimo": float(macros.min()),
            "maximo": float(macros.max()),
        },
        "f1_clase_debil": {
            "media": float(debiles.mean()),
            "desvio": float(debiles.std(ddof=1)),
            "minimo": float(debiles.min()),
            "maximo": float(debiles.max()),
        },
    }


def reparto_por_puerto(
    x: pd.DataFrame, y: pd.Series, cuantos: int = PUERTOS_A_MIRAR
) -> list[dict[str, Any]]:
    """Qué tácticas trae cada uno de los puertos más frecuentes del corpus.

    Un puerto que aparece en cientos de miles de filas y siempre con la misma táctica no es una
    regularidad de los ataques: es cómo estaba montado el laboratorio que grabó el corpus.
    """
    tabla = pd.crosstab(x[PUERTO], y)
    filas: list[dict[str, Any]] = []
    for puerto in tabla.sum(axis=1).nlargest(cuantos).index:
        conteo = tabla.loc[puerto]
        conteo = conteo[conteo > 0].sort_values(ascending=False)
        total = int(conteo.sum())
        filas.append(
            {
                "puerto": int(puerto),
                "filas": total,
                "tacticas_distintas": int(len(conteo)),
                "tactica_dominante": str(conteo.index[0]),
                "participacion_de_la_dominante": float(conteo.iloc[0] / total),
            }
        )
    return filas


def puertos_propios(ruta: Path = EVENTOS_PROPIOS, cuantos: int = PUERTOS_A_MIRAR) -> list[int]:
    """Los puertos de destino que registran de verdad Cowrie y Dionaea.

    Si el parquet consolidado no está generado, devuelve la lista vacía y el contraste queda sin
    hacer. Es una comparación entre dos conjuntos distintos y no tiene por qué frenar al resto.
    """
    if not ruta.exists():
        return []
    columna = pd.read_parquet(ruta, columns=["destination.port"])["destination.port"].dropna()
    return [int(p) for p in columna.value_counts().nlargest(cuantos).index]


def dominio_del_puerto(
    x: pd.DataFrame,
    y: pd.Series,
    particion: tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series],
    f1_modelo: float,
) -> dict[str, Any]:
    """Cuánto del acierto explica el puerto de destino solo, y contra qué puertos vemos nosotros.

    Entrenar el mismo clasificador con esa única columna contesta la primera mitad. La segunda sale
    de cruzar los puertos del corpus con los de nuestros sensores: lo que el modelo aprendió de un
    puerto que nunca vamos a observar no nos sirve, por bueno que sea el número de la tabla.
    """
    x_tr, x_te, y_tr, y_te = particion
    prep = ColumnTransformer([("num", SimpleImputer(strategy="constant", fill_value=0), [PUERTO])])
    pipe = Pipeline([("prep", prep), ("clf", _modelo(**BASE))])
    pipe.fit(x_tr[[PUERTO]], y_tr)
    sola = float(f1_score(y_te, pipe.predict(x_te[[PUERTO]]), average="macro", zero_division=0))

    reparto = reparto_por_puerto(x, y)
    propios = puertos_propios()
    return {
        "caracteristica": PUERTO,
        "f1_macro_con_una_sola": sola,
        "f1_macro_con_todas": f1_modelo,
        "aporte_de_las_demas": f1_modelo - sola,
        "reparto_por_puerto": reparto,
        "puertos_de_nuestros_sensores": propios,
        "puertos_del_corpus_que_no_vemos": [
            r["puerto"] for r in reparto if propios and r["puerto"] not in propios
        ],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rapido", action="store_true", help="submuestrea, para validar el armado")
    args = ap.parse_args()

    print("Cargando el conjunto de referencia…", flush=True)
    x, y = cargar()
    if args.rapido:
        x, _, y, _ = train_test_split(x, y, train_size=0.1, stratify=y, random_state=RANDOM_STATE)
        print("  MODO RÁPIDO: submuestreado, los números son solo orientativos\n")

    particion = partir(x, y)
    x_tr, x_te, y_tr, y_te = particion
    print(f"Entrenamiento: {len(x_tr):,}  |  Prueba: {len(x_te):,}".replace(",", "."))

    print("\n[1/4] Ajustando el modelo de referencia…", flush=True)
    pipe = _ajustar(x_tr, y_tr)
    f1_modelo = float(f1_score(y_te, pipe.predict(x_te), average="macro", zero_division=0))
    print(f"  F1 macro del modelo: {f1_modelo:.4f}")

    print("\n[2/4] Línea base trivial…", flush=True)
    base = linea_base(x_tr, y_tr, x_te, y_te, f1_modelo)
    for r in base["triviales"]:
        print(
            f"  {r['estrategia']:<16} F1 macro {r['f1_macro']:.4f}  exactitud {r['exactitud']:.4f}"
        )
    print(f"  ventaja del modelo: {base['ventaja_sobre_el_mejor_trivial']:+.4f} de F1 macro")

    print("\n[3/4] Matriz de confusión…", flush=True)
    conf = confusion(pipe, x_te, y_te)
    print(
        f"  {WEAK_CLASS}: {conf['verdaderos_positivos']} aciertos y "
        f"{conf['falsos_positivos']} falsos positivos"
    )
    for clase, n in conf["origen_de_los_falsos_positivos"].items():
        print(f"    {n:>5} eran en realidad {clase}")

    print(f"\n[4/4] Peso de {PUERTO}…", flush=True)
    puerto = dominio_del_puerto(x, y, particion, f1_modelo)
    print(
        f"  entrenado con esa columna sola: F1 macro {puerto['f1_macro_con_una_sola']:.4f}"
        f"  (con las quince: {puerto['f1_macro_con_todas']:.4f})"
    )
    for r in puerto["reparto_por_puerto"][:5]:
        filas = f"{r['filas']:,}".replace(",", ".")
        print(
            f"    {r['puerto']:>6}  {filas:>10} filas  {r['tacticas_distintas']} táctica(s), "
            f"{r['participacion_de_la_dominante']:.0%} {r['tactica_dominante']}"
        )
    sin_ver = puerto["puertos_del_corpus_que_no_vemos"]
    if sin_ver:
        listado = ", ".join(str(p) for p in sin_ver)
        print(f"  de esos puertos, nuestros sensores nunca registraron: {listado}")

    print(f"\nDispersión sobre {len(SEMILLAS)} particiones…", flush=True)
    disp = dispersion(x, y)
    m = disp["f1_macro"]
    d = disp["f1_clase_debil"]
    print(
        f"  F1 macro       {m['media']:.4f} ± {m['desvio']:.4f}"
        f"  (de {m['minimo']:.4f} a {m['maximo']:.4f})"
    )
    print(
        f"  F1 clase débil {d['media']:.4f} ± {d['desvio']:.4f}"
        f"  (de {d['minimo']:.4f} a {d['maximo']:.4f})"
    )

    salida = {
        "submuestreado": args.rapido,
        "n_entrenamiento": len(x_tr),
        "n_prueba": len(x_te),
        "linea_base": base,
        "confusion": conf,
        "dominio_del_puerto": puerto,
        "dispersion": disp,
    }
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(salida, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nGuardado en {OUT_FILE}")


if __name__ == "__main__":
    main()
