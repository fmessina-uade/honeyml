"""The boundary the engine sees, and the policy that picks a model.

El nodo de inferencia del grafo depende de `ServicioDeInferencia` y de nada más. No sabe
qué proveedor hay del otro lado, no importa su cliente, y **no elige modelo**: pide una respuesta y
recibe una. Todo lo específico de Groq vive de este lado de la frontera.

Eso no es prolijidad arquitectónica: el proyecto ya tuvo que sustituir un proveedor a mitad de
desarrollo. Cuando vuelva a pasar, lo que se reescribe es este archivo.

LA SELECCIÓN DE MODELO: BARATO PRIMERO, CAPAZ AL REINTENTAR

Hay dos modelos de producción con adherencia garantizada al esquema, y uno sale la mitad que el
otro. La política es:

    intento 0        openai/gpt-oss-20b     mitad de precio, el doble de velocidad
    intento 1 y +    openai/gpt-oss-120b    el que razona mejor

**Por qué escalar al reintentar y no al revés.** Un reintento existe porque la respuesta anterior no
se pudo usar. La temperatura es 0, así que repetir con el mismo modelo cambia poco: lo único
distinto es el reproche agregado al pedido. Puede alcanzar —a veces el modelo solo necesita que le
señalen el campo— pero si el barato ya falló una vez, la diferencia de capacidad explica el fallo
mejor que la redacción del pedido. Y el presupuesto son tres intentos: gastar dos en el modelo que
ya falló es la peor de las apuestas disponibles.

**Por qué no se elige por características del evento.** Se evaluó decidir según cuánto margen deja
el piso —cuando piso y techo coinciden no hay juicio que delegar, solo redacción—. Pero eso pasa
únicamente en el 1,1 % de los eventos (los de transferencia de archivo, que ya arrancan en
`critico`), así que el ahorro sería ruido y la regla, una complicación sin contrapartida medible.

**El escape está declarado.** `HONEYML_MODELO` fija un modelo y desactiva la política entera. Sirve
para medir un modelo contra el otro sobre el mismo corpus, que es exactamente lo que la campaña de
la campaña de validación va a querer hacer.

CONTABILIDAD POR MODELO
El consumo se lleva separado por modelo. Sin eso, la política no se puede evaluar: "cuántos eventos
resolvió el económico" es la única forma de saber si vale la pena, y además es una de las métricas
operativas que hay que reportar.
"""

from __future__ import annotations

from typing import Any, Protocol

from .config import (
    MODELO_ALTERNATIVO,
    MODELO_POR_DEFECTO,
    ConfigInferencia,
    CredencialAusenteError,
)
from .inferencia import (
    ClienteDeInferencia,
    Consumo,
    PedidoRechazadoError,
    ProveedorInalcanzableError,
    Respuesta,
)


class ServicioDeInferencia(Protocol):
    """What the engine is allowed to ask for. Deliberately small.

    Un solo método, y ningún parámetro que nombre un proveedor o un modelo. `intento` está para que
    la política pueda escalar, no para que el llamador elija: el nodo sabe en qué vuelta del ciclo
    correctivo está —es información suya— y no sabe qué hacer con eso, que es información de acá.
    """

    def completar(
        self,
        sistema: str,
        usuario: str,
        esquema: dict[str, Any],
        *,
        intento: int = 0,
        nombre_esquema: str = "decision",
    ) -> Respuesta: ...


def elegir_modelo(intento: int, fijado: str | None = None) -> str:
    """Which model this attempt should use. `fijado` overrides the policy entirely."""
    if fijado:
        return fijado
    return MODELO_ALTERNATIVO if intento == 0 else MODELO_POR_DEFECTO


class AdaptadorDeInferencia:
    """The default implementation of the boundary, backed by the Groq-compatible client.

    Se llama por lo que hace y no por el proveedor que usa hoy: si mañana hay que cambiarlo, el
    nombre sigue siendo cierto y el motor no se entera.
    """

    def __init__(
        self,
        cliente: ClienteDeInferencia | None = None,
        config: ConfigInferencia | None = None,
    ) -> None:
        self.config = config or (cliente.config if cliente else ConfigInferencia.desde_entorno())
        self.cliente = cliente or ClienteDeInferencia(self.config)
        # Un `Consumo` por modelo. El del cliente sigue llevando el total, así que los dos números
        # existen y no se pisan: el agregado para la factura, el desglose para evaluar la política.
        self.por_modelo: dict[str, Consumo] = {}

    @property
    def modelo_fijado(self) -> str | None:
        """The model pinned by configuration, or None when the policy is free to choose.

        Se considera fijado solo cuando difiere del valor por defecto. Si no, arrancar sin
        `HONEYML_MODELO` clavaría el modelo de más capacidad en todos los intentos y la política
        no se aplicaría nunca —silenciosamente, que es la peor forma de no aplicarse.
        """
        return self.config.modelo if self.config.modelo != MODELO_POR_DEFECTO else None

    def completar(
        self,
        sistema: str,
        usuario: str,
        esquema: dict[str, Any],
        *,
        intento: int = 0,
        nombre_esquema: str = "decision",
    ) -> Respuesta:
        modelo = elegir_modelo(intento, self.modelo_fijado)
        respuesta = self.cliente.completar(
            sistema=sistema,
            usuario=usuario,
            esquema=esquema,
            nombre_esquema=nombre_esquema,
            modelo=modelo,
        )
        self.por_modelo.setdefault(modelo, Consumo()).sumar(
            respuesta.tokens_entrada, respuesta.tokens_salida, respuesta.segundos
        )
        return respuesta

    def resumen(self) -> str:
        """Consumption broken down by model, which is how the policy gets evaluated."""
        if not self.por_modelo:
            return "sin llamadas"
        lineas = [
            f"  {modelo:<24}{c.resumen(modelo)}" for modelo, c in sorted(self.por_modelo.items())
        ]

        total = sum(c.llamadas for c in self.por_modelo.values())
        barato = self.por_modelo.get(MODELO_ALTERNATIVO)
        if barato and total:
            proporcion = barato.llamadas / total * 100
            lineas.append(f"  resuelto por el modelo económico: {proporcion:.1f} % de las llamadas")
        return "\n".join(lineas)


def comprobar() -> int:
    """One live round trip through the boundary, policy included. `make inferencia-ok`.

    Va por el adaptador y no por el cliente a propósito: así ejercita exactamente el camino que va a
    usar el motor —incluida la selección de modelo— en vez de un atajo que funciona pero no prueba
    lo mismo. Es la única parte del frente de inferencia que no se puede verificar sin la
    credencial; todo lo demás está cubierto por pruebas que no tocan la red.
    """
    try:
        config = ConfigInferencia.desde_entorno()
    except CredencialAusenteError as exc:
        print(f"✗ {exc}")
        return 1

    adaptador = AdaptadorDeInferencia(config=config)
    fijado = adaptador.modelo_fijado
    print(f"Proveedor : {config.base_url}")
    print(f"Modelo    : {fijado or f'por política — intento 0 usa {MODELO_ALTERNATIVO}'}")
    print(f"Clave     : {config.enmascarada()}")

    esquema = {
        "type": "object",
        "properties": {
            "listo": {"type": "boolean"},
            "resumen": {"type": "string"},
        },
    }
    try:
        r = adaptador.completar(
            sistema="Respondés únicamente con el JSON que se te pide.",
            usuario="Poné listo en verdadero y una frase corta en resumen.",
            esquema=esquema,
            intento=0,
            nombre_esquema="comprobacion",
        )
    except (ProveedorInalcanzableError, PedidoRechazadoError) as exc:
        print(f"\n✗ {type(exc).__name__}: {exc}")
        return 1

    print(f"\n✓ Respondió en {r.segundos:.2f}s con {r.modelo}")
    print(f"  {r.contenido.strip()[:200]}")
    print(adaptador.resumen())

    # El costo por evento multiplicado por los mensajes del bus da la factura de una corrida
    # completa. Es una de las métricas operativas a reportar, y conviene tenerla desde el día uno.
    costo = adaptador.por_modelo[r.modelo].costo_estimado(r.modelo)
    if costo is not None:
        print(f"\n  A este precio, los 52.165 mensajes del bus salen ≈ USD {costo * 52165:.2f}")
        print("  (la comprobación usa un contexto mínimo; el real es bastante mayor)")
    return 0
