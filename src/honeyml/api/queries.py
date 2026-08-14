"""Aggregations over the ECS indices that power the dashboard.

Plain urllib so the module has no dependency beyond the standard library: the same functions
serve the live API and the static snapshot used for offline screenshots.
"""

from __future__ import annotations

import json
import urllib.request
from typing import Any

ES_URL = "http://localhost:9200"
INDEX = "honeypot-*"
LOCAL_IP = "127.0.0.1"

# every query excludes the container's own healthchecks
NOT_LOCAL: dict[str, Any] = {"bool": {"must_not": [{"term": {"source.ip": LOCAL_IP}}]}}


def _search(body: dict[str, Any], es_url: str = ES_URL, index: str = INDEX) -> dict[str, Any]:
    req = urllib.request.Request(
        f"{es_url}/{index}/_search",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        result: dict[str, Any] = json.load(resp)
        return result


def _terms(
    field: str, size: int, es_url: str = ES_URL, extra: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    query = extra or NOT_LOCAL
    body = {"size": 0, "query": query, "aggs": {"t": {"terms": {"field": field, "size": size}}}}
    buckets = _search(body, es_url)["aggregations"]["t"]["buckets"]
    return [{"key": b["key"], "count": b["doc_count"]} for b in buckets]


def overview(es_url: str = ES_URL) -> dict[str, Any]:
    """Headline counters: the numbers that open the dashboard."""
    body = {
        "size": 0,
        # without this ES caps the reported total at 10.000
        "track_total_hits": True,
        "query": NOT_LOCAL,
        "aggs": {
            "ips": {"cardinality": {"field": "source.ip"}},
            "sensors": {"terms": {"field": "honeypot"}},
            "logins": {"filter": {"term": {"event.action": "login"}}},
            "logins_ok": {
                "filter": {
                    "bool": {
                        "must": [
                            {"term": {"event.action": "login"}},
                            {"term": {"event.outcome": "success"}},
                        ]
                    }
                }
            },
            "commands": {"filter": {"exists": {"field": "process.command_line"}}},
            "window": {"stats": {"field": "@timestamp"}},
        },
    }
    res = _search(body, es_url)
    agg = res["aggregations"]
    return {
        "events": res["hits"]["total"]["value"],
        "unique_ips": agg["ips"]["value"],
        "logins": agg["logins"]["doc_count"],
        "logins_success": agg["logins_ok"]["doc_count"],
        "commands": agg["commands"]["doc_count"],
        "by_sensor": {b["key"]: b["doc_count"] for b in agg["sensors"]["buckets"]},
        "first_event": agg["window"]["min_as_string"],
        "last_event": agg["window"]["max_as_string"],
    }


def timeline(es_url: str = ES_URL, interval: str = "1d") -> list[dict[str, Any]]:
    """Events over time: shows the relentlessness of the traffic, and the capture gaps."""
    body = {
        "size": 0,
        "query": NOT_LOCAL,
        "aggs": {
            "t": {
                "date_histogram": {"field": "@timestamp", "calendar_interval": interval},
                "aggs": {"sensors": {"terms": {"field": "honeypot"}}},
            }
        },
    }
    out = []
    for b in _search(body, es_url)["aggregations"]["t"]["buckets"]:
        by_sensor = {s["key"]: s["doc_count"] for s in b["sensors"]["buckets"]}
        out.append({"date": b["key_as_string"][:10], "count": b["doc_count"], **by_sensor})
    return out


def top_credentials(es_url: str = ES_URL, size: int = 10) -> dict[str, list[dict[str, Any]]]:
    """What attackers actually try: the concrete evidence behind 'use strong passwords'."""
    return {
        "users": _terms("user.name", size, es_url),
        "passwords": _terms("cowrie.password", size, es_url),
    }


def top_commands(es_url: str = ES_URL, size: int = 12) -> list[dict[str, Any]]:
    return _terms("process.command_line", size, es_url)


def protocols(es_url: str = ES_URL) -> list[dict[str, Any]]:
    """Attack surface by protocol: what the multiprotocol sensor adds over SSH alone."""
    return _terms("network.protocol", 15, es_url)


def attack_stages(es_url: str = ES_URL) -> list[dict[str, Any]]:
    """Events grouped by stage of the intrusion."""
    return _terms("event.category", 10, es_url)


def protocol_detail(es_url: str = ES_URL) -> list[dict[str, Any]]:
    """Per-protocol traffic on the multiprotocol sensor, with how many distinct sources hit each.

    Event counts alone are misleading here: SMB dominates because a single worm retries endlessly,
    while HTTP is touched by far more distinct scanners. The two numbers together tell that apart.
    """
    body = {
        "size": 0,
        "query": {
            "bool": {
                "must": [{"term": {"honeypot": "dionaea"}}],
                "must_not": [{"term": {"source.ip": LOCAL_IP}}],
            }
        },
        "aggs": {
            "p": {
                "terms": {"field": "network.protocol", "size": 12},
                "aggs": {
                    "ips": {"cardinality": {"field": "source.ip"}},
                    "port": {"terms": {"field": "destination.port", "size": 1}},
                },
            }
        },
    }
    out = []
    for b in _search(body, es_url)["aggregations"]["p"]["buckets"]:
        ports = b["port"]["buckets"]
        out.append(
            {
                "protocol": b["key"],
                "count": b["doc_count"],
                "sources": b["ips"]["value"],
                "port": ports[0]["key"] if ports else None,
            }
        )
    return out


def hourly(es_url: str = ES_URL) -> list[dict[str, Any]]:
    """Attacks by hour of day, in UTC.

    The interesting part is that this distribution is flat. Human activity has office hours;
    a flat curve is the signature of automation, and it is easier to show than to assert.
    """
    body = {
        "size": 0,
        "query": NOT_LOCAL,
        "aggs": {
            "h": {
                "date_histogram": {"field": "@timestamp", "calendar_interval": "hour"},
                "aggs": {"logins": {"filter": {"term": {"event.action": "login"}}}},
            }
        },
    }
    per_hour = [0] * 24
    logins_per_hour = [0] * 24
    for b in _search(body, es_url)["aggregations"]["h"]["buckets"]:
        hour = int(b["key_as_string"][11:13])
        per_hour[hour] += b["doc_count"]
        logins_per_hour[hour] += b["logins"]["doc_count"]
    return [{"hour": h, "count": per_hour[h], "logins": logins_per_hour[h]} for h in range(24)]


def snapshot(es_url: str = ES_URL) -> dict[str, Any]:
    """Everything the dashboard needs, in one object (also used for the offline snapshot)."""
    return {
        "overview": overview(es_url),
        "timeline": timeline(es_url),
        "credentials": top_credentials(es_url),
        "commands": top_commands(es_url),
        "protocols": protocols(es_url),
        "stages": attack_stages(es_url),
        "protocol_detail": protocol_detail(es_url),
        "hourly": hourly(es_url),
    }
