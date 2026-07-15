"""Load ECS-normalized events from Elasticsearch into a pandas DataFrame.

Uses the scroll API over urllib (no elasticsearch client, so we don't pin to its version) and
flattens the nested ECS fields into flat columns ready for the EDA.
"""

from __future__ import annotations

import json
import urllib.request
from typing import Any

import pandas as pd

# ECS fields pulled per event. Asked for explicitly so we don't drag heavy payloads along.
DEFAULT_FIELDS = [
    "@timestamp",
    "honeypot",
    "observer.vendor",
    "event.category",
    "event.action",
    "event.outcome",
    "event.dataset",
    "network.protocol",
    "network.transport",
    "source.ip",
    "source.port",
    "destination.port",
    "user.name",
    "process.command_line",
    "cowrie.session",
    "cowrie.password",
    "event.duration",
]


def _post(url: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
    req = urllib.request.Request(
        f"{url}{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        result: dict[str, Any] = json.load(resp)
        return result


def _first(value: Any) -> Any:
    """ECS allows arrays (e.g. event.category=[network,authentication]); take the first value."""
    if isinstance(value, list):
        return value[0] if value else None
    return value


def load_events(
    es_url: str = "http://localhost:9200",
    index: str = "honeypot-*",
    fields: list[str] | None = None,
    page_size: int = 5000,
    max_docs: int | None = None,
) -> pd.DataFrame:
    """Pull every event of the index into a DataFrame with flat ECS columns.

    Parameters
    ----------
    es_url : Elasticsearch base URL.
    index : index pattern (honeypot-*, honeypot-cowrie-*, ...).
    fields : ECS fields to fetch; defaults to DEFAULT_FIELDS.
    page_size : scroll page size.
    max_docs : optional doc cap (handy for quick tests).
    """
    url = es_url.rstrip("/")
    fields = fields or DEFAULT_FIELDS

    body = {"size": page_size, "_source": fields, "query": {"match_all": {}}}
    res = _post(url, f"/{index}/_search?scroll=2m", body)
    scroll_id = res.get("_scroll_id")
    rows: list[dict[str, Any]] = []

    while True:
        hits = res["hits"]["hits"]
        if not hits:
            break
        for h in hits:
            src = h["_source"]
            row = {}
            for f in fields:
                # walk the dotted path (event.category -> src["event"]["category"])
                node = src
                for part in f.split("."):
                    if isinstance(node, dict):
                        node = node.get(part)
                    else:
                        node = None
                        break
                row[f] = _first(node)
            rows.append(row)
        if max_docs and len(rows) >= max_docs:
            rows = rows[:max_docs]
            break
        res = _post(url, "/_search/scroll", {"scroll": "2m", "scroll_id": scroll_id})
        scroll_id = res.get("_scroll_id")

    # free the scroll context
    if scroll_id:
        try:
            req = urllib.request.Request(
                f"{url}/_search/scroll",
                data=json.dumps({"scroll_id": scroll_id}).encode(),
                headers={"Content-Type": "application/json"},
                method="DELETE",
            )
            urllib.request.urlopen(req, timeout=30)
        except Exception:
            pass

    df = pd.DataFrame(rows, columns=fields)
    if "@timestamp" in df.columns:
        df["@timestamp"] = pd.to_datetime(df["@timestamp"], errors="coerce", utc=True)
    return df


if __name__ == "__main__":
    df = load_events()
    print(f"Events loaded: {len(df):,}")
    print(df.dtypes)
    print(df.head())
