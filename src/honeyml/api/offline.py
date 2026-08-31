"""Freeze the dashboard's telemetry to a file so the panel works without Elasticsearch.

The stack is heavy and only runs on demand. Two situations need the data without it: taking the
screenshots for the report, and showing the panel on a machine that is not the development one.
Both are worse moments than usual to discover that the dashboard needs a running cluster.

The API reads this file automatically when Elasticsearch is unreachable, and reports which mode it
is serving so the panel can say so instead of passing stale numbers off as live.

Usage:
    python -m honeyml.api.offline
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from . import queries

OUT_FILE = Path("data/processed/snapshot.json")


def build(es_url: str = queries.ES_URL) -> dict[str, Any]:
    """Query everything the dashboard needs and stamp it with the time it was taken."""
    data = queries.snapshot(es_url)
    data["generated_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    return data


def load() -> dict[str, Any] | None:
    """Read the frozen snapshot, or None when it was never generated."""
    if not OUT_FILE.exists():
        return None
    parsed: dict[str, Any] = json.loads(OUT_FILE.read_text(encoding="utf-8"))
    return parsed


def timeline(
    interval: str = "day",
    sensor: str | None = None,
    desde: str | None = None,
    hasta: str | None = None,
) -> list[dict[str, Any]] | None:
    """Answer a filtered timeline from the frozen snapshot, or None when it honestly cannot.

    The snapshot stores one bucket per day with its per-sensor breakdown, which is enough to narrow
    a date range, pick a sensor, or roll days up into weeks — all of it arithmetic over data that is
    already there. The hourly view is the one thing it cannot reconstruct: those buckets were never
    stored, and no amount of regrouping days will invent them.

    Returning None for that case rather than an approximation is the point. Before this existed the
    request failed with a stack trace, the panel swallowed the error, and the chart went on showing
    the *unfiltered* series underneath controls that said "last day" — a wrong answer wearing the
    costume of a right one.
    """
    datos = load()
    if datos is None or interval == "hour":
        return None

    dias: list[dict[str, Any]] = datos.get("timeline") or []
    # El panel manda el fin de día como "2026-08-25T23:59:59"; acá se compara contra una fecha.
    d0 = (desde or "")[:10]
    d1 = (hasta or "")[:10]

    filas: list[dict[str, Any]] = []
    for d in dias:
        fecha = str(d.get("date", ""))[:10]
        if d0 and fecha < d0:
            continue
        if d1 and fecha > d1:
            continue

        if sensor:
            # Con un sensor elegido, el total pasa a ser el de ese sensor. Dejar el `count` original
            # mostraría la barra completa bajo una etiqueta que dice lo contrario.
            n = int(d.get(sensor, 0))
            filas.append({"date": fecha, "count": n, sensor: n})
        else:
            filas.append({**d, "date": fecha})

    if interval != "week":
        return filas
    return _por_semana(filas)


def _por_semana(dias: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Roll daily buckets up into weeks starting on Monday, as Elasticsearch labels them.

    Same key as `calendar_interval: week` so that switching between live and frozen does not move
    the bars sideways by a few days.
    """
    semanas: dict[str, dict[str, Any]] = {}
    for d in dias:
        try:
            dia = date.fromisoformat(str(d["date"])[:10])
        except ValueError:
            continue
        lunes = (dia - timedelta(days=dia.weekday())).isoformat()

        acumulado = semanas.setdefault(lunes, {"date": lunes, "count": 0})
        for clave, valor in d.items():
            if clave == "date" or not isinstance(valor, int):
                continue
            acumulado[clave] = int(acumulado.get(clave, 0)) + valor
    return [semanas[k] for k in sorted(semanas)]


def main() -> None:
    data = build()
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    ov = data["overview"]
    size_kb = OUT_FILE.stat().st_size / 1024
    print(f"Snapshot congelado -> {OUT_FILE} ({size_kb:.0f} KB)")
    print(f"  {ov['events']:,} eventos, {ov['unique_ips']:,} direcciones".replace(",", "."))
    print(f"  ventana {ov['first_event'][:10]} a {ov['last_event'][:10]}")
    print(f"  tomado {data['generated_at']}")
    print("\nEl panel ahora funciona sin Elasticsearch levantado.")


if __name__ == "__main__":
    main()
