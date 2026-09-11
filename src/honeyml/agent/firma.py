"""La firma de conducta de un evento: qué hizo el atacante, sin quién fue ni cuándo.

Dos eventos con la misma firma describen la misma conducta observada. Sobre los 71.654 mensajes
acumulados al 10/09 hay 2.088 firmas distintas, el 2,9 %: un solo comando, `uname -s -v -n -r -m`,
aparece 6.588 veces. Pedirle al proveedor una decisión por evento es pagar 6.588 veces la misma
respuesta.

Qué entra y qué no. Entran el sensor, la categoría, la acción, el resultado, el protocolo, el
usuario y el comando, o sea lo que el atacante hizo y contra qué. Quedan afuera la dirección de
origen, la sesión, la marca temporal y el identificador del documento, que dicen quién y cuándo
pero no qué.

El protocolo entró después de medirlo, y casi no entra. Sin él son 2.088 firmas y con él 2.111:
veintitrés llamadas más, un 1,1 %. Pero esas veintitrés estaban juntando conductas que no son la
misma: fuerza bruta por SSH con la misma por telnet, e intentos contra MSSQL con los de MySQL, que
son servicios distintos. Entre las dos alcanzaban al 28 % de los eventos. Un centavo por no tener
que defender esa mezcla es barato.

Dejar la dirección afuera es la decisión discutible, y se midió antes de tomarla. El contexto
enriquecido difiere en 8 de 8 repeticiones de cada firma, sobre todo en el historial: una dirección
con 3.962 eventos previos y otra con 1 comparten firma y nada más. Pero al triar los extremos de
las tres firmas más frecuentes, la severidad salió idéntica en las tres. Tiene sentido, porque la
escala está anclada al embudo de intrusión: mide qué logró el atacante en este evento, no quién es.
La táctica sí osciló, y eso queda anotado como límite conocido en lugar de disimulado.

Hay además una garantía que no depende de esa medición. El piso de severidad sale de
`piso_de(categoria, resultado)` y el techo se deriva del piso, así que los dos dependen solo de
campos que la firma incluye. Una severidad defendible para el evento que se trió es defendible por
construcción para cualquier otro de la misma firma; no hace falta confiar en que el modelo sea
consistente.
"""

from __future__ import annotations

import hashlib

from .consumer import EventoDelBus

# Los campos que componen la firma, en orden. Está acá y no repartido en el código porque el
# criterio se discute como un todo: agregar uno parte todos los grupos, sacar uno los junta.
CAMPOS = ("honeypot", "category", "action", "outcome", "protocol", "user", "command")

# Con qué se unen los campos. Un carácter que no aparece en ninguno de ellos, para que dos eventos
# distintos no puedan producir la misma cadena por cómo quedaron pegados: con un separador que sí
# pudiera aparecer, un usuario terminado en él y un comando vacío colisionarían con el caso
# inverso.
SEPARADOR = "\x1f"

# Cuántos caracteres del resumen se conservan. Dieciséis hexadecimales son 64 bits: para 2.088
# firmas, y aun para varios órdenes de magnitud más, la probabilidad de colisión es despreciable, y
# la clave entra cómoda en un registro y en una consulta.
LARGO = 16


def de_evento(evento: EventoDelBus) -> str:
    """El resumen de la conducta de este evento.

    Se devuelve un hash y no la concatenación por una razón práctica: el comando puede tener miles
    de caracteres (el más largo del corpus pasa los 3.000) y termina siendo clave de Redis y valor
    de un campo indexado.
    """
    crudo = SEPARADOR.join(str(getattr(evento, campo, "") or "") for campo in CAMPOS)
    return hashlib.sha256(crudo.encode("utf-8", "replace")).hexdigest()[:LARGO]
