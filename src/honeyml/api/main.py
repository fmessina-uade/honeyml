"""Servicio FastAPI detrás del panel educativo.

Se pone entre el navegador y Elasticsearch para que la API de búsqueda nunca quede expuesta al
cliente, y además sirve las sesiones anotadas del replay. Corre al lado de Elasticsearch en la red
privada y se alcanza por el túnel SSH, nunca publicado.

Uso:
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
    """Corre la consulta en vivo y cae al respaldo congelado si no se alcanza a Elasticsearch.

    Solo caen al respaldo los errores de conexión. Una consulta mal armada es un error nuestro y
    tiene que aparecer como tal, no quedar tapada por datos viejos que justo estaban en disco.
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

# durante el desarrollo el panel corre en el servidor de Vite
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, Any]:
    """Informa si lo que se está sirviendo es en vivo o sale del respaldo congelado."""
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
    """Eventos en el tiempo, con filtro opcional por sensor y por rango de fechas.

    Con Elasticsearch abajo, el respaldo contesta lo que puede calcular desde sus cubos diarios (un
    rango, un sensor, un agrupado semanal) y rechaza la vista por hora, cuyos cubos nunca guardó.
    El rechazo es un 503 con el motivo adentro y no una traza: el panel muestra ese motivo, así un
    filtro que no se puede cumplir lo dice, en vez de dejar el gráfico sin filtrar en pantalla.
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
    """Los usuarios y contraseñas más intentados."""
    return _live_or_frozen(lambda: queries.top_credentials(size=size), "credentials")


@app.get("/api/commands")
def get_commands(size: int = 12) -> list[dict[str, Any]]:
    """Los comandos más ejecutados."""
    return _live_or_frozen(lambda: queries.top_commands(size=size), "commands")


@app.get("/api/protocol-detail")
def get_protocol_detail() -> list[dict[str, Any]]:
    """Tráfico por protocolo en el sensor multiprotocolo, con direcciones distintas."""
    return _live_or_frozen(queries.protocol_detail, "protocol_detail")


@app.get("/api/protocols")
def get_protocols() -> list[dict[str, Any]]:
    """Superficie de ataque por protocolo."""
    return _live_or_frozen(queries.protocols, "protocols")


@app.get("/api/stages")
def get_stages() -> list[dict[str, Any]]:
    """Eventos por etapa de la intrusión."""
    return _live_or_frozen(queries.attack_stages, "stages")


@app.get("/api/hourly")
def get_hourly() -> list[dict[str, Any]]:
    """Ataques por hora del día: muestra que no hay ritmo humano detrás."""
    return _live_or_frozen(queries.hourly, "hourly")


@app.get("/api/snapshot")
def get_snapshot() -> dict[str, Any]:
    """Todo junto: un solo viaje para la carga inicial del panel."""
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
    """Eventos por día de la semana y hora: si hay algún ritmo humano, acá se vería."""
    return _live_or_frozen(queries.weekly_rhythm, "weekly_rhythm")


@app.get("/api/geography")
def get_geography() -> dict[str, Any]:
    """Origen de los ataques por país y por sistema autónomo."""
    return _live_or_frozen(queries.geography, "geography")


@app.get("/api/archetypes")
def get_archetypes() -> dict[str, Any]:
    """Grupos de conducta de las direcciones observadas.

    Sale del archivo precalculado y no de una consulta en vivo: el agrupamiento corre sobre toda la
    tabla de características y tarda segundos, que está bien como paso por lotes y no en una carga
    de página.
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
    """Familias de sesiones que corren una secuencia de comandos idéntica byte a byte."""
    data = fingerprints.load()
    if data is None:
        raise HTTPException(
            status_code=503,
            detail="Faltan las familias. Generalas con: make fingerprints",
        )
    return data


@app.get("/api/password-check")
def check_password(prefix: str) -> dict[str, Any]:
    """Consulta con k-anonimato: recibe un prefijo de hash, nunca una contraseña.

    En honeyml/education/password_index está el porqué de partir así la comparación.
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
    """Sesiones de ataque anotadas, para el replay paso a paso."""
    if not REPLAY_FILE.exists():
        raise HTTPException(
            status_code=503,
            detail="Faltan las sesiones. Generalas con: python -m honeyml.education.session_replay",
        )
    data: list[dict[str, Any]] = json.loads(REPLAY_FILE.read_text(encoding="utf-8"))
    return data
