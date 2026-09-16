"""Arma la consulta que le permite a un visitante comparar su contraseña con las capturadas.

El diseño de privacidad es el punto, y es el mismo que usa Have I Been Pwned (k-anonimato):

  1. El navegador hashea con SHA-256 la contraseña tipeada y manda solo los primeros cinco
     caracteres hexadecimales del resumen.
  2. El servicio contesta con todos los hashes capturados que comparten ese prefijo, y su conteo.
  3. El navegador termina la comparación localmente.

La contraseña nunca sale del navegador, y el servicio no puede saber por cuál de los hashes
devueltos estaba preguntando el visitante. Pedirle a alguien que tipee una contraseña real en un
formulario que la transmite enseñaría exactamente la lección equivocada, y en un panel cuyo tema
entero son los ataques a credenciales eso sería indefendible.

Uso:
    python -m honeyml.education.password_index
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any

ES_URL = os.environ.get("ES_URL", "http://localhost:9200")
INDEX = "honeypot-*"
OUT_FILE = Path("data/processed/password_index.json")
PREFIX_LEN = 5

# Cuántas contraseñas distintas se piden por página.
#
# Se pagina con un `composite` y no con un `terms` de una sola consulta: Elasticsearch corta en
# 65.536 cubos por agregado y devuelve 400, y la cantidad de contraseñas distintas supera ese techo
# y solo va a seguir creciendo. Con el `terms`, el refresh entero corta en este paso.
POR_PAGINA = 10_000

# Cuántas páginas se aceptan antes de cortar. Con el tamaño de arriba son cinco millones de
# contraseñas distintas, muy por encima de cualquier cosa que estos sensores puedan capturar. Está
# para que un error de paginación no deje el proceso girando para siempre.
MAX_PAGINAS = 500


def _pagina(es_url: str, despues: dict[str, Any] | None) -> dict[str, Any]:
    """Una página del agregado compuesto, desde donde haya quedado la anterior."""
    compuesto: dict[str, Any] = {
        "sources": [{"clave": {"terms": {"field": "cowrie.password"}}}],
        "size": POR_PAGINA,
    }
    if despues is not None:
        compuesto["after"] = despues
    body = {
        "size": 0,
        "query": {"bool": {"must_not": [{"term": {"source.ip": "127.0.0.1"}}]}},
        "aggs": {"p": {"composite": compuesto}},
    }
    req = urllib.request.Request(
        f"{es_url}/{INDEX}/_search",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        datos: dict[str, Any] = json.load(resp)
    agregado: dict[str, Any] = datos["aggregations"]["p"]
    return agregado


def fetch_passwords(es_url: str = ES_URL) -> list[tuple[str, int]]:
    """Cada contraseña distinta capturada, con cuántas veces se intentó."""
    encontradas: list[tuple[str, int]] = []
    despues: dict[str, Any] | None = None
    for _ in range(MAX_PAGINAS):
        agregado = _pagina(es_url, despues)
        cubos = agregado.get("buckets") or []
        encontradas += [(str(b["key"]["clave"]), int(b["doc_count"])) for b in cubos]
        despues = agregado.get("after_key")
        # Sin `after_key` no hay más páginas. El corte por página incompleta no sirve: la última
        # puede venir llena y `after_key` es lo único que dice si quedó algo atrás.
        if despues is None or not cubos:
            break
    return encontradas


def build(es_url: str = ES_URL) -> dict[str, Any]:
    """Agrupa las contraseñas hasheadas por prefijo del resumen."""
    passwords = fetch_passwords(es_url)
    buckets: dict[str, list[list[Any]]] = defaultdict(list)
    for raw, count in passwords:
        digest = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()
        buckets[digest[:PREFIX_LEN]].append([digest[PREFIX_LEN:], count])

    total_attempts = sum(c for _, c in passwords)
    return {
        "prefix_len": PREFIX_LEN,
        "distinct": len(passwords),
        "attempts": total_attempts,
        "buckets": buckets,
    }


def load() -> dict[str, Any] | None:
    if not OUT_FILE.exists():
        return None
    parsed: dict[str, Any] = json.loads(OUT_FILE.read_text(encoding="utf-8"))
    return parsed


def lookup(prefix: str, index: dict[str, Any]) -> dict[str, Any]:
    """Todo lo que el cliente necesita para terminar la comparación por su cuenta."""
    matches = index.get("buckets", {}).get(prefix.lower(), [])
    return {
        "prefix": prefix.lower(),
        "matches": [{"suffix": s, "count": c} for s, c in matches],
        "distinct": index.get("distinct", 0),
        "attempts": index.get("attempts", 0),
    }


def main() -> None:
    index = build()
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")

    size_mb = OUT_FILE.stat().st_size / 1024 / 1024
    print(f"Índice de contraseñas -> {OUT_FILE} ({size_mb:.1f} MB)")
    print(f"  {index['distinct']:,} contraseñas distintas".replace(",", "."))
    print(f"  {index['attempts']:,} intentos en total".replace(",", "."))
    print(f"  {len(index['buckets']):,} prefijos de {PREFIX_LEN} caracteres".replace(",", "."))
    print("\nLa contraseña nunca sale del navegador: solo viaja el prefijo del hash.")


if __name__ == "__main__":
    main()
