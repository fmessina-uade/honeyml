"""Build the lookup that lets a visitor check their own password against the captured ones.

The privacy design is the point, and it is the same one Have I Been Pwned uses (k-anonymity):

  1. The browser hashes the typed password with SHA-256 and sends only the first five hex
     characters of the digest.
  2. The service answers with every captured hash sharing that prefix, and its count.
  3. The browser finishes the comparison locally.

The password never leaves the browser, and the service cannot tell which of the returned hashes
the visitor was asking about. Asking someone to type a real password into a form that transmits
it would teach exactly the wrong lesson — in a panel whose whole subject is credential attacks,
that would be indefensible.

Usage:
    python -m honeyml.education.password_index
"""

from __future__ import annotations

import hashlib
import json
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any

ES_URL = "http://localhost:9200"
INDEX = "honeypot-*"
OUT_FILE = Path("data/processed/password_index.json")
PREFIX_LEN = 5
# how many distinct passwords to pull; the captures hold ~54.000
MAX_TERMS = 100_000


def fetch_passwords(es_url: str = ES_URL) -> list[tuple[str, int]]:
    """Every distinct captured password with how many times it was attempted."""
    body = {
        "size": 0,
        "query": {"bool": {"must_not": [{"term": {"source.ip": "127.0.0.1"}}]}},
        "aggs": {"p": {"terms": {"field": "cowrie.password", "size": MAX_TERMS}}},
    }
    req = urllib.request.Request(
        f"{es_url}/{INDEX}/_search",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        buckets = json.load(resp)["aggregations"]["p"]["buckets"]
    return [(b["key"], b["doc_count"]) for b in buckets]


def build(es_url: str = ES_URL) -> dict[str, Any]:
    """Group the hashed passwords by digest prefix."""
    passwords = fetch_passwords(es_url)
    buckets: dict[str, list[list[Any]]] = defaultdict(list)
    for raw, count in passwords:
        digest = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()
        buckets[digest[:PREFIX_LEN]].append([digest[PREFIX_LEN:], count])

    total_attempts = sum(c for _, c in passwords)
    return {
        "prefix_len": PREFIX_LEN,
        "distinct": len(passwords),
        "attempts": total_attempts,
        "buckets": buckets,
    }


def load() -> dict[str, Any] | None:
    if not OUT_FILE.exists():
        return None
    parsed: dict[str, Any] = json.loads(OUT_FILE.read_text(encoding="utf-8"))
    return parsed


def lookup(prefix: str, index: dict[str, Any]) -> dict[str, Any]:
    """Everything the client needs to finish the comparison on its own."""
    matches = index.get("buckets", {}).get(prefix.lower(), [])
    return {
        "prefix": prefix.lower(),
        "matches": [{"suffix": s, "count": c} for s, c in matches],
        "distinct": index.get("distinct", 0),
        "attempts": index.get("attempts", 0),
    }


def main() -> None:
    index = build()
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")

    size_mb = OUT_FILE.stat().st_size / 1024 / 1024
    print(f"Índice de contraseñas -> {OUT_FILE} ({size_mb:.1f} MB)")
    print(f"  {index['distinct']:,} contraseñas distintas".replace(",", "."))
    print(f"  {index['attempts']:,} intentos en total".replace(",", "."))
    print(f"  {len(index['buckets']):,} prefijos de {PREFIX_LEN} caracteres".replace(",", "."))
    print("\nLa contraseña nunca sale del navegador: solo viaja el prefijo del hash.")


if __name__ == "__main__":
    main()
