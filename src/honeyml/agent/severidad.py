"""The severity scale: which levels exist, what establishes each one, and how far the engine may go.

Fila 78. Everything else in the engine was written against a `severidad` that was declared to exist
and deliberately left without a vocabulary; this is the vocabulary.

THE SCALE IS THE INTRUSION FUNNEL, NOT AN OPINION
The panel already measures how far each address got: knocked, tried credentials, got in, ran
commands, took something. That ladder is observable in the telemetry, it is already computed, and
every step is a real threshold rather than a feeling about how bad something looks. Reusing it as
the severity scale costs nothing and buys the property that matters most here — **the level can be
checked against the evidence by someone who does not trust the engine.**

WHY THAT PROPERTY IS LOAD-BEARING, TWICE

*Validation (fila 84).* An answer that puts a file transfer at "informativo" is not a matter of
judgement, it contradicts the record. The floor below turns that into a rejection instead of a
decision nobody caught.

*The adversarial campaign (Fase 4, fila 102).* "Comparación entre clasificación obtenida y esperada"
needs an *expected*. With severity defined by observable evidence, the expected label is computed
from the events themselves — mechanically, with no second opinion to argue about. A scale that only
a model could apply would leave that row with nothing to compare against.

SO WHAT IS THE MODEL FOR?
A fair question, and the answer has to be stated rather than dodged: if the floor is mechanical, an
`if` would do. The engine earns its place on four things the rule cannot produce.

1. **The audit trail.** A justification in words, and the specific facts it rests on. The rule
   outputs a label; a triage decision that cannot be read is not triage.
2. **Escalation within declared bounds.** A `uname -a` and a `chmod +x` are both "ran a command" to
   the rule. Whether this one deserves the level above is exactly the judgement being delegated —
   bounded, so it stays a judgement and not a free hand.
3. **MITRE attribution.** Which tactic the behaviour corresponds to.
4. **The context the rule ignores.** Repeat offender, known command family, hosting-provider origin.
   These are what the tools of fila 73 return, and this is what they are for.

The bound is one level. See `MARGEN_DE_ESCALADA`.

EL ALCANCE: QUÉ SE CLASIFICA, Y QUÉ NO

**La unidad es el evento, no la sesión ni la dirección.** El bus entrega eventos, el consumidor
deduplica por `doc_id` y el CU-03 describe presentar un evento con su estado de procesamiento. Poner
la decisión en otra unidad obligaría al motor a esperar a que una sesión termine —y una sesión
abierta no termina— o a reclasificar hacia atrás cada vez que llega algo nuevo.

Tiene una consecuencia que conviene decir antes de que la descubra otro: **una sesión que corre
cincuenta comandos produce cincuenta decisiones**, casi todas del mismo nivel. Quien absorbe eso es
el panel, agrupando por sesión y por dirección, que es información que ya tiene. Agregar en el motor
sería mover el problema al lado donde cuesta una llamada de inferencia por reagrupamiento.

**Medido sobre los 52.165 mensajes que había en el bus al 25/08**, el piso mecánico reparte así:

    bajo       4.245   8,1 %
    medio     13.871  26,6 %
    alto      33.501  64,2 %
    critico      548   1,1 %

El 1,1 % de crítico concuerda con lo que encontró el agrupamiento no supervisado por otro camino
—1,5 % de las direcciones llegan a intrusión efectiva—, y esa coincidencia entre dos métodos
independientes es la mejor señal de que la escala está bien puesta.

Que el 64 % caiga en `alto` no es un defecto de la escala sino su consecuencia honesta: el filtro
del bus ya selecciona eventos donde el atacante *hizo* algo. Sobre ese grupo el margen deja al motor
una sola decisión —si esto además es crítico— que es exactamente la pregunta que vale la pena
delegar.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum
from typing import NamedTuple

from .consumer import EventoDelBus


class Severidad(StrEnum):
    """The five levels, ordered. `StrEnum` so it serialises as its own name and needs no mapping."""

    INFORMATIVO = "informativo"
    BAJO = "bajo"
    MEDIO = "medio"
    ALTO = "alto"
    CRITICO = "critico"


# El orden es la escala. Se declara explícito y no se deduce del orden de definición del enum:
# comparar severidades por su posición acá es una operación del dominio, y dejarla atada a cómo
# quedaron escritas las líneas de arriba la volvería frágil ante un reordenamiento inocente.
ORDEN: list[Severidad] = [
    Severidad.INFORMATIVO,
    Severidad.BAJO,
    Severidad.MEDIO,
    Severidad.ALTO,
    Severidad.CRITICO,
]

# Cuántos niveles por encima del piso puede subir el motor con una justificación.
#
# Uno, y no dos ni ilimitado. Con margen amplio, un modelo que ante la duda exagera lleva todo a
# crítico y la escala deja de ordenar nada —que es la forma habitual en que estas escalas mueren—.
# Con margen cero no haría falta modelo. Uno deja que la diferencia entre `uname -a` y `chmod +x`
# se note, y mantiene acotado cuánto puede desviarse de lo que el registro prueba.
MARGEN_DE_ESCALADA = 1


class Criterio(NamedTuple):
    """What establishes a level, in the two registers that matter: evidence and plain words."""

    nivel: Severidad
    #: Qué tiene que haber pasado, en términos de la telemetría.
    evidencia: str
    #: Cómo se le explica a una persona, en el panel y en el informe.
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
    """The floor for a (category, outcome) pair, with no event object in hand.

    Es el primitivo real, y `piso` es la comodidad sobre él. Existe separado porque la fila 82
    necesita ordenar por severidad lo que devuelve una agregación de Elasticsearch —pares de
    categoría y resultado, sin documentos— y fabricar eventos falsos para poder preguntar habría
    metido una estructura de mentira en el único lugar del motor que dice qué prueba el registro.
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
    """The level the telemetry establishes on its own, with no interpretation involved.

    Deliberately conservative: it answers "what does the record prove", not "how bad does this
    look". Dionaea's credential attempts against MySQL and MSSQL land on `BAJO` and not higher
    because that sensor cannot observe the outcome — the same reasoning as fila 67, where an
    unknown was preferred over an unsupported success.
    """
    return piso_de(evento.category, evento.outcome)


def maxima(niveles: Iterable[Severidad]) -> Severidad | None:
    """The highest of several levels, or None when there are none.

    Ordena por `ORDEN` y no por el nombre del miembro: `max()` sobre un `StrEnum` compara cadenas,
    y alfabéticamente 'medio' le gana a 'critico'.
    """
    encontrados = list(niveles)
    if not encontrados:
        return None
    return max(encontrados, key=ORDEN.index)


def techo(evento: EventoDelBus) -> Severidad:
    """The highest level the engine may assign to this event, floor plus the declared margin."""
    i = ORDEN.index(piso(evento))
    return ORDEN[min(i + MARGEN_DE_ESCALADA, len(ORDEN) - 1)]


def dentro_de_limites(nivel: Severidad, evento: EventoDelBus) -> bool:
    """Whether an assigned level is defensible for this event.

    Below the floor is never defensible — that is contradicting the record, not judging it. Above
    the ceiling is the inflation the margin exists to prevent.
    """
    return ORDEN.index(piso(evento)) <= ORDEN.index(nivel) <= ORDEN.index(techo(evento))


def reproche(nivel: Severidad, evento: EventoDelBus) -> str | None:
    """Why a level is out of bounds, phrased to be handed back to the provider.

    Returns None when the level is fine. The text names the evidence rather than the rule, because
    "the event records a file transfer" is correctable and "violates constraint 3" is not.
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
        f"documenta {CRITERIOS[p].evidencia} —piso '{p}'—, y con justificación se admite hasta "
        f"'{t}'."
    )


# Qué niveles puede producir hoy el motor por el camino real.
#
# El filtro de la fila 66 publica al bus autenticaciones exitosas, ejecución de comandos y
# transferencia de archivos: el reconocimiento —el 82,6 % del volumen— no dispara ningún ciclo. Así
# que `INFORMATIVO` está definido pero no llega por acá.
#
# No se lo saca de la escala por dos motivos: la campaña adversaria de la Fase 4 va a generar
# reconocimiento y su etiqueta esperada tiene que existir, y una escala que empieza en "ya probó
# credenciales" no se puede leer sin explicar antes qué quedó afuera.
LLEGAN_POR_EL_BUS: set[Severidad] = {
    Severidad.BAJO,
    Severidad.MEDIO,
    Severidad.ALTO,
    Severidad.CRITICO,
}


def para_el_proveedor() -> str:
    """The scale as it is handed to the inference service, floors included.

    Built from `CRITERIOS` and not written out a second time by hand: two copies of a scale drift,
    and the copy the model reads is the one that decides what comes back.
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
        f"{MARGEN_DE_ESCALADA} nivel —por ejemplo, un comando de persistencia o de evasión",
        "frente a uno de reconocimiento— y nunca más que eso.",
    ]
    return "\n".join(lineas)


if __name__ == "__main__":
    print(para_el_proveedor())
