#!/usr/bin/env python3
"""Valida el indexado ECS en Elasticsearch.

Comprueba que la telemetría de los honeypots haya quedado indexada y normalizada como corresponde:
conteos por índice, cobertura de los campos ECS clave, que no haya eventos sin rutear ni fallas al
parsear fechas, y un reparto rápido de eventos. Sin dependencias externas, solo biblioteca estándar.

Se corre con `python3 validate_indexing.py --es-url http://localhost:9200`. Con `--hasta` cuenta
solo lo indexado hasta ese instante, así la salida reproduce un corte de cifras aunque el índice
siga creciendo.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

OK = "\033[92m[ok]\033[0m"
WARN = "\033[93m[aviso]\033[0m"
FAIL = "\033[91m[falla]\033[0m"

# Cada índice diario contesta solo sus primeros valores y Elasticsearch suma esas respuestas: un
# valor que un día queda afuera pierde los eventos de ese día. Con dos mil por índice, el reparto
# coincide con el conteo exacto.
RECORTE_POR_INDICE = 2000


def es(url: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{url}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST" if data else "GET",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def con_rango(query: dict | None, rango: dict | None) -> dict | None:
    """La consulta con el límite temporal sumado, o la misma si no hay límite."""
    partes = [q for q in (query, rango) if q]
    if len(partes) < 2:
        return partes[0] if partes else None
    return {"bool": {"filter": partes}}


def count(url: str, index: str, query: dict | None = None) -> int:
    body = {"query": query} if query else None
    return es(url, f"/{index}/_count", body).get("count", 0)


def terms(
    url: str, index: str, field: str, size: int = 10, query: dict | None = None
) -> list[tuple[str, int]]:
    agg = {"terms": {"field": field, "size": size, "shard_size": RECORTE_POR_INDICE}}
    body: dict = {"size": 0, "aggs": {"t": agg}}
    if query:
        body["query"] = query
    res = es(url, f"/{index}/_search", body)
    buckets = res.get("aggregations", {}).get("t", {}).get("buckets", [])
    return [(b["key"], b["doc_count"]) for b in buckets]


def _fecha_del_indice(nombre: str) -> str:
    """honeypot-<sensor>-AAAA.MM.DD da AAAA-MM-DD, comparable con el inicio de un instante ISO."""
    return nombre.rsplit("-", 1)[-1].replace(".", "-")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--es-url", default="http://localhost:9200")
    ap.add_argument("--index", default="honeypot-*")
    ap.add_argument(
        "--resumen",
        action="store_true",
        help="salida compacta para capturas de pantalla: colapsa la lista de índices y omite "
        "las direcciones de origen y los usuarios probados",
    )
    ap.add_argument(
        "--hasta",
        help="cuenta solo hasta este instante, en ISO 8601 (por ejemplo 2026-10-03T22:00:59Z)",
    )
    args = ap.parse_args()
    url = args.es_url.rstrip("/")
    rango = {"range": {"@timestamp": {"lte": args.hasta}}} if args.hasta else None

    try:
        health = es(url, "/_cluster/health")
    except (urllib.error.URLError, OSError) as exc:
        print(f"{FAIL} No se pudo conectar a Elasticsearch en {url}: {exc}")
        return 1

    print("\nEstado del cluster")
    print(f"  status={health['status']}  nodos={health['number_of_nodes']}")

    titulo = f"Índices ({args.index})" + (f", hasta {args.hasta}" if args.hasta else "")
    print(f"\n{titulo}")
    try:
        cat = es(url, f"/_cat/indices/{args.index}?format=json&bytes=mb")
    except urllib.error.HTTPError:
        cat = []
    if args.hasta:
        cat = [i for i in cat if _fecha_del_indice(i["index"]) <= args.hasta[:10]]
    if not cat:
        print(f"  {WARN} No hay índices que coincidan con {args.index}. ¿Ya se ingirió algo?")
        return 1

    total = 0
    by_sensor: dict[str, int] = {}
    size_mb = 0.0
    for idx in sorted(cat, key=lambda i: i["index"]):
        # El conteo de _cat es el del momento. Con un límite temporal se cuenta con el filtro.
        docs = count(url, idx["index"], rango) if rango else int(idx.get("docs.count") or 0)
        total += docs
        size_mb += float(idx.get("store.size") or 0)
        # honeypot-<sensor>-<fecha>
        parts = idx["index"].split("-")
        if len(parts) >= 2:
            by_sensor[parts[1]] = by_sensor.get(parts[1], 0) + docs
        if not args.resumen:
            print(f"  {idx['index']:<32} docs={docs:>8}  size={idx.get('store.size', '?')}mb")
    # El tamaño en disco no se puede llevar a un instante pasado, así que con límite no se informa.
    tamano = "" if args.hasta else f"  ({size_mb:.0f} mb)"
    if args.resumen:
        for sensor, docs in sorted(by_sensor.items()):
            n_idx = sum(1 for i in cat if i["index"].split("-")[1:2] == [sensor])
            print(f"  {sensor:<12} {n_idx:>3} índices diarios  docs={docs:>9}")
        print(f"  {'total':<12} {len(cat):>3} índices          docs={total:>9}{tamano}")
    else:
        print(f"  {'total':<32} docs={total:>8}{tamano}")

    checks_ok = True

    print("\nIntegridad de enrutamiento")
    try:
        unrouted = count(url, "honeypot-unrouted-*", rango)
    except urllib.error.HTTPError:
        unrouted = 0
    if unrouted == 0:
        print(f"  {OK} 0 eventos sin enrutar")
    else:
        print(f"  {FAIL} {unrouted} eventos en honeypot-unrouted-* (revisar Filebeat y Logstash)")
        checks_ok = False

    print(f"\nCobertura de campos ECS (sobre {total} docs)")
    ecs_fields = [
        "@timestamp",
        "event.category",
        "event.action",
        "event.outcome",
        "source.ip",
        "observer.type",
    ]
    for field in ecs_fields:
        n = count(url, args.index, con_rango({"exists": {"field": field}}, rango))
        pct = (n / total * 100) if total else 0
        mark = OK if pct >= 99 else (WARN if pct >= 50 else FAIL)
        # source.ip no está en todos los eventos: se informa sin penalizar
        note = "  (esperable <100%)" if field == "source.ip" else ""
        print(f"  {mark} {field:<18} {n:>8} ({pct:5.1f}%){note}")
        if field in ("@timestamp", "event.category", "observer.type") and pct < 99:
            checks_ok = False

    datefail = count(
        url,
        args.index,
        con_rango(
            {"terms": {"tags": ["_dateparsefailure_cowrie", "_dateparsefailure_dionaea"]}}, rango
        ),
    )
    mark = OK if datefail == 0 else FAIL
    print(f"  {mark} sin fallos de parseo de fecha ({datefail} con _dateparsefailure)")
    if datefail:
        checks_ok = False

    # reparto de eventos, que después alimenta el EDA
    print("\nDistribución por event.action")
    for key, n in terms(url, args.index, "event.action", 15, rango):
        print(f"  {n:>8}  {key}")

    print("\nDistribución por event.category")
    for key, n in terms(url, args.index, "event.category", 15, rango):
        print(f"  {n:>8}  {key}")

    # Las direcciones y los usuarios quedan fuera del resumen: es la salida que se captura, y
    # entre los usuarios más probados hay uno que delata la dirección del propio servidor.
    if not args.resumen:
        print("\nTop 10 source.ip")
        try:
            for key, n in terms(url, args.index, "source.ip", 10, rango):
                print(f"  {n:>8}  {key}")
        except urllib.error.HTTPError:
            print("  (sin datos)")

        print("\nTop credenciales probadas (user.name)")
        for key, n in terms(url, args.index, "user.name", 10, rango):
            print(f"  {n:>8}  {key}")

    print()
    if checks_ok:
        print(f"{OK} Validación de indexación ECS: OK")
        return 0
    print(f"{FAIL} Validación de indexación ECS: con observaciones (ver arriba)")
    return 2


if __name__ == "__main__":
    sys.exit(main())
