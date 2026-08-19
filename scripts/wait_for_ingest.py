"""Block until the ingestion pipeline has caught up with the logs on disk.

Why this exists: `make refresh` pulls fresh logs and then regenerates every derived artifact. The
collector picks up the new lines on its own, but it takes a while. Without this wait, the
artifacts would be rebuilt from a half-ingested index and would disagree with each other — the
consolidated table would hold one figure and the frozen snapshot another.

The signal is the document count going quiet: once it stops growing for a few consecutive checks,
the collector has drained what it had. That is more reliable than comparing against the line count
of the logs, because the pipeline legitimately drops events (the sensors' own health checks) and
the two numbers are not meant to match.

Usage:
    python scripts/wait_for_ingest.py
    python scripts/wait_for_ingest.py --timeout 900
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

ES_URL = "http://localhost:9200"
INDEX = "honeypot-*"
# how many identical readings mean "drained" — one alone can land between two batches
STABLE_CHECKS = 3
POLL_SECONDS = 10


def count(es_url: str, index: str) -> int | None:
    try:
        with urllib.request.urlopen(f"{es_url}/{index}/_count", timeout=30) as resp:
            payload: dict[str, object] = json.load(resp)
        value = payload.get("count")
        return int(value) if isinstance(value, int) else None
    except (urllib.error.URLError, OSError, ValueError):
        return None


def miles(v: int) -> str:
    return f"{v:,}".replace(",", ".")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--es-url", default=ES_URL)
    ap.add_argument("--index", default=INDEX)
    ap.add_argument("--timeout", type=int, default=1800, help="segundos como máximo")
    args = ap.parse_args()
    url = args.es_url.rstrip("/")

    start = time.monotonic()
    first = count(url, args.index)
    if first is None:
        print("  Elasticsearch no responde. Levantá el stack con 'make elastic-dev-up'.")
        return 1

    print(f"  documentos al inicio: {miles(first)}")
    previous = first
    stable = 0

    while time.monotonic() - start < args.timeout:
        time.sleep(POLL_SECONDS)
        current = count(url, args.index)
        if current is None:
            print("  se perdió la conexión con Elasticsearch.")
            return 1

        if current == previous:
            stable += 1
            if stable >= STABLE_CHECKS:
                added = current - first
                elapsed = int(time.monotonic() - start)
                print(f"  documentos al final: {miles(current)}  (+{miles(added)} en {elapsed}s)")
                if added == 0:
                    print("  no había nada nuevo que ingerir.")
                return 0
        else:
            if stable:  # it moved again after looking quiet
                stable = 0
            print(f"  ingiriendo… {miles(current)} (+{miles(current - previous)})")
        previous = current

    print(f"  se agotó la espera de {args.timeout}s; la ingesta sigue en curso.")
    print("  Los artefactos que se generen ahora pueden quedar incompletos.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
