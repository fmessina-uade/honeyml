"""Extrae sesiones de ataque reales, anotadas, para que el panel las pueda repasar paso a paso.

Es el material de la sección "anatomía de un ataque": una intrusión de verdad capturada por el
honeypot, repasada comando por comando con una explicación de qué buscaba el atacante. Es lo que un
gráfico no puede mostrar.

Las direcciones de origen van anonimizadas: en las capturas hay terceros involucrados y el valor
educativo no depende de la dirección real.

Uso:
    python -m honeyml.education.session_replay
"""

from __future__ import annotations

import glob
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .. import redes
from .annotations import annotate

LOGS_DIR = Path("data/logs/cowrie")
OUT_FILE = Path("data/processed/replay_sessions.json")

# Comandos que no le aportan nada a quien lee (líneas vacías que manda el cliente al conectar).
MIN_COMMAND_LEN = 2
# Cuántas sesiones se publican, y hasta dónde se recorta una sesión larga. Va una sesión por
# atacante (ver build_replays), así que en realidad es un tope de atacantes distintos. Las capturas
# dan unos 260; el tope solo evita un archivo sin límite si ese número creciera mucho.
TOP_N = 400
MAX_COMMANDS = 20


def anonymize(ip: str) -> str:
    """Seudónimo estable para una dirección: la misma siempre da la misma etiqueta."""
    digest = hashlib.sha256(ip.encode()).hexdigest()[:6]
    return f"attacker-{digest}"


# direcciones y URLs de la infraestructura de malware desde donde baja cosas el atacante
_IP_IN_TEXT = re.compile(r"\b(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})\b")


def defang(command: str) -> str:
    """Neutraliza URLs y direcciones para que el material publicado no sea directamente accionable.

    Es la práctica habitual al publicar inteligencia de amenazas: el lector sigue viendo la
    evidencia, pero la dirección del payload no se puede clickear ni copiar sin querer.
    """
    text = _IP_IN_TEXT.sub(
        lambda m: f"{m.group(1)}.{m.group(2)}.{m.group(3)}[.]{m.group(4)}", command
    )
    return text.replace("http://", "hxxp://").replace("https://", "hxxps://")


def _collect(logs_dir: Path) -> dict[str, dict[str, Any]]:
    """Agrupa todos los eventos de Cowrie por identificador de sesión."""
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
                if not sid or redes.es_interna(ip):
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
    """Ordena por valor educativo: primero la variedad de tácticas, después la cantidad de comandos.

    Una sesión que toca persistencia, descarga y reconocimiento enseña más que una que repite el
    mismo comando veinte veces.
    """
    tactics = {annotate(c).tactic for c in session["commands"]}
    return len(tactics), len(set(session["commands"]))


def build_replays(logs_dir: Path = LOGS_DIR, top_n: int = TOP_N) -> list[dict[str, Any]]:
    """Elige las sesiones más instructivas y anota cada comando.

    Una sesión por dirección de origen: varias sesiones del mismo bot son casi idénticas y llenarían
    la lista de repeticiones en lugar de mostrar estilos de ataque distintos.
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
                    "what_en": a.what_en,
                    "why_en": a.why_en,
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
