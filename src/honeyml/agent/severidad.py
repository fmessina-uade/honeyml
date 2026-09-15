"""La escala de severidad: qué niveles hay, qué establece cada uno y cuánto puede mover el motor.

La escala es el embudo de intrusión y no una opinión. El panel ya mide hasta dónde llegó cada
dirección: tocó la puerta, probó credenciales, entró, ejecutó comandos, se llevó algo. Esa escalera
es observable en la telemetría y cada escalón es un umbral real, así que reutilizarla da la
propiedad que más importa acá: cualquiera puede verificar el nivel contra la evidencia sin confiar
en el motor. De ahí salen el rechazo de la validación (poner una transferencia de archivo en
"informativo" contradice el registro, no es criterio) y la posibilidad de medir el motor contra un
valor esperado que se calcula desde los propios eventos.

Si el piso es mecánico, ¿para qué está el modelo? Por cuatro cosas que un `if` no produce: el rastro
auditable en palabras, la escalada acotada (para la regla, `uname -a` y `chmod +x` son los dos
"ejecutó un comando"), la atribución MITRE, y el contexto que la regla ignora, que es lo que
devuelven las consultas de `tools.py`. El margen es de un nivel, ver `MARGEN_DE_ESCALADA`.

La unidad es el evento y no la sesión ni la dirección, porque el bus entrega eventos y una sesión
abierta no termina nunca. La consecuencia a tener presente es que una sesión de cincuenta comandos
produce cincuenta decisiones, casi todas del mismo nivel; eso lo absorbe el panel agrupando, que es
información que ya tiene.

Sobre el bus, el piso mecánico deja la mayoría de los eventos en `alto` y muy pocos en `critico`.
Que `alto` domine no es un defecto: el filtro del bus ya selecciona eventos donde el atacante hizo
algo. Y la proporción de `critico` es parecida a la fracción de direcciones que el agrupamiento no
supervisado ubica en intrusión efectiva: que dos métodos independientes den lo mismo es la mejor
señal de que la escala está bien puesta.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum
from typing import NamedTuple

from .consumer import EventoDelBus


class Severidad(StrEnum):
    """Los cinco niveles, en orden. `StrEnum` para que se serialice con su propio nombre."""

    INFORMATIVO = "informativo"
    BAJO = "bajo"
    MEDIO = "medio"
    ALTO = "alto"
    CRITICO = "critico"


# El orden es la escala, y se declara explícito en vez de deducirlo del orden de definición del
# enum: comparar por posición es una operación del dominio, y atarla a cómo quedaron escritas las
# líneas de arriba la vuelve frágil ante un reordenamiento inocente.
ORDEN: list[Severidad] = [
    Severidad.INFORMATIVO,
    Severidad.BAJO,
    Severidad.MEDIO,
    Severidad.ALTO,
    Severidad.CRITICO,
]

# Cuántos niveles por encima del piso puede subir el motor con una justificación. Uno: con margen
# amplio, un modelo que ante la duda exagera lleva todo a crítico y la escala deja de ordenar nada,
# que es como mueren estas escalas; con margen cero no haría falta modelo.
MARGEN_DE_ESCALADA = 1


class Criterio(NamedTuple):
    """Qué establece un nivel, en los dos registros que importan: la evidencia y cómo se explica."""

    nivel: Severidad
    #: Qué tiene que haber pasado, en términos de la telemetría.
    evidencia: str
    #: Cómo se le explica a una persona en el panel.
    lectura: str
    #: Escalón del embudo de intrusión al que corresponde.
    escalon: str


CRITERIOS: dict[Severidad, Criterio] = {
    Severidad.INFORMATIVO: Criterio(
        Severidad.INFORMATIVO,
        evidencia="contacto con el señuelo sin presentar credenciales",
        lectura="Alguien miró. Es el fondo permanente de internet, no un ataque dirigido.",
        escalon="tocó la puerta",
    ),
    Severidad.BAJO: Criterio(
        Severidad.BAJO,
        evidencia="intento de credenciales sin evidencia de acceso",
        lectura="Probó entrar y no hay constancia de que lo lograra.",
        escalon="probó credenciales",
    ),
    Severidad.MEDIO: Criterio(
        Severidad.MEDIO,
        evidencia="autenticación con resultado exitoso",
        lectura="Entró. Todavía no hizo nada adentro, pero ya tiene una sesión.",
        escalon="entró",
    ),
    Severidad.ALTO: Criterio(
        Severidad.ALTO,
        evidencia="ejecución de comandos dentro del señuelo",
        lectura="Está operando adentro. Dejó de ser un intento y pasó a ser una intrusión.",
        escalon="ejecutó comandos",
    ),
    Severidad.CRITICO: Criterio(
        Severidad.CRITICO,
        evidencia="transferencia de archivo, en cualquier dirección",
        lectura=(
            "Trajo una herramienta o se llevó algo. Es el escalón donde una intrusión deja de ser "
            "reversible sola."
        ),
        escalon="se llevó algo",
    ),
}


def piso_de(categoria: str, outcome: str = "") -> Severidad:
    """El piso para un par (categoría, resultado), sin necesidad de un objeto evento.

    Es el primitivo, y `piso` es la comodidad sobre él. Va separado porque hay que ordenar por
    severidad lo que devuelve una agregación de Elasticsearch, que trae pares sin documentos.
    """
    if categoria == "file":
        return Severidad.CRITICO
    if categoria == "process":
        return Severidad.ALTO
    if categoria == "authentication":
        return Severidad.MEDIO if outcome == "success" else Severidad.BAJO
    # `network` y cualquier categoría que aparezca más adelante. Ver `LLEGAN_POR_EL_BUS`.
    return Severidad.INFORMATIVO


def piso(evento: EventoDelBus) -> Severidad:
    """El nivel que la telemetría establece sola, sin interpretación de por medio.

    Conservador a propósito: contesta qué prueba el registro y no qué tan grave parece. Los intentos
    de credenciales de Dionaea contra MySQL y MSSQL quedan en `BAJO` porque ese sensor no puede
    observar el resultado, y mejor un desconocido que un éxito sin respaldo.
    """
    return piso_de(evento.category, evento.outcome)


def maxima(niveles: Iterable[Severidad]) -> Severidad | None:
    """El mayor de varios niveles, o None si no hay ninguno.

    Ordena por `ORDEN` y no por el nombre del miembro. `max()` sobre un `StrEnum` compara cadenas, y
    alfabéticamente 'medio' le gana a 'critico'.
    """
    encontrados = list(niveles)
    if not encontrados:
        return None
    return max(encontrados, key=ORDEN.index)


def techo(evento: EventoDelBus) -> Severidad:
    i = ORDEN.index(piso(evento))
    return ORDEN[min(i + MARGEN_DE_ESCALADA, len(ORDEN) - 1)]


def dentro_de_limites(nivel: Severidad, evento: EventoDelBus) -> bool:
    """Si un nivel asignado es defendible para este evento.

    Por debajo del piso nunca es defendible, porque eso contradice el registro en vez de juzgarlo.
    Por encima del techo es la inflación que el margen existe para evitar.
    """
    return ORDEN.index(piso(evento)) <= ORDEN.index(nivel) <= ORDEN.index(techo(evento))


def reproche(nivel: Severidad, evento: EventoDelBus) -> str | None:
    """Por qué un nivel quedó fuera de límites, redactado para devolvérselo al proveedor.

    Devuelve None si el nivel está bien. El texto nombra la evidencia y no la regla, porque "el
    evento documenta una transferencia de archivo" es corregible y "viola la restricción 3" no.
    """
    if dentro_de_limites(nivel, evento):
        return None

    p, t = piso(evento), techo(evento)
    if ORDEN.index(nivel) < ORDEN.index(p):
        return (
            f"La severidad '{nivel}' está por debajo de lo que prueba el registro: el evento "
            f"documenta {CRITERIOS[p].evidencia}, así que el mínimo defendible es '{p}'."
        )
    return (
        f"La severidad '{nivel}' supera en más de un nivel a lo que prueba el registro. El evento "
        f"documenta {CRITERIOS[p].evidencia}, con piso '{p}'. Con justificación se admite hasta "
        f"'{t}'."
    )


# Qué niveles puede producir hoy el motor por el camino real. Sale de las cuatro condiciones del
# filtro de `80-bus.conf`: autenticaciones exitosas (piso `medio`), ejecución de comandos (`alto`),
# transferencia de archivos (`critico`), y los intentos de credenciales contra Dionaea prosperen o
# no, que son los que traen `bajo` porque ese sensor casi nunca puede declarar el resultado.
#
# Esa cuarta condición es la que hay que tener presente al leer este conjunto: sin ella, `bajo` no
# tendría por qué estar acá. `INFORMATIVO` sí está definido y no llega, y no se lo saca de la escala
# porque la campaña de validación adversaria va a generar reconocimiento, y su etiqueta esperada
# tiene que existir.
LLEGAN_POR_EL_BUS: set[Severidad] = {
    Severidad.BAJO,
    Severidad.MEDIO,
    Severidad.ALTO,
    Severidad.CRITICO,
}


def para_el_proveedor() -> str:
    """La escala tal como se le entrega al servicio de inferencia, con los pisos incluidos.

    Se arma desde `CRITERIOS` en vez de escribirla a mano una segunda vez: dos copias se terminan
    desincronizando, y la que lee el modelo es la que decide qué vuelve.
    """
    lineas = [
        "Escala de severidad. Cada nivel se establece por evidencia observable en la telemetría:",
        "",
    ]
    for nivel in ORDEN:
        c = CRITERIOS[nivel]
        lineas.append(f"  {nivel.value:<12} {c.evidencia}  ({c.escalon})")
    lineas += [
        "",
        "El nivel que la evidencia prueba es el mínimo, nunca una sugerencia: asignar por debajo",
        "contradice el registro. Con justificación explícita se admite subir hasta",
        f"{MARGEN_DE_ESCALADA} nivel (por ejemplo, un comando de persistencia o de evasión",
        "frente a uno de reconocimiento) y nunca más que eso.",
    ]
    return "\n".join(lineas)


if __name__ == "__main__":
    print(para_el_proveedor())
