"""Arquetipos de atacante: agrupamiento no supervisado de las direcciones observadas por conducta.

Las huellas de sesión ya agrupan ataques por secuencias de comandos byte a byte idénticas. Es un
criterio estricto, así que no agrupa nada por casualidad y cada familia que encuentra es real, pero
también significa que un carácter distinto parte una familia en dos, y no dice absolutamente nada de
las direcciones que nunca ejecutaron un comando.

Esto trabaja al revés: toma las 35 características de comportamiento calculadas por dirección y deja
que los datos decidan dónde caen los límites. Generaliza más allá de la coincidencia literal y cubre
todas las direcciones observadas, no solo las que llegaron a una consola.

Además llena un hueco que el conjunto de referencia no puede. UWF-ZeekData24 aporta etiquetas MITRE
pero es telemetría de flujos de red: bytes, paquetes, estado de conexión. Las nuestras son de
comportamiento: cuántas contraseñas se probaron, si se descargó un archivo, a qué hora, a qué ritmo.
Nada en el benchmark describe eso, así que nada en el benchmark puede etiquetarlo. El agrupamiento
no necesita etiquetas, y por eso encaja acá.

Qué no es esto. Los grupos son descriptivos, no verdad de campo. No hay una clave externa que diga
cuántos tipos de atacante existen, así que la cantidad de grupos es una elección hecha sobre un
criterio medible y declarada como tal. Los nombres son una capa de interpretación escrita después de
leer los perfiles, y se los rotula como interpretación en todos lados donde se muestran.
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

# Rango de k a evaluar. Por debajo de 3 el resultado no informa (siempre da "mucho" y "poco") y por
# encima de 8 los grupos se vuelven demasiado chicos para describirlos con honestidad.
KS = range(3, 9)

# La silueta crece con el cuadrado de los puntos: sobre 14.000 puntos son 200 millones de pares. Se
# calcula sobre una muestra, que es lo habitual y suficiente para comparar k entre sí.
MUESTRA_SILUETA = 5000

# Cuántas características definen a cada grupo en su perfil. Con 35 disponibles, mostrarlas todas
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
    """Nombra un arquetipo por su perfil, nunca por el número de grupo.

    KMeans no garantiza que la numeración se mantenga entre corridas, así que un nombre pegado al
    "grupo 2" se mudaría a otro conjunto de atacantes en la corrida siguiente sin que nadie se dé
    cuenta. Derivarlo del perfil mantiene el nombre atado a la conducta.

    Esta es la capa de interpretación, y es la única parte del módulo que no está medida.
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
        return f'usó "{col[4:]}"'
    return col


def elegir_k(x: np.ndarray) -> tuple[int, list[dict[str, Any]]]:
    """Elige la cantidad de grupos por silueta, y prefiere menos cuando la ganancia es marginal.

    La silueta mide cuánto mejor encaja cada punto en su propio grupo que en el más cercano. No es
    una verdad sino un criterio, pero es uno declarado, que es lo que importa: la alternativa es
    elegir un número porque el resultado quedaba lindo.
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
    """Describe cada grupo por las características que lo separan del resto de la población.

    La comparación es en el espacio estandarizado, así que un desvío se lee en desvíos estándar y
    características de escalas distintas se pueden ordenar entre sí.
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
    """Lee los arquetipos ya calculados, o None si todavía no se generaron."""
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

    # Escalar es imprescindible: `horas_activas` llega a 24 y los indicadores de comando valen cero
    # o uno. Sin estandarizar, la distancia la domina la columna de mayor rango y el agrupamiento
    # termina midiendo una sola característica.
    x = StandardScaler().fit_transform(crudo)

    print("\n  eligiendo la cantidad de grupos")
    k, barrido = elegir_k(x)
    print(f"\n  elegido k={k}\n")

    km = KMeans(n_clusters=k, n_init=10, random_state=RANDOM_STATE).fit(x)
    perfiles = perfilar(df, x, km.labels_, columnas)

    for p in perfiles:
        n = f"{p['direcciones']:,}".replace(",", ".")
        print(f"  {p['nombre'].upper()}: {n} direcciones ({p['porcentaje']} %)")
        for r in p["rasgos"]:
            print(
                f"      {r['direccion']:>5}  {r['caracteristica']}  ({r['desvios']:+.2f} desvíos)"
            )
        print(
            f"      mediana {p['mediana_eventos']} eventos, "
            f"{p['pct_ejecuto_comandos']} % ejecutó comandos, "
            f"{p['pct_descargo_archivo']} % descargó, "
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
