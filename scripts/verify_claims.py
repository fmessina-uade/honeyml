"""Check the implementation claims made in the report against the running system.

Every table in the document that describes runtime behaviour is re-derived here from
Elasticsearch instead of being trusted. Run it before submitting, and paste the output next to
the chapter it backs.

Usage:
    python scripts/verify_claims.py
"""

from __future__ import annotations

import json
import urllib.request
from typing import Any

ES = "http://localhost:9200"
NOT_LOCAL = {"bool": {"must_not": [{"term": {"source.ip": "127.0.0.1"}}]}}


def search(index: str, body: dict[str, Any]) -> dict[str, Any]:
    req = urllib.request.Request(
        f"{ES}/{index}/_search",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        out: dict[str, Any] = json.load(r)
        return out


def miles(v: int) -> str:
    return f"{v:,}".replace(",", ".")


def event_mapping() -> None:
    """Claim 8: the nine Cowrie event rows (native event, category, action, outcome)."""
    body = {
        "size": 0,
        "query": NOT_LOCAL,
        "aggs": {
            "e": {
                "terms": {"field": "event.action", "size": 30},
                "aggs": {
                    "cat": {"terms": {"field": "event.category", "size": 3}},
                    "out": {"terms": {"field": "event.outcome", "size": 3}},
                },
            }
        },
    }
    buckets = search("honeypot-cowrie-*", body)["aggregations"]["e"]["buckets"]
    print(f"{'event.action':<28}{'event.category':<16}{'event.outcome':<14}{'eventos':>12}")
    print("-" * 70)
    for b in buckets:
        cat = ",".join(x["key"] for x in b["cat"]["buckets"]) or "—"
        out = ",".join(x["key"] for x in b["out"]["buckets"]) or "—"
        print(f"{b['key']:<28}{cat:<16}{out:<14}{miles(b['doc_count']):>12}")
    print(f"\n  filas distintas: {len(buckets)}")


def sensor_namespace() -> None:
    """Claim 9: attributes with no ECS equivalent live under a per-sensor namespace."""
    for sensor in ("cowrie", "dionaea"):
        body = {"size": 1, "query": {"bool": {"filter": [{"exists": {"field": sensor}}]}}}
        hits = search(f"honeypot-{sensor}-*", body)["hits"]["hits"]
        if not hits:
            print(f"  {sensor}: sin espacio de nombres propio")
            continue
        keys = sorted(hits[0]["_source"].get(sensor, {}).keys())
        print(f"  {sensor}.*  ->  {', '.join(keys)}")


def unrouted() -> None:
    """Claim 7: the dead-letter index is empty in normal operation."""
    req = urllib.request.Request(f"{ES}/_cat/indices/honeypot-unrouted-*?format=json")
    with urllib.request.urlopen(req, timeout=30) as r:
        rows = json.load(r)
    if not rows:
        print("  índice honeypot-unrouted-* : no existe (cero eventos sin enrutar)")
    else:
        for row in rows:
            print(f"  {row['index']}: {row['docs.count']} documentos")


def complementarity() -> None:
    """Claim 11: the network-services sensor sees database protocols the SSH sensor cannot."""
    body = {
        "size": 0,
        "query": NOT_LOCAL,
        "aggs": {
            "s": {
                "terms": {"field": "honeypot"},
                "aggs": {"p": {"terms": {"field": "network.protocol", "size": 12}}},
            }
        },
    }
    for s in search("honeypot-*", body)["aggregations"]["s"]["buckets"]:
        protos = ", ".join(f"{p['key']} ({miles(p['doc_count'])})" for p in s["p"]["buckets"])
        print(f"  {s['key']:<9} -> {protos}")


def totals() -> None:
    """The final numbers for the report's cut-off."""
    body = {
        "size": 0,
        "track_total_hits": True,
        "query": NOT_LOCAL,
        "aggs": {
            "ips": {"cardinality": {"field": "source.ip"}},
            "sensor": {"terms": {"field": "honeypot"}},
            "win": {"stats": {"field": "@timestamp"}},
            "logins": {"filter": {"term": {"event.action": "login"}}},
            "ok": {
                "filter": {
                    "bool": {
                        "must": [
                            {"term": {"event.action": "login"}},
                            {"term": {"event.outcome": "success"}},
                        ]
                    }
                }
            },
            "cmds": {"filter": {"exists": {"field": "process.command_line"}}},
        },
    }
    res = search("honeypot-*", body)
    a = res["aggregations"]
    print(
        f"  ventana            {a['win']['min_as_string'][:10]} a {a['win']['max_as_string'][:10]}"
    )
    print(f"  eventos totales    {miles(res['hits']['total']['value'])}")
    print(f"  direcciones únicas {miles(a['ips']['value'])}")
    print(f"  intentos de acceso {miles(a['logins']['doc_count'])}")
    print(f"  accesos logrados   {miles(a['ok']['doc_count'])}")
    print(f"  comandos           {miles(a['cmds']['doc_count'])}")
    for b in a["sensor"]["buckets"]:
        print(f"  sensor {b['key']:<10} {miles(b['doc_count'])}")


def main() -> None:
    for title, fn in [
        ("Afirmación 8 — mapeo de eventos del sensor de acceso remoto", event_mapping),
        ("Afirmación 9 — espacio de nombres por sensor", sensor_namespace),
        ("Afirmación 7 — índice de descarte", unrouted),
        ("Afirmación 11 — complementariedad de sensores", complementarity),
        ("Parte 3 — números finales del corte", totals),
    ]:
        print(f"\n{'=' * 72}\n{title}\n{'=' * 72}")
        fn()
    print()


if __name__ == "__main__":
    main()
