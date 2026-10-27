"""Exporta e importa el estado que el motor guarda en el bus: el repertorio de firmas y las marcas
de eventos ya procesados.

Sirve para cambiar el servidor del bus sin perder el repertorio. La copia es a nivel de aplicación,
clave por clave, y no con el archivo de persistencia, porque ese formato cambia entre versiones y un
servidor no siempre lee el de otro. Cada clave viaja con el momento absoluto en que vence, así el
rato que pasa entre exportar e importar no le estira la vida.

El stream y el grupo de consumidores no se copian. Con el bus sin atraso no queda nada por entregar,
y el motor recrea el grupo al arrancar. Por eso exportar se niega si el grupo tiene atraso o
pendientes: lo que se quedara en el stream viejo no le llegaría nunca al motor.

La exportación sale por la salida estándar, una clave por línea, y la importación la lee de la
entrada estándar. Así corre adentro del contenedor de análisis y el archivo queda del lado del
servidor, sin montar nada con permiso de escritura:

    python scripts/estado_del_bus.py contar --host valkey
    python scripts/estado_del_bus.py exportar --host redis > estado.jsonl
    python scripts/estado_del_bus.py importar --host valkey < estado.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Iterator
from typing import Any, TextIO

import redis

from honeyml.agent.adapters.repertorio import PREFIJO as PREFIJO_FIRMA
from honeyml.agent.consumer import GROUP, PREFIJO_VISTO, STREAM

PREFIJOS = (PREFIJO_FIRMA, PREFIJO_VISTO)
LOTE = 500


def _conectar(host: str, puerto: int, contrasena: str | None) -> redis.Redis:
    r = redis.Redis(
        host=host, port=puerto, password=contrasena, decode_responses=True, socket_timeout=10
    )
    r.ping()
    return r


def _ahora_ms() -> int:
    return int(time.time() * 1000)


def _claves(r: redis.Redis, prefijo: str) -> Iterator[str]:
    for clave in r.scan_iter(match=f"{prefijo}*", count=1000):
        yield str(clave)


def _lotes(claves: Iterator[str]) -> Iterator[list[str]]:
    lote: list[str] = []
    for clave in claves:
        lote.append(clave)
        if len(lote) == LOTE:
            yield lote
            lote = []
    if lote:
        yield lote


def _grupo(r: redis.Redis) -> dict[str, Any] | None:
    """El estado del grupo del motor, o None si el stream o el grupo no existen."""
    try:
        grupos: Any = r.xinfo_groups(STREAM)
    except redis.ResponseError:
        return None
    for g in grupos:
        if g.get("name") == GROUP:
            return dict(g)
    return None


def contar(r: redis.Redis, salida: TextIO) -> dict[str, int]:
    cuentas = {prefijo: sum(1 for _ in _claves(r, prefijo)) for prefijo in PREFIJOS}
    for prefijo, n in cuentas.items():
        print(f"  {prefijo}*  {n}", file=salida)
    largo = r.xlen(STREAM) if r.exists(STREAM) else 0
    grupo = _grupo(r)
    detalle = (
        f"pendientes {grupo.get('pending')}, atraso {grupo.get('lag')}" if grupo else "sin grupo"
    )
    print(f"  stream {STREAM}: {largo} entradas, grupo '{GROUP}': {detalle}", file=salida)
    return cuentas


def exportar(r: redis.Redis, destino: TextIO, forzar: bool) -> int:
    grupo = _grupo(r)
    if grupo and (grupo.get("pending") or grupo.get("lag")) and not forzar:
        print(
            f"  el grupo '{GROUP}' tiene {grupo.get('pending')} pendientes y {grupo.get('lag')} de "
            "atraso: hay que esperar a que el motor los vacíe antes de exportar",
            file=sys.stderr,
        )
        return 1
    total = 0
    for prefijo in PREFIJOS:
        exportadas = 0
        for lote in _lotes(_claves(r, prefijo)):
            tuberia = r.pipeline(transaction=False)
            for clave in lote:
                tuberia.get(clave)
                tuberia.pttl(clave)
            respuestas = tuberia.execute()
            ahora = _ahora_ms()
            for i, clave in enumerate(lote):
                valor, restante = respuestas[2 * i], respuestas[2 * i + 1]
                # Una clave que vence entre el recorrido y la lectura se saltea.
                if valor is None or restante == -2:
                    continue
                vence = None if restante == -1 else ahora + int(restante)
                linea = {"clave": clave, "valor": valor, "vence_ms": vence}
                destino.write(json.dumps(linea, ensure_ascii=False) + "\n")
                exportadas += 1
        print(f"  {prefijo}*  {exportadas} exportadas", file=sys.stderr)
        total += exportadas
    print(f"  total: {total}", file=sys.stderr)
    return 0


def importar(r: redis.Redis, origen: TextIO) -> int:
    cuentas = {prefijo: 0 for prefijo in PREFIJOS}
    vencidas = 0
    tuberia = r.pipeline(transaction=False)
    pendientes_en_tuberia = 0
    for numero, linea in enumerate(origen, start=1):
        if not linea.strip():
            continue
        dato = json.loads(linea)
        clave, valor, vence = dato["clave"], dato["valor"], dato["vence_ms"]
        prefijo = next((p for p in PREFIJOS if clave.startswith(p)), None)
        if prefijo is None:
            print(f"  línea {numero}: clave fuera de los prefijos esperados", file=sys.stderr)
            return 1
        if vence is None:
            tuberia.set(clave, valor)
        else:
            restante = int(vence) - _ahora_ms()
            if restante <= 0:
                vencidas += 1
                continue
            tuberia.set(clave, valor, px=restante)
        cuentas[prefijo] += 1
        pendientes_en_tuberia += 1
        if pendientes_en_tuberia == LOTE:
            tuberia.execute()
            pendientes_en_tuberia = 0
    tuberia.execute()
    for prefijo, n in cuentas.items():
        print(f"  {prefijo}*  {n} importadas", file=sys.stderr)
    print(f"  vencidas en el traslado, no se importaron: {vencidas}", file=sys.stderr)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("accion", choices=["contar", "exportar", "importar"])
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--puerto", type=int, default=6379)
    ap.add_argument("--contrasena", default=os.getenv("BUS_PASSWORD") or None)
    ap.add_argument(
        "--forzar",
        action="store_true",
        help="exportar aunque el grupo tenga atraso o pendientes",
    )
    args = ap.parse_args()

    try:
        r = _conectar(args.host, args.puerto, args.contrasena)
    except redis.RedisError as exc:
        print(f"  no se pudo conectar a {args.host}:{args.puerto}: {exc}", file=sys.stderr)
        return 1

    if args.accion == "contar":
        contar(r, sys.stdout)
        return 0
    if args.accion == "exportar":
        return exportar(r, sys.stdout, args.forzar)
    return importar(r, sys.stdin)


if __name__ == "__main__":
    sys.exit(main())
