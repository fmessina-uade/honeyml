"""FastAPI service behind the educational dashboard.

Sits between the browser and Elasticsearch so the search API is never exposed to the client, and
serves the annotated replay sessions. Runs next to Elasticsearch on the private network; reached
through the SSH tunnel, never published.

Usage:
    uvicorn honeyml.api.main:app --reload --port 8000
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import queries

REPLAY_FILE = Path("data/processed/replay_sessions.json")

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
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/overview")
def get_overview() -> dict[str, Any]:
    """Headline counters."""
    return queries.overview()


@app.get("/api/timeline")
def get_timeline(interval: str = "1d") -> list[dict[str, Any]]:
    """Events over time."""
    return queries.timeline(interval=interval)


@app.get("/api/credentials")
def get_credentials(size: int = 10) -> dict[str, list[dict[str, Any]]]:
    """Most attempted users and passwords."""
    return queries.top_credentials(size=size)


@app.get("/api/commands")
def get_commands(size: int = 12) -> list[dict[str, Any]]:
    """Most executed commands."""
    return queries.top_commands(size=size)


@app.get("/api/protocols")
def get_protocols() -> list[dict[str, Any]]:
    """Attack surface by protocol."""
    return queries.protocols()


@app.get("/api/stages")
def get_stages() -> list[dict[str, Any]]:
    """Events per stage of the intrusion."""
    return queries.attack_stages()


@app.get("/api/snapshot")
def get_snapshot() -> dict[str, Any]:
    """Everything at once: one round trip for the dashboard's initial load."""
    return queries.snapshot()


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
