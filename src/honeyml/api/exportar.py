"""Los reportes en CSV: las decisiones de un filtro y los veredictos del analista.

Las columnas son las del panel y nada más. La dirección de origen no sale en ningún caso, ni las que
aparecen dentro del resumen de un comando: un reporte se reenvía, se pega en un documento y termina
lejos de la API.

Llevan la marca de orden de bytes de UTF-8 adelante porque, sin ella, Excel lee las tildes como
Latin-1.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Sequence
from typing import Any

from .privacidad import sin_direcciones

BOM = "\ufeff"

COLUMNAS_DECISIONES = (
    ("momento", "momento del evento"),
    ("decidida", "momento de la decisión"),
    ("sensor", "sensor"),
    ("categoria", "categoría"),
    ("resultado", "resultado"),
    ("protocolo", "protocolo"),
    ("resumen", "resumen"),
    ("severidad", "severidad"),
    ("tactica_mitre", "táctica MITRE"),
    ("confianza", "confianza"),
    ("concluyente", "concluyente"),
    ("copiada", "copiada del repertorio"),
    ("requiere_revision", "requiere revisión"),
    ("modelo", "modelo"),
    ("segundos", "segundos del modelo"),
    ("veredicto", "veredicto"),
    ("severidad_analista", "severidad del analista"),
    ("tactica_analista", "táctica del analista"),
    ("a_ciegas", "revisada a ciegas"),
)

COLUMNAS_REVISIONES = (
    ("@timestamp", "momento del veredicto"),
    ("usuario", "analista"),
    ("veredicto", "veredicto"),
    ("a_ciegas", "a ciegas"),
    ("estrato", "estrato"),
    ("severidad", "severidad del analista"),
    ("tactica_mitre", "táctica del analista"),
    ("severidad_motor", "severidad del motor"),
    ("tactica_motor", "táctica del motor"),
    ("nota", "nota"),
    ("doc_id", "identificador del evento"),
)


def _valor(v: Any) -> Any:
    if isinstance(v, bool):
        return "sí" if v else "no"
    return "" if v is None else sin_direcciones(v)


def _csv(columnas: Sequence[tuple[str, str]], filas: Iterable[dict[str, Any]]) -> str:
    salida = io.StringIO()
    salida.write(BOM)
    escritor = csv.writer(salida, lineterminator="\r\n")
    escritor.writerow([titulo for _, titulo in columnas])
    for fila in filas:
        escritor.writerow([_valor(fila.get(campo)) for campo, _ in columnas])
    return salida.getvalue()


def decisiones_csv(items: Iterable[dict[str, Any]]) -> str:
    def plana(d: dict[str, Any]) -> dict[str, Any]:
        revision = d.get("revision") or {}
        return {
            **d,
            "veredicto": revision.get("veredicto"),
            "severidad_analista": revision.get("severidad"),
            "tactica_analista": revision.get("tactica_mitre"),
            "a_ciegas": bool(revision.get("a_ciegas")) if revision else None,
        }

    return _csv(COLUMNAS_DECISIONES, (plana(d) for d in items))


def revisiones_csv(revisiones: Iterable[dict[str, Any]]) -> str:
    def plana(r: dict[str, Any]) -> dict[str, Any]:
        motor = r.get("motor") or {}
        return {
            **r,
            "a_ciegas": bool(r.get("a_ciegas")),
            "severidad_motor": motor.get("severidad"),
            "tactica_motor": motor.get("tactica_mitre"),
        }

    return _csv(COLUMNAS_REVISIONES, (plana(r) for r in revisiones))
