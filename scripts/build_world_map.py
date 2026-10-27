"""Convierte un atlas mundial en TopoJSON en el contorno compacto que dibuja el globo.

Genera el contorno una sola vez, así el panel no carga una biblioteca de TopoJSON del lado del
cliente ni decodifica en cada carga los deltas cuantizados del archivo crudo (más de cien KB) para
dibujar una esfera de 320 píxeles. Lo que viaja son arreglos de coordenadas.

Va simplificado porque el contorno original tiene mucho más detalle del que un globo de ese tamaño
puede mostrar: a 320 píxeles de ancho, un grado de longitud no llega a un píxel, así que simplificar
saca puntos que a ese tamaño no se distinguen.

El resultado queda versionado en el repositorio. El script sirve para regenerarlo y auditarlo, y
queda fuera del build porque necesita salir a la red, que puede estar caída.

Fuente: world-atlas (Natural Earth 110m), dominio público.
    curl -o countries-110m.json https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json
    python scripts/build_world_map.py countries-110m.json

Uso:
    python scripts/build_world_map.py <countries-110m.json> [--tolerancia 0.8]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

SALIDA = Path("dashboard/src/lib/world.ts")

Punto = tuple[float, float]


def decodificar_arcos(topo: dict[str, Any]) -> list[list[Punto]]:
    """Deshace la codificación por deltas y la cuantización de TopoJSON, a pares lon/lat absolutos.

    Cada arco guarda su primer punto como absoluto cuantizado y el resto como deltas respecto del
    anterior; la transformación devuelve esa grilla de enteros a grados.
    """
    t = topo["transform"]
    sx, sy = t["scale"]
    tx, ty = t["translate"]

    arcos: list[list[Punto]] = []
    for arco in topo["arcs"]:
        x = y = 0
        puntos: list[Punto] = []
        for dx, dy in arco:
            x += dx
            y += dy
            puntos.append((x * sx + tx, y * sy + ty))
        arcos.append(puntos)
    return arcos


def _perpendicular(p: Punto, a: Punto, b: Punto) -> float:
    """Distancia de p al segmento a-b, en grados. A esta escala alcanza y sobra."""
    (px, py), (ax, ay), (bx, by) = p, a, b
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    tt = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    cx, cy = ax + tt * dx, ay + tt * dy
    return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5


def simplificar(puntos: list[Punto], tolerancia: float) -> list[Punto]:
    """Douglas-Peucker, iterativo para que una costa larga no reviente el límite de recursión."""
    if len(puntos) < 3:
        return puntos

    conservar = [False] * len(puntos)
    conservar[0] = conservar[-1] = True
    pila = [(0, len(puntos) - 1)]

    while pila:
        ini, fin = pila.pop()
        if fin - ini < 2:
            continue
        peor, dist = -1, tolerancia
        for i in range(ini + 1, fin):
            d = _perpendicular(puntos[i], puntos[ini], puntos[fin])
            if d > dist:
                peor, dist = i, d
        if peor != -1:
            conservar[peor] = True
            pila.append((ini, peor))
            pila.append((peor, fin))

    return [p for p, c in zip(puntos, conservar, strict=True) if c]


def anillos(geom: dict[str, Any], arcos: list[list[Punto]]) -> list[list[Punto]]:
    """Resuelve las referencias a arcos de una geometría en anillos cerrados.

    Un índice negativo significa que el arco va al revés, codificado como ~i, que es la forma en que
    TopoJSON deja que dos países compartan la frontera entre ellos en vez de guardarla dos veces.
    """
    if geom["type"] == "Polygon":
        listas = geom["arcs"]
    elif geom["type"] == "MultiPolygon":
        listas = [anillo for poly in geom["arcs"] for anillo in poly]
    else:
        return []

    salida = []
    for refs in listas:
        puntos: list[Punto] = []
        for ref in refs:
            arco = arcos[~ref][::-1] if ref < 0 else arcos[ref]
            puntos.extend(arco[1:] if puntos else arco)
        salida.append(puntos)
    return salida


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("topojson", type=Path)
    ap.add_argument(
        "--tolerancia",
        type=float,
        default=0.8,
        help="grados; más alto simplifica más. 0,8 es cerca de un píxel en un globo de 320",
    )
    ap.add_argument(
        "--minimo",
        type=int,
        default=5,
        help="anillos con menos puntos que esto se descartan: son islas invisibles a esta escala",
    )
    args = ap.parse_args()

    topo = json.loads(args.topojson.read_text(encoding="utf-8"))
    arcos = decodificar_arcos(topo)

    originales = 0
    figuras: list[list[list[float]]] = []
    for geom in topo["objects"]["countries"]["geometries"]:
        for anillo in anillos(geom, arcos):
            originales += len(anillo)
            simple = simplificar(anillo, args.tolerancia)
            if len(simple) >= args.minimo:
                figuras.append([[round(x, 2), round(y, 2)] for x, y in simple])

    puntos = sum(len(f) for f in figuras)
    compacto = json.dumps(figuras, separators=(",", ":"))

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(
        "// Generado por scripts/build_world_map.py, no editar a mano.\n"
        "//\n"
        "// Contornos de países del atlas world-atlas (Natural Earth 110m, dominio público),\n"
        f"// simplificados con Douglas-Peucker a {args.tolerancia} grados de tolerancia.\n"
        f"// {len(figuras)} anillos, {puntos} puntos.\n"
        "//\n"
        "// Cada anillo es una lista de pares [longitud, latitud] en grados.\n"
        f"export const WORLD: [number, number][][] = {compacto};\n",
        encoding="utf-8",
    )

    print(f"  anillos: {len(figuras)}")
    print(f"  puntos: {originales:,} antes, {puntos:,} después".replace(",", "."))
    print(f"  tamaño: {len(compacto) / 1024:.0f} KB")
    print(f"  escrito en {SALIDA}")


if __name__ == "__main__":
    main()
