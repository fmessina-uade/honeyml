"""La verificación de la reutilización por firma: una segunda clasificación, independiente, de una
muestra de conductas ya decididas, para medir cuánto coincide con la que el repertorio copia.

El repertorio copia la decisión de la primera repetición de cada firma a todas las demás. Para el
piso de severidad eso es correcto por construcción, porque sale de la categoría y el resultado, que
son campos de la firma; lo que no está garantizado es el valor exacto dentro de los límites ni la
táctica. Esta medición toma una muestra de firmas reutilizadas, razona de nuevo un evento ya copiado
de cada una sin consultar el repertorio y enfrenta la clasificación nueva con la copiada. El evento
se arma con la conducta más la dirección, el momento y la sesión que guardó la decisión, porque sin
dirección el nodo de contexto lo cortaría antes de razonarlo. De la severidad informa cuántas veces
cae en el mismo nivel y cuántas, aun difiriendo, siguen dentro de los límites del evento (la
invariante que vuelve defendible copiar); de la táctica, la coincidencia y en qué se fue cuando
difiere.

Cuesta una llamada de inferencia por firma, así que la muestra es chica y fija por semilla. Razona
con un almacén que no escribe y sin repertorio, de modo que no toca ni el corpus ni las firmas
guardadas. Se corre en el servidor con `make verificacion`; con `--seco` muestra la población sin
gastar, y con `--desde` se limita a las firmas nacidas de una fecha en adelante, para que la
clasificación guardada y la nueva salgan del mismo criterio.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import urllib.request
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import Any

from ..agent import firma, severidad
from ..agent.adapters.config import CredencialAusenteError
from ..agent.adapters.inferencia import CuotaAgotadaError
from ..agent.adapters.servicio import AdaptadorDeInferencia
from ..agent.consumer import EventoDelBus
from ..agent.graph import ejecutar
from ..agent.motor import compilar, costo_estimado
from ..agent.state import estado_inicial
from ..api import queries
from ..api.decisiones import DECISIONES
from .muestra import leer_telemetria

# Cuántas firmas entran en la muestra. Cada una cuesta una llamada de inferencia, así que el valor
# por defecto es un número que alcanza para una proporción creíble sin un gasto que pese.
CUANTAS = 50
SEMILLA = 42

SIN_TACTICA = "ninguna"


class _NoEscribe:
    """Un almacén que acepta todo y no escribe: la verificación no deja rastro en el corpus.

    El nodo de persistencia necesita un almacén para cerrar el ciclo, pero acá el resultado solo se
    compara en memoria. Devolver verdadero es decirle al grafo que la decisión quedó, que para el
    caso es cierto: quedó, en la comparación, y no en el índice.
    """

    def guardar(self, doc_id: str, documento: dict[str, Any]) -> bool:
        return True


@dataclass
class Conducta:
    """Una firma reutilizada, con el evento copiado que se vuelve a razonar y lo que se le copió."""

    firma: str
    representante: str = ""
    evento: dict[str, Any] = field(default_factory=dict)
    severidad: str = ""
    tactica: str | None = None
    momento: str = ""
    # El momento de la primera decisión de la firma, que es siempre la razonada original: ninguna
    # copia existe antes que el original del que copia. Sirve para quedarse con las firmas nacidas
    # bajo un criterio dado, sin arrastrar las que se decidieron con uno anterior.
    primera: str = ""
    decisiones: int = 0
    reutilizadas: int = 0


@dataclass
class Contraste:
    """El resultado de volver a razonar una conducta: lo copiado contra lo que salió de nuevo."""

    firma: str
    severidad_guardada: str
    severidad_fresca: str
    dentro_de_limites: bool
    tactica_guardada: str | None
    tactica_fresca: str | None


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
    """Las decisiones del motor, con lo que hace falta para agruparlas por firma y volver a razonar.

    La firma guardada evita recalcularla para agrupar, pero el usuario y el comando no viven en la
    decisión, así que el evento se reconstruye después con la telemetría del representante.
    """
    campos = [
        "@timestamp",
        "evento",
        "decision.severidad",
        "decision.tactica_mitre",
        "ciclo.firma",
        "ciclo.reutilizada_de",
    ]
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


def agrupar(decisiones: Iterable[tuple[str, dict[str, Any]]]) -> dict[str, Conducta]:
    """Las conductas por firma, con el evento copiado más reciente como representante.

    Se toma un evento copiado y no la decisión original razonada porque lo que se verifica es
    justamente lo que el repertorio sirve: la decisión que una repetición recibió sin razonar. La
    severidad y la táctica guardadas salen de ese mismo evento, que es lo que se le había copiado.
    """
    conductas: dict[str, Conducta] = {}
    for doc_id, d in decisiones:
        clave = d.get("ciclo", {}).get("firma") or ""
        if not clave:
            continue
        c = conductas.get(clave)
        if c is None:
            c = conductas[clave] = Conducta(firma=clave)
        c.decisiones += 1
        momento = str(d.get("@timestamp", ""))
        if momento and (not c.primera or momento < c.primera):
            c.primera = momento
        if not d.get("ciclo", {}).get("reutilizada_de"):
            continue
        c.reutilizadas += 1
        if momento >= c.momento:
            clasificacion = d.get("decision", {})
            c.momento = momento
            c.representante = doc_id
            c.evento = d.get("evento", {})
            c.severidad = clasificacion.get("severidad") or ""
            c.tactica = clasificacion.get("tactica_mitre")
    return conductas


def poblacion(conductas: Iterable[Conducta], desde: str | None = None) -> list[Conducta]:
    """Las conductas que sirven para verificar: reutilizadas y con representante.

    Con `desde` se queda solo con las firmas cuya primera decisión es de esa fecha en adelante, que
    es como se aísla un criterio: enfrentar la clasificación guardada bajo un criterio con una
    nueva hecha con otro mediría el cambio de criterio, no la estabilidad de la reutilización.
    """
    return [
        c
        for c in conductas
        if c.reutilizadas and c.representante and (not desde or c.primera >= desde)
    ]


def elegir(
    conductas: Iterable[Conducta], cuantas: int, semilla: int, desde: str | None = None
) -> list[Conducta]:
    """Muestra fija por semilla, ordenada antes de mezclar para no atarla al orden de ES."""
    poblado = sorted(poblacion(conductas, desde), key=lambda c: c.firma)
    generador = random.Random(semilla)
    return generador.sample(poblado, min(cuantas, len(poblado)))


def _primero(valor: Any) -> str:
    if isinstance(valor, list):
        return str(valor[0]) if valor else ""
    return "" if valor is None else str(valor)


def _evento(conducta: Conducta, telemetria: dict[str, Any] | None) -> EventoDelBus:
    """El evento reconstruido para volver a razonarlo.

    La conducta viene de la decisión guardada y el usuario con el comando, de la telemetría, igual
    que para la firma. Además se reponen la dirección, el momento y la sesión, que la firma no mira
    pero el nodo de contexto sí: sin la dirección no hay contexto que armar y el evento se corta
    antes de razonarlo. Reponerlos con lo que guardó la decisión es razonar el mismo evento, no uno
    parecido.
    """
    e = conducta.evento
    telemetria = telemetria or {}
    campos = {
        "doc_id": e.get("doc_id", ""),
        "timestamp": e.get("momento", ""),
        "honeypot": e.get("sensor") or "",
        "category": e.get("categoria") or "",
        "action": e.get("accion") or "",
        "outcome": e.get("resultado") or "",
        "protocol": e.get("protocolo") or "",
        "source_ip": e.get("origen") or "",
        "session": e.get("sesion") or "",
        "user": _primero(telemetria.get("user", {}).get("name")),
        "command": _primero(telemetria.get("process", {}).get("command_line")),
    }
    return EventoDelBus.desde_mensaje("", campos)


def contrastar(
    conducta: Conducta, telemetria: dict[str, Any] | None, compilado: Any
) -> Contraste | None:
    """Vuelve a razonar el evento representante y lo enfrenta con lo copiado.

    Devuelve None si la telemetría no deja reconstruir la misma firma (sin el usuario y el comando
    el evento no se puede volver a armar, y uno que firma distinto no es esta decisión), o si el
    grafo vuelve sin decisión.
    """
    evento = _evento(conducta, telemetria)
    if firma.de_evento(evento) != conducta.firma:
        return None
    estado = estado_inicial(evento)
    final: Any = ejecutar(compilado, estado)
    decision = final.get("decision")
    if decision is None:
        return None
    return Contraste(
        firma=conducta.firma,
        severidad_guardada=conducta.severidad,
        severidad_fresca=str(decision.severidad),
        dentro_de_limites=severidad.dentro_de_limites(decision.severidad, evento),
        tactica_guardada=conducta.tactica,
        tactica_fresca=decision.tactica_mitre,
    )


def comparar(contrastes: Iterable[Contraste]) -> dict[str, Any]:
    """Cuenta coincidencias de severidad y de táctica, y en qué se fue la táctica cuando difiere."""
    contrastes = list(contrastes)
    mismo_nivel = sum(1 for c in contrastes if c.severidad_fresca == c.severidad_guardada)
    distinto_dentro = sum(
        1 for c in contrastes if c.severidad_fresca != c.severidad_guardada and c.dentro_de_limites
    )
    fuera = sum(1 for c in contrastes if not c.dentro_de_limites)
    tactica_coincide = sum(1 for c in contrastes if c.tactica_fresca == c.tactica_guardada)
    derivas: Counter[tuple[str, str]] = Counter()
    for c in contrastes:
        if c.tactica_fresca != c.tactica_guardada:
            derivas[(c.tactica_guardada or SIN_TACTICA, c.tactica_fresca or SIN_TACTICA)] += 1
    return {
        "verificadas": len(contrastes),
        "severidad_mismo_nivel": mismo_nivel,
        "severidad_distinto_dentro": distinto_dentro,
        "severidad_fuera": fuera,
        "tactica_coincide": tactica_coincide,
        "derivas_de_tactica": dict(derivas),
    }


def _porcentaje(parte: int, total: int) -> str:
    return f"{parte / total * 100:.0f} %" if total else "sin datos"


def informe(resumen: dict[str, Any], poblada: int, consumo: str = "") -> str:
    """El texto del resultado, una línea por métrica."""
    n = resumen["verificadas"]
    lineas = [
        "  verificación de la reutilización por firma",
        "",
        f"  población: {poblada} firmas reutilizadas",
        f"  muestra: {n} firmas",
        "",
        "  severidad",
        f"    mismo nivel que lo copiado: {resumen['severidad_mismo_nivel']}/{n} "
        f"({_porcentaje(resumen['severidad_mismo_nivel'], n)})",
        f"    distinto pero dentro de los límites: {resumen['severidad_distinto_dentro']}/{n}",
        f"    fuera de los límites (cero por el piso): {resumen['severidad_fuera']}/{n}",
        "",
        "  táctica",
        f"    coincide: {resumen['tactica_coincide']}/{n} "
        f"({_porcentaje(resumen['tactica_coincide'], n)})",
    ]
    derivas = resumen["derivas_de_tactica"]
    if derivas:
        lineas.append("    difiere:")
        for (guardada, fresca), cuantas in sorted(derivas.items(), key=lambda kv: -kv[1]):
            lineas.append(f"      de {guardada} a {fresca}: {cuantas}")
    if consumo:
        lineas.extend(["", "  consumo de inferencia", consumo])
    return "\n".join(lineas)


def main() -> int:
    ap = argparse.ArgumentParser(description="Verifica la reutilización por firma.")
    ap.add_argument("--cuantas", type=int, default=CUANTAS, help="firmas en la muestra")
    ap.add_argument("--semilla", type=int, default=SEMILLA)
    ap.add_argument("--seco", action="store_true", help="muestra la población sin razonar")
    ap.add_argument(
        "--desde",
        default=None,
        help="solo firmas nacidas en esta fecha o después, ISO con forma AAAA-MM-DD",
    )
    args = ap.parse_args()

    conductas = agrupar(leer_decisiones())
    poblada = poblacion(conductas.values(), args.desde)
    muestra = elegir(conductas.values(), args.cuantas, args.semilla, args.desde)
    gasto = costo_estimado(len(muestra))
    desde_txt = f" nacidas desde {args.desde}" if args.desde else ""
    print(f"  {len(conductas)} firmas en el corpus, {len(poblada)} reutilizadas{desde_txt}")
    print(f"  muestra de {len(muestra)} firmas, gasto estimado USD {gasto:.2f}")
    if args.seco or not muestra:
        return 0

    try:
        inferencia = AdaptadorDeInferencia()
    except CredencialAusenteError as exc:
        print(f"  No se puede arrancar: {exc}")
        return 1

    telemetria = leer_telemetria([c.representante for c in muestra])
    compilado = compilar(servicio=inferencia, almacen=_NoEscribe(), repertorio=None)
    contrastes: list[Contraste] = []
    descartadas = 0
    for i, conducta in enumerate(muestra, start=1):
        try:
            contraste = contrastar(conducta, telemetria.get(conducta.representante), compilado)
        except CuotaAgotadaError as exc:
            print(f"\n  Se agotó la cuota del proveedor en la firma {i}: {exc}")
            print("  Se informa lo verificado hasta acá.")
            break
        if contraste is None:
            descartadas += 1
            continue
        contrastes.append(contraste)
        if i % 10 == 0:
            print(f"  {i}/{len(muestra)}")

    if descartadas:
        print(f"  {descartadas} firmas descartadas (firma distinta o sin decisión)")
    print()
    print(informe(comparar(contrastes), len(poblada), inferencia.resumen()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
