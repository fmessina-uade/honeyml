r"""La firma de conducta de un evento: qué hizo el atacante, sin quién fue ni cuándo.

Dos eventos con la misma firma describen la misma conducta observada, y en el bus las conductas se
repiten muchísimo: las firmas distintas son una fracción chica de los mensajes. Pedirle al
proveedor una decisión por evento es pagar muchas veces la misma respuesta.

Entran el sensor, la categoría, la acción, el resultado, el protocolo, el usuario y el comando.
Quedan afuera la dirección de origen, la sesión, la marca temporal y el identificador del
documento, que dicen quién y cuándo pero no qué. El protocolo entra aunque sume firmas, porque sin
él se juntan conductas que no son la misma: fuerza bruta por SSH con la misma por telnet, o
intentos contra MSSQL con los de MySQL.

Dejar la dirección afuera es la decisión discutible, porque el historial cambia entre repeticiones
de una firma. Pero la escala mide qué logró el atacante en este evento y no quién es, y hay una
garantía que no depende de medir nada: el piso sale de `piso_de(categoria, resultado)` y el techo se
deriva del piso, así que una severidad defendible para el evento triado lo es por construcción para
cualquier otro de la misma firma. La táctica sí puede oscilar entre repeticiones, y queda declarada
como límite conocido.

El comando entra con los bytes escritos como escapes reemplazados por una marca. Un dropper que no
logra descargar su binario lo escribe de a trozos, con `echo -ne '\x7f\x45\x4c...' >> archivo`, y
cada trozo es un comando distinto: sin la marca, una sola descarga son cientos de firmas y cientos
de llamadas para decidir lo mismo. Los bytes no cambian la conducta, que es escribir un binario en
el señuelo. El archivo y la redirección se conservan, y un comando sin escapes firma igual que si
la marca no existiera, así que el repertorio ya guardado sigue valiendo.
"""

from __future__ import annotations

import hashlib
import re

from .consumer import EventoDelBus

# Los campos que componen la firma, en orden. Está acá y no repartido en el código porque el
# criterio se discute como un todo: agregar uno parte todos los grupos, sacar uno los junta.
CAMPOS = ("honeypot", "category", "action", "outcome", "protocol", "user", "command")

# Con qué se unen los campos. Un carácter que no aparece en ninguno de ellos, para que dos eventos
# distintos no puedan producir la misma cadena por cómo quedaron pegados: con un separador que sí
# pudiera aparecer, un usuario terminado en él y un comando vacío colisionarían con el caso
# inverso.
SEPARADOR = "\x1f"

# Una tira seguida de escapes se vuelve una sola marca, sea del largo que sea: el último trozo de
# un binario casi nunca mide lo mismo que los anteriores y tiene que caer en la misma firma.
ESCAPES_HEX = re.compile(r"(?:\\x[0-9a-fA-F]{2})+")
MARCA_DE_BYTES = "<bytes>"

# Cuántos caracteres del resumen se conservan. Dieciséis hexadecimales son 64 bits: con miles de
# firmas, y aun con varios órdenes de magnitud más, la probabilidad de colisión es despreciable, y
# la clave entra cómoda en un registro y en una consulta.
LARGO = 16


def comando_firmado(comando: str) -> str:
    """El comando como entra en la firma: los bytes escritos a mano quedan como una marca."""
    return ESCAPES_HEX.sub(MARCA_DE_BYTES, comando)


def de_evento(evento: EventoDelBus) -> str:
    """El resumen de la conducta de este evento.

    Se devuelve un hash y no la concatenación por una razón práctica: el comando puede tener miles
    de caracteres y termina siendo clave de Redis y valor de un campo indexado.
    """
    valores = []
    for campo in CAMPOS:
        valor = str(getattr(evento, campo, "") or "")
        valores.append(comando_firmado(valor) if campo == "command" else valor)
    crudo = SEPARADOR.join(valores)
    return hashlib.sha256(crudo.encode("utf-8", "replace")).hexdigest()[:LARGO]
