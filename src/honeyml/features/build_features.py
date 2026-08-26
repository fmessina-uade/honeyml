"""Per-source-IP time and frequency features from Cowrie telemetry.

The source IP is the unit of analysis: each attacker boils down to a vector of volume, auth,
timing and behaviour features, to train the supervised model later. Works off the ECS parquet
(data/processed/honeypot_events.parquet). Feature names and output stay in Spanish (thesis).

Feature-engineering choices:
- count/rate features are heavy-tailed, so log1p to tame the skew.
- the event rate uses a span floor (1 min) so bursts (span ~ 0) don't blow it up.
- prune redundant features (high correlation / multicollinearity).
- scaling is NOT done here: it belongs in the modeling Pipeline, fit on train only, so we don't
  leak test stats into training (data leakage).

Usage:
    python -m src.honeyml.features.build_features
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

PARQUET_IN = Path("data/processed/honeypot_events.parquet")
PARQUET_OUT = Path("data/processed/features_por_ip.parquet")
LOCAL_IP = "127.0.0.1"

# typical post-exploitation tools; seeing them is a signal of intent
COMMAND_KEYWORDS = [
    "wget",
    "curl",
    "chmod",
    "busybox",
    "uname",
    "cat",
    "rm",
    "cd",
    "echo",
    "tftp",
    "sh",
    "kill",
    "ps",
    "crontab",
    "nproc",
    "free",
    "history",
]

# heavy-tailed count/rate features, get a log1p
SKEWED = [
    "n_eventos",
    "n_sesiones",
    "eventos_por_sesion",
    "login_intentos",
    "login_fallidos",
    "login_exitosos",
    "usuarios_distintos",
    "pass_distintas",
    "n_comandos",
    "span_horas",
    "interarribo_medio_s",
    "eventos_por_hora",
    "dur_sesion_media_s",
]

MIN_SPAN_H = 1 / 60  # 1-minute floor for the events-per-hour rate


def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    df = df[df["source.ip"] != LOCAL_IP].dropna(subset=["source.ip"]).copy()
    df["@timestamp"] = pd.to_datetime(df["@timestamp"], utc=True)
    df["is_login"] = df["event.action"].eq("login")
    df["is_fail"] = df["is_login"] & df["event.outcome"].eq("failure")
    df["is_success"] = df["is_login"] & df["event.outcome"].eq("success")
    df["is_command"] = df["event.action"].str.startswith("command", na=False)
    df["is_download"] = df["event.action"].eq("file-download")
    df["hour"] = df["@timestamp"].dt.hour
    df["is_ssh"] = df["network.protocol"].eq("ssh")
    return df


def _interarrival(df: pd.DataFrame) -> pd.Series:
    """Mean time between consecutive events (seconds) per IP."""
    d = df.sort_values(["source.ip", "@timestamp"])
    delta = d.groupby("source.ip")["@timestamp"].diff().dt.total_seconds()
    return delta.groupby(d["source.ip"]).mean()


def _command_flags(df: pd.DataFrame, index: pd.Index) -> pd.DataFrame:
    """Binary per-IP flags: whether each COMMAND_KEYWORDS tool shows up."""
    cmds = df.loc[df["is_command"], ["source.ip", "process.command_line"]].dropna()
    cmds["cmd"] = cmds["process.command_line"].str.lower()
    out = {}
    for kw in COMMAND_KEYWORDS:
        has_kw = cmds.assign(f=cmds["cmd"].str.contains(rf"\b{kw}\b", regex=True))
        flags = has_kw.groupby("source.ip")["f"].max()
        out[f"cmd_{kw}"] = flags.reindex(index).fillna(0).astype(int)
    return pd.DataFrame(out, index=index)


def prune_correlated(
    feats: pd.DataFrame, threshold: float = 0.95
) -> tuple[pd.DataFrame, list[str]]:
    """Drop one feature from each pair with abs correlation > threshold (multicollinearity)."""
    corr = feats.corr().abs()
    upper = corr.where(np.triu(np.ones(corr.shape), k=1).astype(bool))
    to_drop = [c for c in upper.columns if (upper[c] > threshold).any()]
    return feats.drop(columns=to_drop), to_drop


def build_features(df: pd.DataFrame, prune: bool = True) -> pd.DataFrame:
    df = _prepare(df)
    g = df.groupby("source.ip")

    feats = pd.DataFrame(
        {
            # volume / frequency
            "n_eventos": g.size(),
            "n_sesiones": g["cowrie.session"].nunique(),
            # El denominador lleva piso 1. Una dirección puede tener eventos y ninguna sesión
            # identificada —los de Dionaea no traen identificador de sesión, y algunos de Cowrie
            # tampoco—, y ahí la división daba infinito: 3.077 de 14.173 direcciones, el 21,7 %.
            # Un infinito no se nota en un promedio (lo vuelve infinito, que se lee como error de
            # otra cosa) pero rompe cualquier escalado o modelo que consuma la tabla.
            # Con piso 1, una ráfaga sin sesión cuenta como una sola sesión, que es la lectura
            # razonable: hubo actividad, no se pudo segmentar.
            "eventos_por_sesion": g.size() / g["cowrie.session"].nunique().clip(lower=1),
            # auth
            "login_intentos": g["is_login"].sum(),
            "login_fallidos": g["is_fail"].sum(),
            "login_exitosos": g["is_success"].sum(),
            "usuarios_distintos": g["user.name"].nunique(),
            "pass_distintas": g["cowrie.password"].nunique(),
            # behaviour
            "n_comandos": g["is_command"].sum(),
            "ejecuto_comandos": (g["is_command"].sum() > 0).astype(int),
            "descargo_archivo": (g["is_download"].sum() > 0).astype(int),
            "ratio_ssh": g["is_ssh"].mean(),
            # timing
            "span_horas": (g["@timestamp"].max() - g["@timestamp"].min()).dt.total_seconds() / 3600,
            "horas_activas": g["hour"].nunique(),
            "ratio_nocturno": g["hour"].apply(lambda h: (h < 6).mean()),
            "dur_sesion_media_s": g["event.duration"].mean() / 1e9,
        }
    )
    # derived features + disambiguate the zero-filled ratios
    feats["tuvo_logins"] = (feats["login_intentos"] > 0).astype(int)
    feats["ratio_fallo_login"] = (feats["login_fallidos"] / feats["login_intentos"]).fillna(0)
    feats["interarribo_medio_s"] = _interarrival(df).reindex(feats.index).fillna(0)
    # rate with a span floor so a burst of events in seconds doesn't explode it
    span_floor = feats["span_horas"].clip(lower=MIN_SPAN_H)
    feats["eventos_por_hora"] = feats["n_eventos"] / span_floor

    feats = feats.fillna(0)

    # log1p the heavy-tailed features (cuts skew, keeps the ordering)
    for col in SKEWED:
        feats[col] = np.log1p(feats[col])
    feats = feats.rename(columns={col: f"log1p_{col}" for col in SKEWED})

    # command flags (binary, not transformed or pruned)
    feats = feats.join(_command_flags(df, feats.index))

    if prune:
        feats, dropped = prune_correlated(feats)
        if dropped:
            print(f"Features podadas por correlación >0.95: {dropped}")

    return feats.round(4)


def main() -> None:
    if not PARQUET_IN.exists():
        raise SystemExit(f"Falta {PARQUET_IN}. Extraé primero con es_loader (ES levantado).")
    df = pd.read_parquet(PARQUET_IN)
    feats = build_features(df)
    PARQUET_OUT.parent.mkdir(parents=True, exist_ok=True)
    feats.to_parquet(PARQUET_OUT)
    print(f"Features por IP: {feats.shape[0]:,} IPs x {feats.shape[1]} features")
    print(f"Guardado en {PARQUET_OUT}\n")
    print("Columnas:")
    print("  " + ", ".join(feats.columns))
    print("\nEstadísticas (features no-flag):")
    non_flags = [c for c in feats.columns if not c.startswith("cmd_")]
    print(feats[non_flags].describe().round(2).T.to_string())


if __name__ == "__main__":
    main()
