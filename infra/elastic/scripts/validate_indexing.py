#!/usr/bin/env python3
"""Validate the ECS indexing in Elasticsearch.

Checks the honeypot telemetry was indexed and normalized correctly: per-index counts, coverage of
the key ECS fields, no unrouted events or date-parse failures, and a quick event distribution.
No external deps (stdlib only).

Usage:
    python3 validate_indexing.py [--es-url http://localhost:9200]
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

OK = "\033[92m✓\033[0m"
WARN = "\033[93m!\033[0m"
FAIL = "\033[91m✗\033[0m"


def es(url: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{url}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST" if data else "GET",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def count(url: str, index: str, query: dict | None = None) -> int:
    body = {"query": query} if query else None
    return es(url, f"/{index}/_count", body).get("count", 0)


def terms(url: str, index: str, field: str, size: int = 10) -> list[tuple[str, int]]:
    body = {"size": 0, "aggs": {"t": {"terms": {"field": field, "size": size}}}}
    res = es(url, f"/{index}/_search", body)
    buckets = res.get("aggregations", {}).get("t", {}).get("buckets", [])
    return [(b["key"], b["doc_count"]) for b in buckets]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--es-url", default="http://localhost:9200")
    ap.add_argument("--index", default="honeypot-*")
    args = ap.parse_args()
    url = args.es_url.rstrip("/")

    try:
        health = es(url, "/_cluster/health")
    except (urllib.error.URLError, OSError) as exc:
        print(f"{FAIL} No se pudo conectar a Elasticsearch en {url}: {exc}")
        return 1

    print("\n=== Estado del cluster ===")
    print(f"  status={health['status']}  nodos={health['number_of_nodes']}")

    # --- Índices honeypot-* ---
    print(f"\n=== Índices ({args.index}) ===")
    try:
        cat = es(url, f"/_cat/indices/{args.index}?format=json&bytes=mb")
    except urllib.error.HTTPError:
        cat = []
    if not cat:
        print(f"  {WARN} No hay índices que coincidan con {args.index}. ¿Ya se ingirió algo?")
        return 1
    total = 0
    for idx in sorted(cat, key=lambda i: i["index"]):
        docs = int(idx.get("docs.count") or 0)
        total += docs
        print(f"  {idx['index']:<32} docs={docs:>8}  size={idx.get('store.size', '?')}mb")
    print(f"  {'TOTAL':<32} docs={total:>8}")

    checks_ok = True

    # unrouted events
    print("\n=== Integridad de enrutamiento ===")
    try:
        unrouted = count(url, "honeypot-unrouted-*")
    except urllib.error.HTTPError:
        unrouted = 0
    if unrouted == 0:
        print(f"  {OK} 0 eventos sin enrutar")
    else:
        print(f"  {FAIL} {unrouted} eventos en honeypot-unrouted-* (revisar filebeat/logstash)")
        checks_ok = False

    # ECS field coverage
    print(f"\n=== Cobertura de campos ECS (sobre {total} docs) ===")
    ecs_fields = [
        "@timestamp",
        "event.category",
        "event.action",
        "event.outcome",
        "source.ip",
        "observer.type",
    ]
    for field in ecs_fields:
        n = count(url, args.index, {"exists": {"field": field}})
        pct = (n / total * 100) if total else 0
        mark = OK if pct >= 99 else (WARN if pct >= 50 else FAIL)
        # source.ip isn't in every event: report it without penalizing
        note = "  (esperable <100%)" if field == "source.ip" else ""
        print(f"  {mark} {field:<18} {n:>8} ({pct:5.1f}%){note}")
        if field in ("@timestamp", "event.category", "observer.type") and pct < 99:
            checks_ok = False

    # date parse failures
    datefail = count(
        url,
        args.index,
        {"terms": {"tags": ["_dateparsefailure_cowrie", "_dateparsefailure_dionaea"]}},
    )
    mark = OK if datefail == 0 else FAIL
    print(f"  {mark} sin fallos de parseo de fecha ({datefail} con _dateparsefailure)")
    if datefail:
        checks_ok = False

    # event distribution (seeds the EDA)
    print("\n=== Distribución por event.action ===")
    for key, n in terms(url, args.index, "event.action", 15):
        print(f"  {n:>8}  {key}")

    print("\n=== Distribución por event.category ===")
    for key, n in terms(url, args.index, "event.category", 15):
        print(f"  {n:>8}  {key}")

    print("\n=== Top 10 source.ip ===")
    try:
        for key, n in terms(url, args.index, "source.ip", 10):
            print(f"  {n:>8}  {key}")
    except urllib.error.HTTPError:
        print("  (sin datos)")

    print("\n=== Top credenciales probadas (user.name) ===")
    for key, n in terms(url, args.index, "user.name", 10):
        print(f"  {n:>8}  {key}")

    print()
    if checks_ok:
        print(f"{OK} Validación de indexación ECS: OK")
        return 0
    print(f"{FAIL} Validación de indexación ECS: con observaciones (ver arriba)")
    return 2


if __name__ == "__main__":
    sys.exit(main())
