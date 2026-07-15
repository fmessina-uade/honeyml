"""Load Cowrie's raw JSON logs into a pandas DataFrame.

Reads the cowrie.json* files the honeypot writes (one JSON event per line) without needing the
Elastic Stack up. This is the ground-truth source for offline EDA.
"""

from __future__ import annotations

import glob
import json
from pathlib import Path
from typing import Any

import pandas as pd

# Cowrie fields we care about (the rest is dropped to keep memory down).
FIELDS = [
    "eventid",
    "timestamp",
    "src_ip",
    "src_port",
    "dst_port",
    "session",
    "protocol",
    "username",
    "password",
    "input",
    "url",
    "shasum",
    "duration",
    "sensor",
]


def load_cowrie(
    logs_dir: str | Path = "data/logs/cowrie",
    pattern: str = "cowrie.json*",
    drop_local: bool = True,
) -> pd.DataFrame:
    """Read all cowrie.json* files in a directory into a DataFrame.

    Parameters
    ----------
    logs_dir : directory holding the cowrie.json* files.
    pattern : glob of files to read.
    drop_local : if True, drop 127.0.0.1 events (the container's own healthchecks).
    """
    logs_dir = Path(logs_dir)
    rows: list[dict[str, Any]] = []
    for path in sorted(glob.glob(str(logs_dir / pattern))):
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rows.append({f: obj.get(f) for f in FIELDS})

    df = pd.DataFrame(rows, columns=FIELDS)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
    if drop_local:
        df = df[df["src_ip"] != "127.0.0.1"].reset_index(drop=True)
    return df


if __name__ == "__main__":
    df = load_cowrie()
    print(f"External events loaded: {len(df):,}")
    print(f"Time range: {df['timestamp'].min()}  ->  {df['timestamp'].max()}")
    print(f"Unique IPs: {df['src_ip'].nunique():,}")
    print(df["eventid"].value_counts().head(10))
