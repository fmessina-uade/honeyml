"""Análisis exploratorio de la telemetría de honeypots normalizada a ECS (Fase 2, Obj. 2).

Cubre las tareas del Gantt: limpieza (duplicados, nulos, outliers), distribución de clases de
ataque y matriz de correlación. Trabaja sobre el parquet extraído de Elasticsearch
(data/processed/honeypot_events.parquet) y guarda figuras en reports/figures/.

Uso:
    python -m src.honeyml.eda.honeypot_eda
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # backend sin display, para guardar figuras
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

PARQUET = Path("data/processed/honeypot_events.parquet")
FIG_DIR = Path("reports/figures")

# Mapeo de acciones de Cowrie a etapas de ataque (taxonomía simplificada, previa a MITRE ATT&CK,
# que se aplica formalmente sobre UWF-ZeekData24 para el modelo supervisado del Obj. 4).
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


LOCAL_IP = "127.0.0.1"  # healthchecks del propio contenedor (no son tráfico de atacantes)


def load() -> pd.DataFrame:
    if not PARQUET.exists():
        raise SystemExit(f"Falta {PARQUET}. Extraé primero con es_loader (ES levantado).")
    return pd.read_parquet(PARQUET)


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Aplica y reporta la limpieza; devuelve el DataFrame depurado."""
    print("\n" + "=" * 70)
    print("LIMPIEZA DE DATOS")
    print("=" * 70)
    print(f"Eventos crudos:             {len(df):,}")

    # 1. Healthchecks locales: conexiones del contenedor a sí mismo, no son ataques.
    hc = (df["source.ip"] == LOCAL_IP).sum()
    df = df[df["source.ip"] != LOCAL_IP].copy()
    print(f"Healthchecks 127.0.0.1:     -{hc:,} eliminados")

    # 2. Duplicados exactos residuales (el pipeline ya deduplica por fingerprint/document_id).
    dup = df.duplicated().sum()
    df = df.drop_duplicates().reset_index(drop=True)
    print(f"Duplicados exactos:         -{dup:,} eliminados")

    print(f"Eventos de ataque limpios:  {len(df):,}")
    print(f"Rango temporal:             {df['@timestamp'].min()}  ->  {df['@timestamp'].max()}")

    # Nulos: esperables y semánticos (cada tipo de evento puebla distintos campos).
    print("\nNulos por campo (%):")
    nulls = (df.isna().mean() * 100).round(1).sort_values(ascending=False)
    for col, pct in nulls.items():
        print(f"  {col:<24} {pct:5.1f}%")

    # Outliers de duración de sesión (solo eventos session-closed con duración).
    dur = df.loc[df["event.duration"].notna(), "event.duration"] / 1e9  # ns -> s
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
    print("\n" + "=" * 70)
    print("DISTRIBUCIÓN DE CLASES DE ATAQUE")
    print("=" * 70)

    print("\nPor acción (event.action):")
    for action, n in df["event.action"].value_counts().head(15).items():
        print(f"  {n:>7,}  {action}")

    df = df.copy()
    df["stage"] = df["event.action"].map(STAGE_BY_ACTION).fillna("Otro")
    stages = df["stage"].value_counts()
    print("\nPor etapa de ataque (taxonomía simplificada):")
    for stage, n in stages.items():
        print(f"  {n:>7,}  ({n / len(df) * 100:4.1f}%)  {stage}")

    # Figura: distribución por etapa
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    stages.sort_values().plot.barh(ax=ax, color="#D4860A")
    ax.set_title("Distribución de eventos por etapa de ataque (Cowrie)")
    ax.set_xlabel("Eventos")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "distribucion_clases.png", dpi=120)
    plt.close(fig)
    print(f"\n  -> figura: {FIG_DIR / 'distribucion_clases.png'}")


def attacker_summary(df: pd.DataFrame) -> None:
    print("\n" + "=" * 70)
    print("PERFIL DE ATACANTES")
    print("=" * 70)
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
    """Matriz de correlación sobre features agregadas por IP (base del feature engineering)."""
    print("\n" + "=" * 70)
    print("MATRIZ DE CORRELACIÓN (features agregadas por IP)")
    print("=" * 70)

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
    print(f"\n  -> figura: {FIG_DIR / 'matriz_correlacion.png'}")

    feats.to_parquet("data/processed/features_por_ip.parquet")
    print("  -> features: data/processed/features_por_ip.parquet")


def main() -> None:
    sns.set_theme(style="whitegrid")
    df = clean(load())
    class_distribution(df)
    attacker_summary(df)
    correlation_matrix(df)
    print("\nEDA completo.\n")


if __name__ == "__main__":
    main()
