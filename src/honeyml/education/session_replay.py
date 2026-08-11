"""Extract real attack sessions, annotated, so the dashboard can replay them step by step.

This is the material for the "anatomy of an attack" section: a genuine intrusion captured by the
honeypot, replayed command by command with an explanation of what the attacker was after. It is
what a chart cannot show.

Source IPs are anonymized: the captures involve third parties and the educational value does not
depend on the real address.

Usage:
    python -m honeyml.education.session_replay
"""

from __future__ import annotations

import glob
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .annotations import annotate

LOGS_DIR = Path("data/logs/cowrie")
OUT_FILE = Path("data/processed/replay_sessions.json")
LOCAL_IP = "127.0.0.1"

# Commands that add nothing for a reader (empty lines the client sends on connect).
MIN_COMMAND_LEN = 2
# How many sessions to publish, and how long a session may be before we trim it.
TOP_N = 12
MAX_COMMANDS = 20


def anonymize(ip: str) -> str:
    """Stable pseudonym for a source IP: same address always yields the same label."""
    digest = hashlib.sha256(ip.encode()).hexdigest()[:6]
    return f"attacker-{digest}"


# addresses and URLs of the malware infrastructure the attacker pulls from
_IP_IN_TEXT = re.compile(r"\b(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})\b")


def defang(command: str) -> str:
    """Neutralize URLs and addresses so the published material is not directly actionable.

    Standard practice when publishing threat intelligence: the reader still sees the evidence,
    but the payload address cannot be clicked or copied by accident.
    """
    text = _IP_IN_TEXT.sub(
        lambda m: f"{m.group(1)}.{m.group(2)}.{m.group(3)}[.]{m.group(4)}", command
    )
    return text.replace("http://", "hxxp://").replace("https://", "hxxps://")


def _collect(logs_dir: Path) -> dict[str, dict[str, Any]]:
    """Group every Cowrie event by session id."""
    sessions: dict[str, dict[str, Any]] = {}
    for path in sorted(glob.glob(str(logs_dir / "cowrie.json*"))):
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                sid = event.get("session")
                ip = event.get("src_ip", "")
                if not sid or ip == LOCAL_IP:
                    continue

                s = sessions.setdefault(
                    sid,
                    {
                        "ip": ip,
                        "commands": [],
                        "credentials": None,
                        "protocol": None,
                        "start": None,
                    },
                )
                eventid = event.get("eventid", "")
                if s["start"] is None:
                    s["start"] = event.get("timestamp")
                if event.get("protocol"):
                    s["protocol"] = event["protocol"]
                if eventid == "cowrie.login.success":
                    s["credentials"] = (event.get("username"), event.get("password"))
                elif eventid == "cowrie.command.input":
                    cmd = (event.get("input") or "").strip()
                    if len(cmd) >= MIN_COMMAND_LEN:
                        s["commands"].append(cmd)
    return sessions


def _score(session: dict[str, Any]) -> tuple[int, int]:
    """Rank by educational value: variety of tactics first, then number of commands.

    A session touching persistence, download and discovery teaches more than one repeating the
    same command twenty times.
    """
    tactics = {annotate(c).tactic for c in session["commands"]}
    return len(tactics), len(set(session["commands"]))


def build_replays(logs_dir: Path = LOGS_DIR, top_n: int = TOP_N) -> list[dict[str, Any]]:
    """Pick the most instructive sessions and annotate every command.

    One session per source address: several sessions from the same bot are nearly identical and
    would fill the list with repetitions instead of showing different attack styles.
    """
    sessions = _collect(logs_dir)
    usable = [s for s in sessions.values() if s["credentials"] and len(s["commands"]) >= 4]
    usable.sort(key=_score, reverse=True)

    replays: list[dict[str, Any]] = []
    seen_attackers: set[str] = set()
    for s in usable:
        if len(replays) >= top_n:
            break
        if s["ip"] in seen_attackers:
            continue
        seen_attackers.add(s["ip"])

        user, password = s["credentials"]
        steps = []
        for cmd in s["commands"][:MAX_COMMANDS]:
            a = annotate(cmd)
            steps.append(
                {
                    "command": defang(cmd),
                    "what": a.what,
                    "why": a.why,
                    "tactic": a.tactic,
                    "technique": a.technique,
                }
            )
        replays.append(
            {
                "attacker": anonymize(s["ip"]),
                "protocol": s["protocol"] or "ssh",
                "timestamp": s["start"],
                "credentials": {"user": user, "password": password},
                "tactics": sorted({s_["tactic"] for s_ in steps}),
                "steps": steps,
            }
        )
    return replays


def main() -> None:
    replays = build_replays()
    if not replays:
        raise SystemExit("No se encontraron sesiones con login exitoso y comandos.")
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(replays, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Sesiones publicadas: {len(replays)} -> {OUT_FILE}")
    top = replays[0]
    print(
        f"\nLa más instructiva: {top['attacker']} ({top['credentials']['user']}:"
        f"{top['credentials']['password']}), {len(top['steps'])} comandos"
    )
    print(f"Tácticas que cubre: {', '.join(top['tactics'])}\n")
    for step in top["steps"][:6]:
        print(f"  $ {step['command'][:70]}")
        print(f"    {step['tactic']}: {step['what']}")


if __name__ == "__main__":
    main()
