"""La muestra estratificada por conducta que el analista revisa a ciegas.

La tasa de falsos positivos toma como positiva la alerta crítica, y el motor solo decide algo en esa
frontera cuando sube un comando de alto a crítico: el resto de los niveles los fija la evidencia.
Por eso la muestra sale solo de las conductas con piso alto, y se reparte en cuatro estratos según
dos preguntas independientes: si el motor escaló, y si la regla de referencia dice que el comando
transfiere un archivo. Los estratos donde el motor y la regla no coinciden son los candidatos a
falso positivo y a falso negativo, y entran enteros si son chicos.

La unidad es la conducta y no la decisión, porque todas las decisiones de una conducta comparten la
misma clasificación: revisar dos veces la misma no agrega nada. La conducta se recalcula con la
firma vigente, sobre el usuario y el comando completos del evento. Las decisiones viejas de un
cargador que escribe un binario de a trozos se tomaron cuando cada trozo era una firma aparte, y
sin recalcular, ese cargador se llevaría cientos de lugares de la muestra.

Se corre en el servidor, que es donde está el índice, con `make muestra`. Con `--seco` muestra los
estratos sin escribir nada.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import urllib.request
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from ..agent import firma
from ..agent.consumer import EventoDelBus
from ..api import queries
from ..api.decisiones import DECISIONES, MUESTRA_FILE

# Cuántas conductas entran por estrato como máximo. Los estratos más chicos entran enteros.
POR_ESTRATO = 50
SEMILLA = 42

ESTRATOS = (
    "escalada_con_transferencia",
    "escalada_sin_transferencia",
    "alto_con_transferencia",
    "alto_sin_transferencia",
)

# La regla de referencia: un comando es crítico si transfiere un archivo en cualquier dirección.
# Una herramienta de descarga cuenta solo si en el mismo tramo del comando aparece adónde va:
# pedirle la versión o la ayuda la nombra sin traer nada.
_HERRAMIENTA = re.compile(r"\b(?:wget|curl|tftp|ftpget|scp|sftp)\b", re.IGNORECASE)
_DESTINO = re.compile(
    r"\b[a-z][a-z0-9+.-]*://"  # una dirección con esquema
    r"|\b\d{1,3}(?:\.\d{1,3}){3}\b"  # una IPv4
    r"|\b[\w-]+(?:\.[\w-]+)+(?::\d+)?/",  # un dominio seguido de una ruta
    re.IGNORECASE,
)
_BYTES = re.compile(r"\\x[0-9a-f]{2}", re.IGNORECASE)
_BASE64 = re.compile(r"\bbase64\s+(?:-d|--decode)\b", re.IGNORECASE)
_TRAMOS = re.compile(r"\|\||&&|[;|\n]")


def transfiere(comando: str) -> bool:
    """Si el comando trae, manda o escribe un archivo, según la regla de referencia.

    Se mira por tramos, separados por `;`, `|`, `&&` o `||`, salvo `/dev/tcp`, que abre la conexión
    en cualquier posición. Escribir bytes con escapes y decodificar base64 cuentan si el tramo los
    redirige a un archivo: impresos en pantalla son una prueba del entorno y no una descarga.
    """
    if "/dev/tcp/" in comando:
        return True
    for tramo in _TRAMOS.split(comando):
        if _HERRAMIENTA.search(tramo) and _DESTINO.search(tramo):
            return True
        if ">" in tramo and (_BYTES.search(tramo) or _BASE64.search(tramo)):
            return True
    return False


@dataclass
class Conducta:
    """Las decisiones que comparten la firma vigente, con la que representa a todas."""

    firma: str
    piso: str
    transfiere: bool
    representante: str = ""
    severidad: str = ""
    momento_del_representante: str = ""
    decisiones: int = 0
    por_severidad: Counter[str] = field(default_factory=Counter)

    @property
    def estrato(self) -> str | None:
        if self.piso != "alto":
            return None
        escalo = "escalada" if self.severidad == "critico" else "alto"
        regla = "con_transferencia" if self.transfiere else "sin_transferencia"
        return f"{escalo}_{regla}"


def _primero(valor: Any) -> str:
    if isinstance(valor, list):
        return str(valor[0]) if valor else ""
    return "" if valor is None else str(valor)


def evento_del_bus(decision: dict[str, Any], telemetria: dict[str, Any] | None) -> EventoDelBus:
    """El evento tal como lo publicó el pipeline, para firmarlo igual que el motor.

    Los campos que el motor ya tenía vienen copiados en la decisión. El usuario y el comando
    completos salen del documento de telemetría, que son los campos de los que los toma el pipeline.
    """
    evento = decision.get("evento", {})
    telemetria = telemetria or {}
    campos = {
        "doc_id": evento.get("doc_id", ""),
        "honeypot": evento.get("sensor") or "",
        "category": evento.get("categoria") or "",
        "action": evento.get("accion") or "",
        "outcome": evento.get("resultado") or "",
        "protocol": evento.get("protocolo") or "",
        "user": _primero(telemetria.get("user", {}).get("name")),
        "command": _primero(telemetria.get("process", {}).get("command_line")),
    }
    return EventoDelBus.desde_mensaje("", campos)


def agrupar(
    decisiones: Iterable[tuple[str, dict[str, Any]]],
    telemetria: dict[str, dict[str, Any]],
) -> dict[str, Conducta]:
    """Las conductas, a partir de las decisiones y de la telemetría de cada una.

    El representante es la decisión razonada más reciente de la conducta, que es el último juicio
    del motor sobre ella; si ninguna se razonó dentro del índice, la más reciente a secas.
    """
    conductas: dict[str, Conducta] = {}
    elegido: dict[str, tuple[bool, str]] = {}
    for doc_id, decision in decisiones:
        evento = evento_del_bus(decision, telemetria.get(doc_id))
        clave = firma.de_evento(evento)
        clasificacion = decision.get("decision", {})
        c = conductas.get(clave)
        if c is None:
            c = conductas[clave] = Conducta(
                firma=clave,
                piso=clasificacion.get("piso") or "",
                transfiere=transfiere(evento.command),
            )
        severidad = clasificacion.get("severidad") or ""
        c.decisiones += 1
        c.por_severidad[severidad] += 1

        razonada = not decision.get("ciclo", {}).get("reutilizada_de")
        momento = decision.get("@timestamp", "")
        if (razonada, momento) > elegido.get(clave, (False, "")):
            elegido[clave] = (razonada, momento)
            c.representante = doc_id
            c.severidad = severidad
            c.momento_del_representante = momento
    return conductas


def elegir(
    conductas: Iterable[Conducta], por_estrato: int = POR_ESTRATO, semilla: int = SEMILLA
) -> dict[str, Any]:
    """La muestra, con hasta `por_estrato` conductas de cada estrato, en un orden mezclado.

    Se mezcla para que quien revisa no pueda deducir el estrato del lugar en la fila: los estratos
    dicen si el motor escaló, que es justo lo que no tiene que saber.
    """
    generador = random.Random(semilla)
    por_estrato_de: dict[str, list[Conducta]] = {e: [] for e in ESTRATOS}
    for c in conductas:
        if c.estrato:
            por_estrato_de[c.estrato].append(c)

    elegidas: list[dict[str, Any]] = []
    resumen: dict[str, dict[str, int]] = {}
    for estrato in ESTRATOS:
        poblacion = sorted(por_estrato_de[estrato], key=lambda c: c.firma)
        tomadas = generador.sample(poblacion, min(por_estrato, len(poblacion)))
        resumen[estrato] = {
            "conductas": len(poblacion),
            "decisiones": sum(c.decisiones for c in poblacion),
            "en_la_muestra": len(tomadas),
        }
        elegidas.extend(
            {"doc_id": c.representante, "estrato": estrato, "firma": c.firma} for c in tomadas
        )
    generador.shuffle(elegidas)
    return {"estratos": resumen, "conductas": elegidas}


def _miles(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _pedir(ruta: str, cuerpo: dict[str, Any], metodo: str = "POST") -> dict[str, Any]:
    pedido = urllib.request.Request(
        f"{queries.ES_URL}{ruta}",
        data=json.dumps(cuerpo).encode(),
        headers={"Content-Type": "application/json"},
        method=metodo,
    )
    with urllib.request.urlopen(pedido, timeout=120) as resp:
        resultado: dict[str, Any] = json.load(resp)
        return resultado


def leer_decisiones() -> Iterator[tuple[str, dict[str, Any]]]:
    """Todas las decisiones del motor, con los campos que hacen falta para agruparlas."""
    campos = ["@timestamp", "evento", "decision.piso", "decision.severidad", "ciclo.reutilizada_de"]
    r = _pedir(f"/{DECISIONES}/_search?scroll=2m", {"size": 5000, "_source": campos})
    scroll = r.get("_scroll_id")
    try:
        while r["hits"]["hits"]:
            for h in r["hits"]["hits"]:
                yield h["_id"], h["_source"]
            r = _pedir("/_search/scroll", {"scroll": "2m", "scroll_id": scroll})
            scroll = r.get("_scroll_id")
    finally:
        if scroll:
            try:
                _pedir("/_search/scroll", {"scroll_id": scroll}, metodo="DELETE")
            except OSError:
                pass


def leer_telemetria(ids: list[str], de_a: int = 1000) -> dict[str, dict[str, Any]]:
    """El usuario y el comando de cada evento, buscados por identificador en la telemetría."""
    encontrados: dict[str, dict[str, Any]] = {}
    for i in range(0, len(ids), de_a):
        tanda = ids[i : i + de_a]
        cuerpo = {
            "size": len(tanda),
            "_source": ["user.name", "process.command_line"],
            "query": {"ids": {"values": tanda}},
        }
        for h in _pedir(f"/{queries.INDEX}/_search", cuerpo)["hits"]["hits"]:
            encontrados[h["_id"]] = h["_source"]
    return encontrados


def main() -> int:
    ap = argparse.ArgumentParser(description="Muestra estratificada para la revisión a ciegas.")
    ap.add_argument("--por-estrato", type=int, default=POR_ESTRATO)
    ap.add_argument("--semilla", type=int, default=SEMILLA)
    ap.add_argument("--seco", action="store_true", help="muestra los estratos sin escribir")
    ap.add_argument(
        "--reemplazar",
        action="store_true",
        help="reemplaza una muestra existente; las revisiones ya hechas quedan fuera de la nueva",
    )
    args = ap.parse_args()

    if MUESTRA_FILE.exists() and not (args.seco or args.reemplazar):
        print(
            f"Ya hay una muestra en {MUESTRA_FILE}. Cambiarla deja afuera lo que ya se revisó "
            "contra ella; para hacerlo igual, --reemplazar."
        )
        return 1

    decisiones = list(leer_decisiones())
    print(f"  {_miles(len(decisiones))} decisiones leídas")
    con_piso_alto = [
        doc_id for doc_id, d in decisiones if d.get("decision", {}).get("piso") == "alto"
    ]
    telemetria = leer_telemetria(con_piso_alto)
    faltantes = len(con_piso_alto) - len(telemetria)
    print(f"  {_miles(len(telemetria))} eventos de comandos encontrados, {faltantes} sin evento")

    conductas = agrupar(decisiones, telemetria)
    muestra = elegir(conductas.values(), args.por_estrato, args.semilla)
    print(f"  {_miles(len(conductas))} conductas distintas\n")
    print(f"  {'estrato':<28}{'conductas':>10}{'decisiones':>12}{'en la muestra':>15}")
    for estrato, r in muestra["estratos"].items():
        print(f"  {estrato:<28}{r['conductas']:>10}{r['decisiones']:>12}{r['en_la_muestra']:>15}")
    print(f"\n  {len(muestra['conductas'])} conductas para revisar a ciegas")

    if args.seco:
        return 0
    salida = {
        "generada": datetime.now(UTC).isoformat(timespec="seconds"),
        "semilla": args.semilla,
        "por_estrato": args.por_estrato,
        **muestra,
    }
    MUESTRA_FILE.write_text(json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Guardada en {MUESTRA_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
