"""Lo que no sale de la API hacia el panel aunque esté en los datos.

Las direcciones IPv4 se tapan en todo texto que llega a una persona que no las necesita: la del
honeypot, las de origen y las de la infraestructura que aparecen dentro de los comandos (un `wget`
contra el servidor que reparte el binario). Se tapan en el servidor y no en el panel, porque lo que
no viaja no se puede ver por accidente.
"""

from __future__ import annotations

import re
from typing import Any

DIRECCION = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
TAPADA = "x.x.x.x"


def sin_direcciones(valor: Any) -> Any:
    """El mismo valor, con cada dirección de cada texto tapada, a cualquier profundidad."""
    if isinstance(valor, str):
        return DIRECCION.sub(TAPADA, valor)
    if isinstance(valor, dict):
        return {clave: sin_direcciones(v) for clave, v in valor.items()}
    if isinstance(valor, list):
        return [sin_direcciones(v) for v in valor]
    return valor
