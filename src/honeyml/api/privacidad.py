"""Lo que no sale de la API hacia el panel aunque esté en los datos.

Las direcciones y los destinos se tapan en todo texto que llega a una persona que no los necesita:
la dirección del honeypot, las de origen, y la infraestructura que aparece dentro de los comandos
(un `wget` contra el servidor que reparte el binario). Alcanza con las direcciones IPv4, el host de
una URL con esquema, y un dominio usado como host (seguido de una barra). Un dominio suelto sin ruta
se deja, porque separarlo de un nombre de archivo como `config.json` sin tocar el comando no es
confiable. Se tapa en el servidor y no en el panel, porque lo que no viaja no se puede ver por
accidente.
"""

from __future__ import annotations

import re
from typing import Any

DIRECCION = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
TAPADA = "x.x.x.x"

# El host de una URL con esquema: desde `esquema://` hasta la barra, el signo de pregunta o el
# final. Se conserva el esquema y la ruta, así el comando sigue diciendo que descarga algo.
HOST_DE_URL = re.compile(r"\b([a-z][a-z0-9+.-]*://)[^/\s?#]+")
# Un dominio usado como host, es decir seguido de una barra. El dominio exige un último tramo de dos
# letras o más, así `x.x.x.x` (ya tapado) y nombres como `a.sh` sin barra no entran.
DOMINIO_CON_RUTA = re.compile(r"\b(?:[a-z0-9-]+\.)+[a-z]{2,}(?=/)", re.IGNORECASE)
HOST_TAPADO = "tapado"

# Una credencial con forma de dirección es un fragmento de una IP que el atacante probó como usuario
# o contraseña, y uno de esos fragmentos es parte de la dirección del propio servidor. Tres grupos
# alcanzan para reconocerla, aun cuando sea una dirección cortada que no llega a los cuatro octetos.
PARECE_DIRECCION = re.compile(r"\d{1,3}\.\d{1,3}\.\d{1,3}")


def parece_direccion(texto: object) -> bool:
    return bool(PARECE_DIRECCION.search(str(texto)))


def sin_credenciales_con_direccion(
    cubos: list[dict[str, Any]], tope: int | None = None
) -> list[dict[str, Any]]:
    """El ranking sin las entradas con forma de dirección, recortado al tope si se pide.

    Se piden más de las que se muestran y se descarta acá, así ninguna dirección sale en la
    respuesta aunque el panel muestre menos de las que vienen.
    """
    limpios = [c for c in cubos if not parece_direccion(c.get("key"))]
    return limpios[:tope] if tope is not None else limpios


def _tapar_texto(texto: str) -> str:
    """Un texto con las direcciones, el host de las URL y los dominios con ruta tapados.

    Primero las IPv4, así una URL contra una dirección queda con el host ya tapado y el dominio no
    la vuelve a tocar.
    """
    texto = DIRECCION.sub(TAPADA, texto)
    texto = HOST_DE_URL.sub(rf"\1{HOST_TAPADO}", texto)
    return DOMINIO_CON_RUTA.sub(HOST_TAPADO, texto)


def sin_direcciones(valor: Any) -> Any:
    """El mismo valor, con cada dirección y destino tapado, a cualquier profundidad."""
    if isinstance(valor, str):
        return _tapar_texto(valor)
    if isinstance(valor, dict):
        return {clave: sin_direcciones(v) for clave, v in valor.items()}
    if isinstance(valor, list):
        return [sin_direcciones(v) for v in valor]
    return valor
