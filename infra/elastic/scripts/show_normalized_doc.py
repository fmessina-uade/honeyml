"""Print a normalized document, and the raw record it came from, for the report's figures.

Shows what the ECS pipeline contributes: the same event before and after normalization, side by
side. Credentials and source addresses are masked — the point of the figure is the shape of the
document, not who was attacking.

Usage:
    python infra/elastic/scripts/show_normalized_doc.py                 # a login event
    python infra/elastic/scripts/show_normalized_doc.py --tipo comando  # a command execution
    python infra/elastic/scripts/show_normalized_doc.py --sin-mascara   # unmasked, local review
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.request
from pathlib import Path
from typing import Any

ES = "http://localhost:9200"
# the indexed document keeps only Cowrie's `message`; the true native record lives in the log
RAW_LOG = Path("data/logs/cowrie/cowrie.json")

QUERIES = {
    "login": {"term": {"event.action": "login"}},
    "comando": {"term": {"event.action": "command-input"}},
}

# fields whose value identifies a third party or reveals a credential
MASK_FIELDS = {
    "source.ip",
    "source.address",
    "host.ip",
    "related.ip",
    "cowrie.password",
    "event.original",
}

# Cowrie writes the attempted credential into the raw line: "login attempt [user/pass] failed"
_CRED_IN_TEXT = re.compile(r"\[([^\]/]+)/([^\]]*)\]")


def mask_ip(ip: str) -> str:
    """Keep the shape of an address without identifying the host."""
    parts = ip.split(".")
    if len(parts) == 4:
        return f"{parts[0]}.{parts[1]}.xxx.xxx"
    return "xxxx:xxxx::xxxx"


def mask_value(path: str, value: Any) -> Any:
    if isinstance(value, list):
        return [mask_value(path, v) for v in value]
    if not isinstance(value, str):
        return value
    if path in ("source.ip", "source.address", "host.ip", "related.ip"):
        return mask_ip(value)
    if path == "cowrie.password":
        return "•" * min(len(value), 8)
    if path == "event.original":
        # the username stays (it is the finding); the password does not
        return _CRED_IN_TEXT.sub(lambda m: f"[{m.group(1)}/{'•' * min(len(m.group(2)), 8)}]", value)
    return value


def apply_mask(doc: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in doc.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            out[key] = apply_mask(value, f"{path}.")
        elif path in MASK_FIELDS:
            out[key] = mask_value(path, value)
        else:
            out[key] = value
    return out


def fetch(tipo: str, es_url: str) -> dict[str, Any] | None:
    body = {
        "size": 1,
        "query": {
            "bool": {
                "must": [QUERIES[tipo]],
                "must_not": [{"term": {"source.ip": "127.0.0.1"}}],
            }
        },
        "sort": [{"@timestamp": "desc"}],
    }
    req = urllib.request.Request(
        f"{es_url}/honeypot-cowrie-*/_search",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        hits = json.load(r)["hits"]["hits"]
    return hits[0]["_source"] if hits else None


def find_native(session: str, eventid: str) -> dict[str, Any] | None:
    """Recover the sensor's original line from the local log copy, matched by session and event."""
    if not RAW_LOG.exists():
        return None
    with open(RAW_LOG, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if session not in line or eventid not in line:
                continue
            try:
                rec: dict[str, Any] = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("session") == session and rec.get("eventid") == eventid:
                return rec
    return None


def show(title: str, payload: dict[str, Any]) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")
    print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tipo", choices=sorted(QUERIES), default="login")
    ap.add_argument("--es-url", default=ES)
    ap.add_argument("--sin-mascara", action="store_true")
    args = ap.parse_args()

    doc = fetch(args.tipo, args.es_url.rstrip("/"))
    if doc is None:
        raise SystemExit(f"No se encontró ningún evento de tipo '{args.tipo}'.")

    raw_msg = doc.pop("message", None)
    shown = doc if args.sin_mascara else apply_mask(doc)

    native = find_native(doc.get("cowrie", {}).get("session", ""), doc.get("eventid", ""))
    if native is not None:
        if not args.sin_mascara:
            for k in ("src_ip", "peer_ip", "dst_ip"):
                if k in native:
                    native[k] = mask_ip(str(native[k]))
            if "password" in native:
                native["password"] = "•" * min(len(str(native["password"])), 8)
            if "message" in native:
                native["message"] = mask_value("event.original", str(native["message"]))
        show("ANTES — registro nativo del sensor (Cowrie jsonlog)", native)
    elif raw_msg:
        print("\nANTES — registro nativo (solo el mensaje; falta la copia local del log):")
        print(f"  {raw_msg[:300]}")

    show("DESPUÉS — documento normalizado a Elastic Common Schema", shown)

    ecs = sum(1 for k in shown if k not in ("cowrie", "dionaea", "honeypot"))
    own = len(shown.get("cowrie", {})) + len(shown.get("dionaea", {}))
    print(f"\n  campos ECS: {ecs}   |   campos bajo espacio de nombres del sensor: {own}")
    if not args.sin_mascara:
        print("  (direcciones y contraseñas enmascaradas para publicación)")


if __name__ == "__main__":
    main()
