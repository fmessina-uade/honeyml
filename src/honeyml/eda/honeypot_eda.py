"""Análisis exploratorio de la telemetría de los honeypots ya normalizada a ECS.

Hace la limpieza (duplicados, nulos, valores atípicos), el reparto por clase de ataque y la matriz
de correlación. Lee el parquet extraído de Elasticsearch (data/processed/honeypot_events.parquet) y
escribe las figuras en reports/figures/.

Uso:
    python -m src.honeyml.eda.honeypot_eda
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # backend sin ventana: acá solo se guardan figuras
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from .. import redes

PARQUET = Path("data/processed/honeypot_events.parquet")
FIG_DIR = Path("reports/figures")

# Acciones de Cowrie agrupadas por etapa del ataque. Es una taxonomía gruesa, anterior a las
# etiquetas MITRE ATT&CK de verdad, que salen de UWF-ZeekData24 para el modelo supervisado.
STAGE_BY_ACTION = {
    "session-connect": "Reconocimiento",
    "session-closed": "Reconocimiento",
    "cowrie.client.version": "Reconocimiento",
    "cowrie.client.kex": "Reconocimiento",
    "cowrie.client.fingerprint": "Reconocimiento",
    "login": "Acceso por credenciales",
    "command-input": "Ejecución",
    "command-failed": "Ejecución",
    "command-success": "Ejecución",
    "file-download": "Descarga de payload",
    "file-upload": "Descarga de payload",
    "direct-tcpip-request": "Pivoting / túnel",
}


def load() -> pd.DataFrame:
    if not PARQUET.exists():
        raise SystemExit(f"Falta {PARQUET}. Extraé primero con es_loader (ES levantado).")
    return pd.read_parquet(PARQUET)


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Hace la limpieza, la informa por pantalla y devuelve el DataFrame limpio."""
    print("\nLimpieza de datos")
    print(f"Eventos crudos:             {len(df):,}")

    # los orígenes internos (healthcheck de los contenedores y pruebas propias) no son ataques
    externa = redes.mascara_externa(df["source.ip"])
    internos = int((~externa).sum())
    df = df[externa].copy()
    print(f"Orígenes internos:          -{internos:,} eliminados")

    # duplicados exactos que se le hayan escapado al pipeline, que ya deduplica por document_id
    dup = df.duplicated().sum()
    df = df.drop_duplicates().reset_index(drop=True)
    print(f"Duplicados exactos:         -{dup:,} eliminados")

    print(f"Eventos de ataque limpios:  {len(df):,}")
    print(f"Rango temporal:             {df['@timestamp'].min()} a {df['@timestamp'].max()}")

    # los nulos son esperables y significan algo: cada tipo de evento llena campos distintos
    print("\nNulos por campo (%):")
    nulls = (df.isna().mean() * 100).round(1).sort_values(ascending=False)
    for col, pct in nulls.items():
        print(f"  {col:<24} {pct:5.1f}%")

    # atípicos de duración de sesión; solo los eventos de cierre traen duración, en nanosegundos
    dur = df.loc[df["event.duration"].notna(), "event.duration"] / 1e9
    if len(dur):
        q1, q3 = dur.quantile(0.25), dur.quantile(0.75)
        iqr = q3 - q1
        upper = q3 + 1.5 * iqr
        outliers = (dur > upper).sum()
        print(
            f"\nDuración de sesión (s):     mediana={dur.median():.1f}  "
            f"p95={dur.quantile(0.95):.1f}  máx={dur.max():.1f}"
        )
        print(f"Outliers (>{upper:.1f}s, IQR):  {outliers:,} ({outliers / len(dur) * 100:.2f}%)")

    return df


def class_distribution(df: pd.DataFrame) -> None:
    print("\nDistribución de clases de ataque")

    print("\nPor acción (event.action):")
    for action, n in df["event.action"].value_counts().head(15).items():
        print(f"  {n:>7,}  {action}")

    df = df.copy()
    df["stage"] = df["event.action"].map(STAGE_BY_ACTION).fillna("Otro")
    stages = df["stage"].value_counts()
    print("\nPor etapa de ataque (taxonomía simplificada):")
    for stage, n in stages.items():
        print(f"  {n:>7,}  ({n / len(df) * 100:4.1f}%)  {stage}")

    # figura: eventos por etapa del ataque
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    stages.sort_values().plot.barh(ax=ax, color="#D4860A")
    ax.set_title("Distribución de eventos por etapa de ataque (Cowrie)")
    ax.set_xlabel("Eventos")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "distribucion_clases.png", dpi=120)
    plt.close(fig)
    print(f"\n  Figura en {FIG_DIR / 'distribucion_clases.png'}")


def attacker_summary(df: pd.DataFrame) -> None:
    print("\nPerfil de atacantes")
    ext = df[df["source.ip"].notna()]
    print(f"IPs origen únicas:          {ext['source.ip'].nunique():,}")
    print("\nTop 10 IPs por volumen:")
    for ip, n in ext["source.ip"].value_counts().head(10).items():
        print(f"  {n:>7,}  {ip}")
    print("\nTop 10 credenciales (usuario):")
    for u, n in df["user.name"].dropna().value_counts().head(10).items():
        print(f"  {n:>7,}  {u}")
    print("\nTop 10 contraseñas:")
    for p, n in df["cowrie.password"].dropna().value_counts().head(10).items():
        print(f"  {n:>7,}  {p}")


def correlation_matrix(df: pd.DataFrame) -> None:
    """Matriz de correlación por IP, el punto de partida de la ingeniería de características."""
    print("\nMatriz de correlación (características agregadas por IP)")

    df = df.copy()
    df["is_login_fail"] = df["event.outcome"].eq("failure") & df["event.action"].eq("login")
    df["is_login_ok"] = df["event.outcome"].eq("success") & df["event.action"].eq("login")
    df["is_command"] = df["event.action"].str.startswith("command", na=False)

    g = df.groupby("source.ip")
    feats = pd.DataFrame(
        {
            "eventos": g.size(),
            "sesiones": g["cowrie.session"].nunique(),
            "logins_fallidos": g["is_login_fail"].sum(),
            "logins_ok": g["is_login_ok"].sum(),
            "comandos": g["is_command"].sum(),
            "user_distintos": g["user.name"].nunique(),
            "pass_distintas": g["cowrie.password"].nunique(),
        }
    )
    feats = feats[feats.index.notna()]
    print(f"IPs (filas):                {len(feats):,}")
    print("\nEstadísticas de las features:")
    print(feats.describe().round(1).to_string())

    corr = feats.corr()
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7, 6))
    sns.heatmap(corr, annot=True, fmt=".2f", cmap="RdYlGn", center=0, ax=ax, square=True)
    ax.set_title("Correlación de features por IP origen (Cowrie)")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "matriz_correlacion.png", dpi=120)
    plt.close(fig)
    print(f"\n  Figura en {FIG_DIR / 'matriz_correlacion.png'}")

    feats.to_parquet("data/processed/features_por_ip.parquet")
    print("  Características en data/processed/features_por_ip.parquet")


def main() -> None:
    sns.set_theme(style="whitegrid")
    df = clean(load())
    class_distribution(df)
    attacker_summary(df)
    correlation_matrix(df)
    print("\nEDA completo.\n")


if __name__ == "__main__":
    main()
