"""Attacker archetypes: unsupervised grouping of the observed sources by their behaviour.

WHY THIS EXISTS
The session fingerprints already group attacks by byte-identical command sequences. That is a
strict criterion — it cannot group anything by accident, which makes every family it finds real,
but it also means one changed character splits a family in two, and it says nothing at all about
the sources that never ran a command.

This works the other way round: it takes the 35 behavioural features computed per source IP and
lets the data decide where the boundaries fall. It generalises past literal matching and covers
every observed address, not only those that reached a shell.

It also fills a gap the reference dataset cannot. UWF-ZeekData24 supplies MITRE labels but is
network-flow telemetry: bytes, packets, connection state. Our features are behavioural — how many
passwords were tried, whether a file was downloaded, at what hour, at what pace. Nothing in the
benchmark describes that, so nothing in the benchmark can label it. Clustering needs no labels,
which is exactly why it fits here.

WHAT IT IS NOT
The groups are descriptive, not ground truth. There is no external key saying how many kinds of
attacker exist, so the number of groups is a choice made on a measurable criterion and stated as
such. The names are an interpretation layer written after reading the profiles, and they are
labelled as interpretation wherever they are shown.

Usage:
    python -m honeyml.features.arquetipos
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

ENTRADA = Path("data/processed/features_por_ip.parquet")
SALIDA = Path("data/processed/arquetipos.json")
RANDOM_STATE = 42

# Rango de k a evaluar. Por debajo de 3 el resultado no informa —siempre da "mucho" y "poco"— y por
# encima de 8 los grupos se vuelven demasiado chicos para describirlos con honestidad.
KS = range(3, 9)

# La silueta es O(n²): sobre 14.000 puntos son 200 millones de pares. Se calcula sobre una muestra,
# que es lo habitual y suficiente para comparar k entre sí.
MUESTRA_SILUETA = 5000

# Cuántas características definen a cada grupo en el informe. Con 35 disponibles, mostrarlas todas
# no describe: esconde.
RASGOS_POR_GRUPO = 5

# Nombres legibles para las columnas, para que el perfil se pueda leer sin conocer el esquema.
LEGIBLE = {
    "log1p_n_eventos": "volumen de eventos",
    "log1p_n_sesiones": "cantidad de sesiones",
    "log1p_eventos_por_sesion": "eventos por sesión",
    "log1p_login_intentos": "intentos de acceso",
    "log1p_login_exitosos": "accesos logrados",
    "log1p_usuarios_distintos": "usuarios distintos probados",
    "log1p_pass_distintas": "contraseñas distintas probadas",
    "log1p_n_comandos": "comandos ejecutados",
    "ejecuto_comandos": "llegó a ejecutar comandos",
    "descargo_archivo": "descargó un archivo",
    "ratio_ssh": "proporción de SSH",
    "log1p_span_horas": "horas entre el primer y último evento",
    "horas_activas": "horas distintas con actividad",
    "ratio_nocturno": "proporción de actividad nocturna",
    "log1p_dur_sesion_media_s": "duración media de sesión",
    "tuvo_logins": "intentó autenticarse",
    "ratio_fallo_login": "proporción de accesos fallidos",
    "log1p_interarribo_medio_s": "tiempo medio entre eventos",
    "log1p_eventos_por_hora": "ritmo por hora",
}


def nombrar(p: dict[str, Any]) -> tuple[str, str]:
    """Name an archetype from its profile, never from its cluster number.

    KMeans does not guarantee stable numbering between runs, so a name attached to "group 2" would
    move to a different set of attackers on the next run without anyone noticing. Deriving it from
    the profile keeps the name attached to the behaviour.

    This is the interpretation layer, and it is the only part of this module that is not measured.
    """
    if p["pct_ejecuto_comandos"] > 50 and p["pct_descargo_archivo"] > 25:
        return (
            "Intrusión efectiva",
            "Entraron, ejecutaron comandos y trajeron algo. Es el grupo que representa un "
            "compromiso real y no un intento.",
        )
    if p["pct_logro_acceso"] > 50 or p["mediana_intentos_acceso"] >= 10:
        return (
            "Fuerza bruta",
            "Prueban credenciales de forma sostenida. Algunos entran, pero casi ninguno hace algo "
            "después: el objetivo parece ser la credencial en sí.",
        )
    return (
        "Sondeo",
        "Se conectan, miran y se van. Sin intentos de acceso sostenidos ni comandos: es "
        "reconocimiento indiscriminado, el ruido de fondo de internet.",
    )


def _legible(col: str) -> str:
    if col in LEGIBLE:
        return LEGIBLE[col]
    if col.startswith("cmd_"):
        return f"usó «{col[4:]}»"
    return col


def elegir_k(x: np.ndarray) -> tuple[int, list[dict[str, Any]]]:
    """Pick the number of groups by silhouette, preferring fewer when the gain is marginal.

    Silhouette measures how much better each point fits its own group than the nearest other one.
    It is not a truth, it is a criterion — but it is a stated one, which is what matters: the
    alternative is choosing a number because the result looked nice.
    """
    rng = np.random.default_rng(RANDOM_STATE)
    idx = rng.choice(len(x), size=min(MUESTRA_SILUETA, len(x)), replace=False)

    barrido = []
    for k in KS:
        km = KMeans(n_clusters=k, n_init=10, random_state=RANDOM_STATE).fit(x)
        s = float(silhouette_score(x[idx], km.labels_[idx]))
        barrido.append({"k": k, "silueta": s, "inercia": float(km.inertia_)})
        print(f"    k={k}  silueta {s:.4f}")

    mejor = max(barrido, key=lambda b: b["silueta"])
    # Un k menor que quede dentro del 2 % del mejor se prefiere: grupos más grandes se describen
    # mejor y se sostienen mejor ante un cambio de datos.
    umbral = mejor["silueta"] * 0.98
    elegido = min((b for b in barrido if b["silueta"] >= umbral), key=lambda b: b["k"])
    return int(elegido["k"]), barrido


def perfilar(
    df: pd.DataFrame, x: np.ndarray, etiquetas: np.ndarray, columnas: list[str]
) -> list[dict[str, Any]]:
    """Describe each group by the features that separate it from the rest of the population.

    The comparison is in standardised space, so a deviation is read in standard deviations and
    features on different scales can be ranked against each other.
    """
    perfiles = []
    for g in sorted(set(etiquetas)):
        mascara = etiquetas == g
        centro = x[mascara].mean(axis=0)
        orden = np.argsort(-np.abs(centro))[:RASGOS_POR_GRUPO]

        rasgos = [
            {
                "caracteristica": _legible(columnas[i]),
                "columna": columnas[i],
                "desvios": round(float(centro[i]), 2),
                "direccion": "alto" if centro[i] > 0 else "bajo",
            }
            for i in orden
        ]

        sub = df[mascara]
        perfil: dict[str, Any] = {
            "grupo": int(g),
            "direcciones": int(mascara.sum()),
            "porcentaje": round(float(mascara.mean() * 100), 1),
            "rasgos": rasgos,
            # Cifras crudas, para que el perfil se pueda leer sin pensar en desvíos estándar.
            "mediana_eventos": int(np.expm1(sub["log1p_n_eventos"]).median()),
            "mediana_intentos_acceso": int(np.expm1(sub["log1p_login_intentos"]).median()),
            "pct_ejecuto_comandos": round(float(sub["ejecuto_comandos"].mean() * 100), 1),
            "pct_descargo_archivo": round(float(sub["descargo_archivo"].mean() * 100), 1),
            "pct_logro_acceso": round(
                float((np.expm1(sub["log1p_login_exitosos"]) > 0).mean() * 100), 1
            ),
        }
        perfil["nombre"], perfil["descripcion"] = nombrar(perfil)
        perfiles.append(perfil)

    # De mayor a menor gravedad, que es como se lee: primero quien entró.
    orden_gravedad = {"Intrusión efectiva": 0, "Fuerza bruta": 1, "Sondeo": 2}
    perfiles.sort(key=lambda p: orden_gravedad.get(str(p["nombre"]), 9))
    return perfiles


def load() -> dict[str, Any] | None:
    """Read the computed archetypes, or None when they have not been generated yet."""
    if not SALIDA.exists():
        return None
    parsed: dict[str, Any] = json.loads(SALIDA.read_text(encoding="utf-8"))
    return parsed


def main() -> None:
    if not ENTRADA.exists():
        raise SystemExit(f"Falta {ENTRADA}. Generalo con: make features")

    df = pd.read_parquet(ENTRADA)
    columnas = list(df.columns)
    print(f"  direcciones: {len(df):,}  |  características: {len(columnas)}".replace(",", "."))

    crudo = df.to_numpy(dtype=float)
    if not np.isfinite(crudo).all():
        raise SystemExit(
            "La tabla trae valores no finitos. Regeneralas con `make features` "
            "antes de agrupar: un infinito hace que el escalado deje de tener sentido."
        )

    # Escalar es imprescindible: `horas_activas` llega a 24 y los indicadores de comando valen 0 o
    # 1. Sin estandarizar, la distancia la domina la columna de mayor rango y el agrupamiento
    # termina midiendo una sola característica.
    x = StandardScaler().fit_transform(crudo)

    print("\n  eligiendo la cantidad de grupos")
    k, barrido = elegir_k(x)
    print(f"\n  elegido k={k}\n")

    km = KMeans(n_clusters=k, n_init=10, random_state=RANDOM_STATE).fit(x)
    perfiles = perfilar(df, x, km.labels_, columnas)

    for p in perfiles:
        n = f"{p['direcciones']:,}".replace(",", ".")
        print(f"  {p['nombre'].upper()} — {n} direcciones ({p['porcentaje']} %)")
        for r in p["rasgos"]:
            print(f"      {r['direccion']:>5}  {r['caracteristica']}  ({r['desvios']:+.2f} σ)")
        print(
            f"      mediana {p['mediana_eventos']} eventos · "
            f"{p['pct_ejecuto_comandos']} % ejecutó comandos · "
            f"{p['pct_descargo_archivo']} % descargó · "
            f"{p['pct_logro_acceso']} % logró acceso\n"
        )

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(
        json.dumps(
            {
                "direcciones_analizadas": len(df),
                "caracteristicas": len(columnas),
                "grupos": k,
                "criterio_k": "mejor silueta, prefiriendo el k menor dentro del 2 % del máximo",
                "barrido_k": barrido,
                "perfiles": perfiles,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"  Arquetipos -> {SALIDA}")


if __name__ == "__main__":
    main()
