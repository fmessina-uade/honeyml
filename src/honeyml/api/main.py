"""FastAPI service behind the educational dashboard.

Sits between the browser and Elasticsearch so the search API is never exposed to the client, and
serves the annotated replay sessions. Runs next to Elasticsearch on the private network; reached
through the SSH tunnel, never published.

Usage:
    uvicorn honeyml.api.main:app --reload --port 8000
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.error import URLError

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from ..education import fingerprints, password_index
from ..features import arquetipos
from . import offline, queries

REPLAY_FILE = Path("data/processed/replay_sessions.json")


def _live_or_frozen[T](fetch: Callable[[], T], key: str) -> T:
    """Run a live query, falling back to the frozen snapshot when Elasticsearch is unreachable.

    Only connection errors fall back. A malformed query is a bug and must surface as one rather
    than be masked by stale data that happens to be on disk.
    """
    try:
        return fetch()
    except (URLError, ConnectionError, TimeoutError) as exc:
        frozen = offline.load()
        if frozen is None or key not in frozen:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Elasticsearch no responde y no hay snapshot congelado. "
                    "Levantá el stack con 'make elastic-dev-up', o generá el snapshot "
                    "con 'make snapshot' mientras esté disponible."
                ),
            ) from exc
        value: T = frozen[key]
        return value


app = FastAPI(
    title="HoneyML API",
    description="Telemetría normalizada del honeypot para el panel educativo",
    version="0.1.0",
)

# the dashboard runs on the Vite dev server during development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, Any]:
    """Reports whether the data being served is live or comes from the frozen snapshot."""
    try:
        queries.overview()
        return {"status": "ok", "mode": "live"}
    except (URLError, ConnectionError, TimeoutError):
        frozen = offline.load()
        if frozen is None:
            return {"status": "down", "mode": "none"}
        return {
            "status": "ok",
            "mode": "snapshot",
            "generated_at": frozen.get("generated_at", ""),
        }


@app.get("/api/overview")
def get_overview() -> dict[str, Any]:
    """Headline counters."""
    return _live_or_frozen(queries.overview, "overview")


@app.get("/api/timeline")
def get_timeline(
    interval: str = "day",
    sensor: str | None = None,
    desde: str | None = None,
    hasta: str | None = None,
) -> list[dict[str, Any]]:
    """Events over time, optionally narrowed by sensor and date range.

    With Elasticsearch down the snapshot answers what it can compute from its daily buckets —a date
    range, a sensor, a weekly rollup— and refuses the hourly view, whose buckets it never stored.
    The refusal is a 503 with the reason in it, not a stack trace: the panel shows the reason, and a
    filter that cannot be honoured says so instead of leaving the unfiltered chart on screen.
    """
    filtrado = bool(sensor or desde or hasta) or interval != "day"
    if not filtrado:
        return _live_or_frozen(queries.timeline, "timeline")

    try:
        return queries.timeline(interval=interval, sensor=sensor, desde=desde, hasta=hasta)
    except (URLError, ConnectionError, TimeoutError) as exc:
        congelado = offline.timeline(interval=interval, sensor=sensor, desde=desde, hasta=hasta)
        if congelado is not None:
            return congelado
        raise HTTPException(
            status_code=503,
            detail=(
                "La vista por hora necesita Elasticsearch: el respaldo congelado guarda un punto "
                "por día y esas horas nunca se almacenaron. Las vistas por día y por semana sí "
                "funcionan sobre el respaldo."
            ),
        ) from exc


@app.get("/api/credentials")
def get_credentials(size: int = 10) -> dict[str, list[dict[str, Any]]]:
    """Most attempted users and passwords."""
    return _live_or_frozen(lambda: queries.top_credentials(size=size), "credentials")


@app.get("/api/commands")
def get_commands(size: int = 12) -> list[dict[str, Any]]:
    """Most executed commands."""
    return _live_or_frozen(lambda: queries.top_commands(size=size), "commands")


@app.get("/api/protocol-detail")
def get_protocol_detail() -> list[dict[str, Any]]:
    """Per-protocol traffic on the multiprotocol sensor, with distinct sources."""
    return _live_or_frozen(queries.protocol_detail, "protocol_detail")


@app.get("/api/protocols")
def get_protocols() -> list[dict[str, Any]]:
    """Attack surface by protocol."""
    return _live_or_frozen(queries.protocols, "protocols")


@app.get("/api/stages")
def get_stages() -> list[dict[str, Any]]:
    """Events per stage of the intrusion."""
    return _live_or_frozen(queries.attack_stages, "stages")


@app.get("/api/hourly")
def get_hourly() -> list[dict[str, Any]]:
    """Attacks by hour of day: shows the absence of a human rhythm."""
    return _live_or_frozen(queries.hourly, "hourly")


@app.get("/api/snapshot")
def get_snapshot() -> dict[str, Any]:
    """Everything at once: one round trip for the dashboard's initial load."""
    try:
        return queries.snapshot()
    except (URLError, ConnectionError, TimeoutError) as exc:
        frozen = offline.load()
        if frozen is None:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Elasticsearch no responde y no hay snapshot congelado. "
                    "Levantá el stack con 'make elastic-dev-up', o generá el snapshot "
                    "con 'make snapshot' mientras esté disponible."
                ),
            ) from exc
        return frozen


@app.get("/api/weekly-rhythm")
def get_weekly_rhythm() -> dict[str, Any]:
    """Events by day of week and hour of day: whether there is any human rhythm at all."""
    return _live_or_frozen(queries.weekly_rhythm, "weekly_rhythm")


@app.get("/api/geography")
def get_geography() -> dict[str, Any]:
    """Origin of the attacks by country and by autonomous system."""
    return _live_or_frozen(queries.geography, "geography")


@app.get("/api/archetypes")
def get_archetypes() -> dict[str, Any]:
    """Behavioural groups of the observed sources.

    Served from the precomputed file and not from a live query: the grouping runs over the whole
    feature table and takes seconds, which is fine as a batch step and not on a page load.
    """
    data = arquetipos.load()
    if data is None:
        raise HTTPException(
            status_code=503,
            detail="Faltan los arquetipos. Generalos con: make arquetipos",
        )
    return data


@app.get("/api/fingerprints")
def get_fingerprints() -> dict[str, Any]:
    """Families of sessions running a byte-identical command sequence."""
    data = fingerprints.load()
    if data is None:
        raise HTTPException(
            status_code=503,
            detail="Faltan las familias. Generalas con: make fingerprints",
        )
    return data


@app.get("/api/password-check")
def check_password(prefix: str) -> dict[str, Any]:
    """k-anonymity lookup: takes a hash prefix, never a password.

    See honeyml/education/password_index for why the comparison is split this way.
    """
    if not prefix or len(prefix) > 8 or not all(c in "0123456789abcdefABCDEF" for c in prefix):
        raise HTTPException(status_code=400, detail="Prefijo inválido.")
    index = password_index.load()
    if index is None:
        raise HTTPException(
            status_code=503,
            detail="Falta el índice de contraseñas. Generalo con: make passwords",
        )
    return password_index.lookup(prefix, index)


@app.get("/api/replays")
def get_replays() -> list[dict[str, Any]]:
    """Annotated attack sessions for the step by step replay."""
    if not REPLAY_FILE.exists():
        raise HTTPException(
            status_code=503,
            detail="Faltan las sesiones. Generalas con: python -m honeyml.education.session_replay",
        )
    data: list[dict[str, Any]] = json.loads(REPLAY_FILE.read_text(encoding="utf-8"))
    return data
