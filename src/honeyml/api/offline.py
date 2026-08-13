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
from datetime import UTC, datetime
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
