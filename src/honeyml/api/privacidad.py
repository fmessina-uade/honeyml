"""Lo que no sale de la API hacia el panel aunque esté en los datos.

Las direcciones y los destinos se tapan en todo texto que llega a una persona que no los necesita:
la dirección del honeypot, las de origen, y la infraestructura que aparece dentro de los comandos
(un `wget` contra el servidor que reparte el binario). Alcanza con las direcciones IPv4, el host de
una URL con esquema, y un dominio usado como host (seguido de una barra). Un dominio suelto sin ruta
se deja, porque separarlo de un nombre de archivo como `config.json` sin tocar el comando no es
confiable. Una dirección escondida en base64 o en escapes hexadecimales también se tapa. Se tapa en
el servidor y no en el panel, porque lo que no viaja no se puede ver por accidente.
"""

from __future__ import annotations

import base64
import binascii
import re
from typing import Any

# Alrededor de la dirección se pide que no haya otro dígito, y no un límite de palabra, porque para
# la expresión regular el guion bajo y las letras son parte de la palabra. Con `\b` quedan sin tapar
# la versión de cliente que manda un escáner (`MGLNDD_203.0.113.10_22`) y una dirección pegada a
# texto, como en `Host: 198.51.100.7rnrn`.
DIRECCION = re.compile(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)")
TAPADA = "x.x.x.x"

# El host de una URL con esquema: desde `esquema://` hasta la barra, el signo de pregunta o el
# final. Se conserva el esquema y la ruta, así el comando sigue diciendo que descarga algo.
HOST_DE_URL = re.compile(r"\b([a-z][a-z0-9+.-]*://)[^/\s?#]+")
# Un dominio usado como host, es decir seguido de una barra. El dominio exige un último tramo de dos
# letras o más, así `x.x.x.x` (ya tapado) y nombres como `a.sh` sin barra no entran.
DOMINIO_CON_RUTA = re.compile(r"\b(?:[a-z0-9-]+\.)+[a-z]{2,}(?=/)", re.IGNORECASE)
HOST_TAPADO = "tapado"

# Un comando puede esconder la dirección, como en `echo <base64> | base64 -d | sh` o en un `printf`
# con escapes hexadecimales, y ahí el patrón de arriba no la ve. Cada bloque se decodifica, se le
# tapa la dirección y se vuelve a codificar, así el comando sigue diciendo lo mismo sin ella.
BLOQUE_BASE64 = re.compile(r"[A-Za-z0-9+/]{16,}={0,2}")
BLOQUE_HEXA = re.compile(r"(?:\\x[0-9a-fA-F]{2})+")
# El alfabeto del base64 también lo tienen los caminos largos y las huellas en hexadecimal, que
# decodificados dan bytes al azar. Por eso un bloque cuenta solo si decodificado es texto. Los
# escapes hexadecimales son siempre una codificación a propósito, y se miran aunque traigan un
# binario: la dirección del servidor de control suele ir adentro.
PROPORCION_DE_TEXTO = 0.9

# Una credencial con forma de dirección es un fragmento de una IP que el atacante probó como usuario
# o contraseña, y uno de esos fragmentos es parte de la dirección del propio servidor. Tres grupos
# alcanzan para reconocerla, aun cuando sea una dirección cortada que no llega a los cuatro octetos.
PARECE_DIRECCION = re.compile(r"\d{1,3}\.\d{1,3}\.\d{1,3}")


def parece_direccion(texto: object) -> bool:
    return bool(PARECE_DIRECCION.search(str(texto)))


# Una credencial se muestra solo si la probaron al menos estas direcciones distintas. Las de
# diccionario las prueban cientos; una credencial real filtrada de otro servicio apunta a una cuenta
# puntual, y la prueban una o muy pocas. El corte deja las primeras y descarta las segundas.
MINIMO_DE_ORIGENES = 5

# Lo que se muestra en lugar de una credencial que no llega al mínimo, cuando hay que mostrar algo.
CREDENCIAL_TAPADA = "(poco probada)"


def sin_credenciales_con_direccion(
    cubos: list[dict[str, Any]], tope: int | None = None
) -> list[dict[str, Any]]:
    """El ranking sin las entradas con forma de dirección, recortado al tope si se pide.

    Se piden más de las que se muestran y se descarta acá, así ninguna dirección sale en la
    respuesta aunque el panel muestre menos de las que vienen.
    """
    limpios = [c for c in cubos if not parece_direccion(c.get("key"))]
    return limpios[:tope] if tope is not None else limpios


def credenciales_frecuentes(
    cubos: list[dict[str, Any]], tope: int | None = None
) -> list[dict[str, Any]]:
    """El ranking con las credenciales que probaron al menos `MINIMO_DE_ORIGENES` direcciones.

    Cada cubo trae en `origenes` cuántas direcciones distintas probaron esa credencial, y sale sin
    ese campo, con la misma forma de siempre. Las que tienen forma de dirección se descartan igual.
    """
    frecuentes = [
        {"key": c["key"], "count": c["count"]}
        for c in sin_credenciales_con_direccion(cubos)
        if c.get("origenes", 0) >= MINIMO_DE_ORIGENES
    ]
    return frecuentes[:tope] if tope is not None else frecuentes


def credenciales_de_sesiones(
    sesiones: list[dict[str, Any]], usuarios: set[str], contrasenas: set[str]
) -> list[dict[str, Any]]:
    """Las sesiones con la credencial de entrada tapada cuando no pasa la regla de arriba.

    `usuarios` y `contrasenas` son las que la pasan. Una sesión es un solo atacante, así que su
    credencial no dice nada de cuántos la probaron: eso se mide sobre todo el corpus.
    """
    salida = []
    for sesion in sesiones:
        credencial = sesion.get("credentials") or {}
        usuario, contrasena = credencial.get("user"), credencial.get("password")
        salida.append(
            sesion
            | {
                "credentials": {
                    "user": usuario if usuario in usuarios else CREDENCIAL_TAPADA,
                    "password": contrasena if contrasena in contrasenas else CREDENCIAL_TAPADA,
                }
            }
        )
    return salida


# Las contraseñas de un evento, tal como las guarda el índice. Para revisar una clasificación hacen
# falta; para mirar el panel en una demostración, no.
CAMPOS_DE_CONTRASENA = ("cowrie.password", "dionaea.password")
CONTRASENA_OCULTA = "(oculta)"


def sin_contrasenas(valor: Any) -> Any:
    """El mismo valor, con las contraseñas de los eventos ocultas, a cualquier profundidad."""
    if isinstance(valor, dict):
        return {
            clave: CONTRASENA_OCULTA
            if clave in CAMPOS_DE_CONTRASENA and v is not None
            else sin_contrasenas(v)
            for clave, v in valor.items()
        }
    if isinstance(valor, list):
        return [sin_contrasenas(v) for v in valor]
    return valor


def _es_texto(datos: bytes) -> bool:
    legibles = sum(32 <= b < 127 or b in (9, 10, 13) for b in datos)
    return bool(datos) and legibles >= PROPORCION_DE_TEXTO * len(datos)


def _base64_sin_direcciones(bloque: re.Match[str]) -> str:
    original = bloque.group(0)
    try:
        datos = base64.b64decode(original + "=" * (-len(original) % 4))
    except (binascii.Error, ValueError):
        return original
    texto = datos.decode("latin-1")
    if not _es_texto(datos) or not DIRECCION.search(texto):
        return original
    return base64.b64encode(DIRECCION.sub(TAPADA, texto).encode("latin-1")).decode()


def _hexa_sin_direcciones(bloque: re.Match[str]) -> str:
    original = bloque.group(0)
    texto = bytes.fromhex(original.replace("\\x", "")).decode("latin-1")
    if not DIRECCION.search(texto):
        return original
    return "".join(f"\\x{b:02x}" for b in DIRECCION.sub(TAPADA, texto).encode("latin-1"))


def _tapar_texto(texto: str) -> str:
    """Un texto con las direcciones, el host de las URL y los dominios con ruta tapados.

    Primero las IPv4, así una URL contra una dirección queda con el host ya tapado y el dominio no
    la vuelve a tocar. Los bloques codificados van al final: el base64 no tiene puntos ni `://`, así
    que las sustituciones de antes no lo alteran.
    """
    texto = DIRECCION.sub(TAPADA, texto)
    texto = HOST_DE_URL.sub(rf"\1{HOST_TAPADO}", texto)
    texto = DOMINIO_CON_RUTA.sub(HOST_TAPADO, texto)
    texto = BLOQUE_BASE64.sub(_base64_sin_direcciones, texto)
    return BLOQUE_HEXA.sub(_hexa_sin_direcciones, texto)


def sin_direcciones(valor: Any) -> Any:
    """El mismo valor, con cada dirección y destino tapado, a cualquier profundidad."""
    if isinstance(valor, str):
        return _tapar_texto(valor)
    if isinstance(valor, dict):
        return {clave: sin_direcciones(v) for clave, v in valor.items()}
    if isinstance(valor, list):
        return [sin_direcciones(v) for v in valor]
    return valor
