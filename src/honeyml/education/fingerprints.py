"""Agrupa las sesiones capturadas por la secuencia exacta de comandos que ejecutan.

El hallazgo que esto existe para mostrar: la mayoría de las sesiones no son ataques distintos, son
el mismo script reproducido por muchas máquinas. Agrupar por secuencia de comandos convierte un
número de volumen en evidencia de que el atacante es un programa y no una persona, que es la premisa
sobre la que se apoya todo el proyecto.

Una familia acá es un conjunto de sesiones cuya secuencia de comandos es idéntica byte a byte. Es
una definición estricta a propósito: no puede producir agrupaciones falsas, así que toda familia que
encuentra es real.

Uso:
    python -m honeyml.education.fingerprints
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from .annotations import annotate
from .session_replay import LOGS_DIR, _collect, anonymize, defang

OUT_FILE = Path("data/processed/fingerprints.json")
# una familia necesita suficientes miembros para ser un patrón y no una casualidad
MIN_SESSIONS = 3
# cuántas familias se publican, y cuántos comandos se guardan como firma de cada una
TOP_N = 12
MAX_COMMANDS = 12


def _signature(commands: list[str]) -> str:
    return hashlib.sha256("\n".join(commands).encode()).hexdigest()[:12]


def build(logs_dir: Path = LOGS_DIR) -> dict[str, Any]:
    sessions = _collect(logs_dir)
    usable = [s for s in sessions.values() if s["commands"]]

    families: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"sessions": 0, "ips": set(), "commands": [], "first": None, "last": None}
    )
    for s in usable:
        sig = _signature(s["commands"])
        fam = families[sig]
        fam["sessions"] += 1
        fam["ips"].add(s["ip"])
        fam["commands"] = s["commands"]
        ts = s["start"]
        if ts:
            fam["first"] = min(fam["first"] or ts, ts)
            fam["last"] = max(fam["last"] or ts, ts)

    ranked = sorted(
        (f for f in families.values() if f["sessions"] >= MIN_SESSIONS),
        key=lambda f: f["sessions"],
        reverse=True,
    )

    total_sessions = len(usable)
    grouped = sum(f["sessions"] for f in ranked)

    out = []
    for fam in ranked[:TOP_N]:
        commands = fam["commands"][:MAX_COMMANDS]
        tactics = sorted({annotate(c).tactic for c in commands})
        out.append(
            {
                "sessions": fam["sessions"],
                "sources": len(fam["ips"]),
                "commands": [defang(c) for c in commands],
                "truncated": len(fam["commands"]) > MAX_COMMANDS,
                "total_commands": len(fam["commands"]),
                "tactics": tactics,
                "first_seen": fam["first"],
                "last_seen": fam["last"],
                # una etiqueta estable, para poder referirse a la familia en el informe
                "label": anonymize("|".join(fam["commands"])).replace("attacker-", "family-"),
            }
        )

    return {
        "families": out,
        "total_sessions": total_sessions,
        "families_found": len(ranked),
        "grouped_sessions": grouped,
    }


def load() -> dict[str, Any] | None:
    if not OUT_FILE.exists():
        return None
    parsed: dict[str, Any] = json.loads(OUT_FILE.read_text(encoding="utf-8"))
    return parsed


def main() -> None:
    data = build()
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    pct = 100 * data["grouped_sessions"] / (data["total_sessions"] or 1)
    print(f"Familias -> {OUT_FILE}")
    print(f"  {data['total_sessions']:,} sesiones con comandos".replace(",", "."))
    print(f"  {data['families_found']:,} familias de 3+ sesiones idénticas".replace(",", "."))
    print(f"  {data['grouped_sessions']:,} sesiones agrupadas ({pct:.0f}%)".replace(",", "."))
    print()
    for fam in data["families"][:5]:
        print(
            f"  {fam['label']}: {fam['sessions']:,} sesiones desde "
            f"{fam['sources']} direcciones".replace(",", ".")
        )
        print(f"    {' ; '.join(fam['commands'][:3])[:88]}")


if __name__ == "__main__":
    main()
