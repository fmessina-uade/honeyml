"""La telemetría tal como va llegando, para la vista en vivo del superadmin.

Son los eventos ya normalizados del índice, no los registros crudos de los sensores: leer esos pide
entrar a los volúmenes de los contenedores con permisos de administrador. Entre que el sensor
escribe y el evento aparece acá pasan los segundos del pipeline.

De cada evento viaja lo que sirve para seguir la actividad y nada que identifique a nadie: ni la
dirección de origen ni la del honeypot, y las que aparecen dentro de un comando van tapadas.
"""

from __future__ import annotations

from typing import Any

from . import queries
from .privacidad import sin_direcciones

CAMPOS = (
    "@timestamp",
    "honeypot",
    "event.category",
    "event.action",
    "event.outcome",
    "network.protocol",
    "destination.port",
    "user.name",
    "process.command_line",
    "url.original",
    "file.name",
    "source.geo.country_name",
    "source.geo.country_iso_code",
    "source.as.organization.name",
)
MAX_TAMANO = 100


def _plano(fuente: dict[str, Any], prefijo: str = "") -> dict[str, Any]:
    """Los campos de `CAMPOS` con su nombre punteado, vengan anidados o ya con puntos."""
    plano: dict[str, Any] = {}
    for clave, valor in fuente.items():
        if isinstance(valor, dict):
            plano.update(_plano(valor, f"{prefijo}{clave}."))
        elif f"{prefijo}{clave}" in CAMPOS:
            plano[f"{prefijo}{clave}"] = valor
    return plano


def en_vivo(
    despues: str | None = None, tamano: int = 40, es_url: str = queries.ES_URL
) -> dict[str, Any]:
    """Los últimos eventos, del más nuevo al más viejo. Con `despues`, solo los posteriores a ese
    momento: el panel pide con el del último que ya tiene y recibe solo lo que llegó."""
    filtro: list[dict[str, Any]] = [queries.NOT_LOCAL]
    if despues:
        filtro.append({"range": {"@timestamp": {"gt": despues}}})
    r = queries._search(
        {
            "size": min(max(tamano, 1), MAX_TAMANO),
            "_source": list(CAMPOS),
            "query": {"bool": {"filter": filtro}},
            "sort": [{"@timestamp": {"order": "desc"}}],
        },
        es_url,
    )
    eventos = [{"id": h["_id"], **sin_direcciones(_plano(h["_source"]))} for h in r["hits"]["hits"]]
    return {"eventos": eventos}
