"""Los registros que el servidor escribe por su cuenta, para la vista de auditoría.

Son los de los scripts del anfitrión: los despliegues que deja `make deploy-vps`, los reinicios del
vigilante, el chequeo de salud y el respaldo diario. La API los ve por un montaje de solo lectura
del directorio de registros, y solo abre los que están en `FUENTES`. Los de Docker quedan afuera
porque leerlos pide el socket del motor de contenedores, que equivale a ser administrador del
servidor.

Se monta el directorio y no cada archivo porque Docker crea un directorio en lugar de un archivo
que todavía no existe, y eso rompería el script que después quiera escribirlo.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from .privacidad import sin_direcciones

DIRECTORIO = Path(os.environ.get("HONEYML_REGISTROS", "/registros-del-servidor"))

FUENTES = {
    "despliegues": "honeyml_despliegues.log",
    "vigilante": "honeyml_watchdog.log",
    "salud": "honeyml_health.log",
    "respaldo": "honeyml_backup.log",
}

# Los cuatro escriben igual: `[AAAA-MM-DD HH:MM:SS] texto`, en hora UTC.
_LINEA = re.compile(r"^\[(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2})\] (.*)$")
_ALERTA = re.compile(r"\b(ALERT|ERROR|AVISO|FALLO|CUELGUE|reinici)", re.IGNORECASE)

# Cuánto se lee desde el final de cada archivo. El de salud suma unas líneas cada cinco minutos y
# no tiene sentido recorrerlo entero para mostrar las últimas.
_COLA_BYTES = 256 * 1024


def _cola(archivo: Path, cuantas: int) -> list[str]:
    with archivo.open("rb") as f:
        f.seek(0, os.SEEK_END)
        tamano = f.tell()
        f.seek(max(tamano - _COLA_BYTES, 0))
        lineas = f.read().decode("utf-8", errors="replace").splitlines()
    # si se empezó a leer en el medio de un archivo, la primera línea está cortada
    if tamano > _COLA_BYTES:
        lineas = lineas[1:]
    return lineas[-cuantas:]


def _entrada(fuente: str, linea: str) -> dict[str, Any]:
    m = _LINEA.match(linea)
    texto = m.group(3) if m else linea
    return {
        "fuente": fuente,
        "momento": f"{m.group(1)}T{m.group(2)}Z" if m else None,
        "texto": sin_direcciones(texto),
        "alerta": bool(_ALERTA.search(texto)),
    }


def ultimas(cuantas: int = 150, directorio: Path | None = None) -> dict[str, Any]:
    """Las últimas líneas de cada fuente, juntas y de la más nueva a la más vieja.

    Una fuente sin archivo no es una falla: en una instalación nueva el registro de despliegues
    aparece con el primero.
    """
    base = directorio or DIRECTORIO
    if not base.is_dir():
        return {"disponible": False, "fuentes": {}, "entradas": []}
    ordenadas: list[tuple[str, dict[str, Any]]] = []
    fuentes: dict[str, bool] = {}
    for fuente, nombre in FUENTES.items():
        archivo = base / nombre
        fuentes[fuente] = archivo.is_file()
        if not fuentes[fuente]:
            continue
        # Una línea sin fecha es la continuación de un mensaje largo: se ordena con el momento de
        # la que tiene arriba, y como el orden es estable sigue debajo de ella.
        anterior = ""
        for linea in _cola(archivo, cuantas):
            if linea:
                entrada = _entrada(fuente, linea)
                anterior = entrada["momento"] or anterior
                ordenadas.append((anterior, entrada))
    ordenadas.sort(key=lambda par: par[0], reverse=True)
    entradas = [entrada for _, entrada in ordenadas[:cuantas]]
    return {"disponible": True, "fuentes": fuentes, "entradas": entradas}
