"""Cliente del proveedor de inferencia, con límites de tasa y contabilidad de consumo.

Habla el dialecto compatible con OpenAI que expone Groq, por HTTP y con `urllib`, que es el mismo
camino por el que el proyecto ya consulta Elasticsearch. No trae ningún cliente HTTP: el proveedor
se alcanza por un adaptador, así que esa dependencia pertenece al adaptador y no al motor.

La única dependencia que sí agrega es `certifi`, y no es un cliente sino el paquete de certificados
raíz. Ver `_contexto_tls`: se usa como respaldo cuando el intérprete no tiene almacén propio, que es
el caso del Python de python.org en macOS mientras no se corra su `Install Certificates.command`.

"Manejo de consumo" son tres cosas distintas y las tres están acá.

Los límites de tasa. Un 429 no es un fallo, es el proveedor pidiendo que se espere. Se respeta el
`retry-after` que manda y se reintenta con retroceso acotado. Agotados los reintentos se levanta,
porque un límite de tasa es transitorio y el evento tiene que volver al bus en vez de persistirse
como no concluyente.

La contabilidad. Cada respuesta trae cuántos tokens costó, se acumulan y se traducen a dólares con
los precios de abajo. No es telemetría decorativa: "cuánto sale clasificar un evento" es una métrica
operativa que hay que reportar, y medirla desde el principio evita reconstruirla después.

Y la distinción que el grafo necesita. El grafo separa "el proveedor contestó mal" de "el proveedor
no contestó" y las trata distinto (una persiste, la otra reintenta). Esa distinción se sostiene en
la taxonomía de excepciones de este módulo: una red caída, un timeout o un 5xx dan
`ProveedorInalcanzableError` y el motor no confirma el evento; un 4xx que no es 429 da
`PedidoRechazadoError`, que es un defecto nuestro y tiene que verse.

Sobre la salida estructurada: se pide `json_schema` con `strict: true`, que en Groq usa
decodificación restringida, así que la respuesta cumple el esquema o no se emite. Tiene dos
requisitos que `esquema_estricto` se encarga de cumplir (todas las propiedades obligatorias y
objetos cerrados) y una limitación que este diseño ya respetaba: no admite herramientas ni
streaming. El motor arma el contexto por su cuenta en los nodos anteriores, así que no las necesita.
"""

from __future__ import annotations

import json
import os
import ssl
import time
import urllib.error
import urllib.request
from copy import deepcopy
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from .config import (
    MODELO_ALTERNATIVO,
    MODELO_POR_DEFECTO,
    VARIABLE_DE_CLAVE,
    ConfigInferencia,
)

# Precio por millón de tokens, en dólares, al 01/09/2026. Está acá y no en un cálculo suelto para
# que actualizarlo sea una línea. Un modelo que no figure se contabiliza en tokens y no en dinero:
# preferible a inventar un precio.
PRECIOS: dict[str, tuple[float, float]] = {
    MODELO_POR_DEFECTO: (0.15, 0.60),
    MODELO_ALTERNATIVO: (0.075, 0.30),
}

# Cuántas veces se reintenta ante un límite de tasa o un 5xx.
#
# Tres. El bus ya es la red de seguridad de verdad: un evento no confirmado vuelve solo. Insistir
# más acá retiene un consumidor ocupado esperando en vez de dejarlo procesar otro evento.
MAX_REINTENTOS = 3

# Espera base del retroceso, en segundos. Solo se usa cuando el proveedor no dice `retry-after`.
ESPERA_BASE = 2.0

# Techo de espera. Un `retry-after` de diez minutos es una respuesta válida del proveedor y una
# pésima idea para un consumidor: mejor devolver el evento al bus y volver a tomarlo después.
ESPERA_MAXIMA = 30.0


# Identificación del cliente. No es cortesía: sin ella `urllib` manda `Python-urllib/3.12`, y el
# borde de Cloudflare que el proveedor tiene adelante lo rechaza con un 403 y el código 1010
# ("navegador vedado") antes de que el proveedor llegue a ver la petición.
#
# El síntoma es cruel, porque la misma petición por `curl` funciona y entonces todo apunta a la
# credencial cuando la credencial está perfecta. Lo medimos con una clave inválida a propósito: con
# el agente por defecto da 403/1010, y con este da 401 "Invalid API Key", que es el error honesto de
# alguien que sí llegó al proveedor.
AGENTE = "honeyml/0.1 (+https://www.honeyml.com.ar)"

# Código de Cloudflare para "agente bloqueado". Se distingue de un rechazo de credencial porque
# mandan a revisar cosas distintas.
CODIGO_AGENTE_BLOQUEADO = "1010"

# El proveedor devuelve este código, con un 400, cuando su decodificación restringida no logró
# producir una respuesta que cumpla el esquema. Parece un pedido mal armado y no lo es: sobre una
# tanda de treinta eventos falló en cuatro, y los cuatro pasaron al reintentarlos tal cual, sin
# cambiarles una coma. Es una falla pasajera del proveedor.
#
# Importa clasificarlo bien. Como rechazo, el evento salía del grafo sin confirmar y había que
# esperar los diez minutos de la ventana de reclamo para que otro consumidor lo tomara; a razón de
# uno de cada ocho eventos, eso convierte una puesta al día en una espera. Como pasajero, se
# reintenta en el acto y el evento sigue.
CODIGO_ESQUEMA_NO_CUMPLIDO = "json_validate_failed"

AYUDA_CERTIFICADOS = (
    "TLS falló al verificar el certificado del proveedor. No es que el proveedor no responda: "
    "este intérprete de Python no tiene instalado su paquete de certificados raíz.\n"
    "  En macOS, con Python de python.org, se arregla una sola vez y para todo el sistema:\n"
    '      "/Applications/Python 3.12/Install Certificates.command"\n'
    "  Alternativa sin permisos de administrador: instalar certifi en el entorno\n"
    '  (`pip install -e ".[agent]"`), que este cliente usa como respaldo automático.'
)


@lru_cache(maxsize=1)
def _contexto_tls() -> ssl.SSLContext:
    """El contexto TLS con el que se verifica al proveedor. Nunca desactiva la verificación.

    Por esta conexión viaja la credencial, así que verificar no es negociable y desactivarlo no es
    una opción disponible, ni siquiera para depurar.

    Lo que sí hace es cubrir un caso concreto y bastante común: el intérprete de python.org en macOS
    apunta su almacén de certificados a `…/etc/openssl/cert.pem`, un archivo que su instalador crea
    recién cuando se corre `Install Certificates.command`. Sin ese paso, toda conexión HTTPS
    falla con un mensaje de OpenSSL que no nombra ninguna causa.

    Cuando el almacén configurado no existe se recurre al paquete de `certifi`, que es el mismo que
    instala ese script. No se sustituye un almacén que funcione, solo se provee uno cuando no hay.
    """
    rutas = ssl.get_default_verify_paths()
    hay_almacen = bool(
        (rutas.cafile and os.path.exists(rutas.cafile))
        or (rutas.capath and os.path.isdir(rutas.capath))
    )
    if hay_almacen:
        return ssl.create_default_context()

    try:
        import certifi
    except ImportError:  # pragma: no cover - solo si se instala sin el extra [agent]
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())


class ProveedorInalcanzableError(RuntimeError):
    """Fallo de transporte, o un límite de tasa que sobrevivió a los reintentos. Es transitorio."""


class PedidoRechazadoError(RuntimeError):
    """El proveedor entendió el pedido y lo rechazó. Eso es un defecto de este lado."""


@dataclass
class Consumo:
    """Acumulado de lo que gastó el motor. Alimenta las métricas operativas que hay que reportar."""

    llamadas: int = 0
    tokens_entrada: int = 0
    tokens_salida: int = 0
    segundos: float = 0.0
    esperas_por_limite: int = 0

    def sumar(self, entrada: int, salida: int, segundos: float) -> None:
        self.llamadas += 1
        self.tokens_entrada += entrada
        self.tokens_salida += salida
        self.segundos += segundos

    def costo_estimado(self, modelo: str) -> float | None:
        """Costo en dólares, o None si el modelo no tiene precio registrado."""
        precios = PRECIOS.get(modelo)
        if precios is None:
            return None
        p_entrada, p_salida = precios
        return (self.tokens_entrada * p_entrada + self.tokens_salida * p_salida) / 1_000_000

    def resumen(self, modelo: str) -> str:
        costo = self.costo_estimado(modelo)
        linea = (
            f"{self.llamadas} llamadas · {self.tokens_entrada:,} tokens de entrada · "
            f"{self.tokens_salida:,} de salida · {self.segundos:.1f}s"
        ).replace(",", ".")
        if costo is not None:
            linea += f" · ≈ USD {costo:.4f}"
        if self.esperas_por_limite:
            linea += f" · {self.esperas_por_limite} esperas por límite de tasa"
        return linea


@dataclass
class Respuesta:
    """Una respuesta y lo que costó. El contenido viene crudo: parsearlo es tarea de quien llama."""

    contenido: str
    tokens_entrada: int
    tokens_salida: int
    segundos: float
    modelo: str
    # Lo que devolvió el proveedor sin tocar, para poder auditar una decisión después.
    crudo: dict[str, Any] = field(default_factory=dict, repr=False)


def costo_de(respuesta: Respuesta) -> float | None:
    """Cuánto costó una respuesta, o None si su modelo no tiene precio registrado.

    `Consumo.costo_estimado` responde lo mismo sobre un acumulado. Esto existe para el nodo de
    persistencia, que guarda el costo de la llamada que produjo cada decisión.
    """
    precios = PRECIOS.get(respuesta.modelo)
    if precios is None:
        return None
    p_entrada, p_salida = precios
    return (respuesta.tokens_entrada * p_entrada + respuesta.tokens_salida * p_salida) / 1_000_000


def esquema_estricto(esquema: dict[str, Any]) -> dict[str, Any]:
    """Lleva un JSON Schema de Pydantic a la forma que exige el modo estricto.

    Tres reglas, todas impuestas por el proveedor y ninguna negociable:

    Todo tiene que ser obligatorio: un campo opcional se expresa como unión con `null` y no
    omitiéndolo, que es como ya declara `tactica_mitre` el modelo `Decision`. Los objetos tienen que
    estar cerrados, con `additionalProperties: false`. Y no puede haber `default`, porque la
    decodificación restringida no rellena: si el campo es obligatorio el modelo lo emite, y un valor
    por defecto en el esquema solo confunde sobre quién decide.

    Se trabaja sobre una copia. Mutar el esquema que devuelve Pydantic afectaría a todo el proceso,
    porque lo cachea por clase.
    """
    copia = deepcopy(esquema)

    def normalizar(nodo: Any) -> None:
        if isinstance(nodo, list):
            for x in nodo:
                normalizar(x)
            return
        if not isinstance(nodo, dict):
            return

        nodo.pop("default", None)
        if nodo.get("type") == "object" and isinstance(nodo.get("properties"), dict):
            nodo["additionalProperties"] = False
            nodo["required"] = list(nodo["properties"].keys())

        for valor in nodo.values():
            normalizar(valor)

    normalizar(copia)
    return copia


class ClienteDeInferencia:
    """Habla con el proveedor. Una instancia por consumidor: la contabilidad es por instancia."""

    def __init__(self, config: ConfigInferencia | None = None) -> None:
        self.config = config or ConfigInferencia.desde_entorno()
        self.consumo = Consumo()

    # -- transporte -----------------------------------------------------------------------

    def _postear(self, cuerpo: dict[str, Any]) -> dict[str, Any]:
        # Levanta la taxonomía de excepciones que declara el encabezado del módulo.
        pedido = urllib.request.Request(
            f"{self.config.base_url}/chat/completions",
            data=json.dumps(cuerpo).encode("utf-8"),
            headers={
                # La clave se arma acá y no se guarda en ningún atributo ni mensaje de error.
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
                "User-Agent": AGENTE,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                pedido, timeout=self.config.timeout, context=_contexto_tls()
            ) as r:
                datos: dict[str, Any] = json.loads(r.read())
                return datos
        except urllib.error.HTTPError as exc:
            detalle = exc.read().decode("utf-8", "replace")[:400]
            if exc.code == 429:
                raise _LimiteDeTasaError(exc.headers.get("retry-after")) from exc
            if 500 <= exc.code < 600:
                raise _TransitorioError(f"HTTP {exc.code}") from exc
            if exc.code == 400 and CODIGO_ESQUEMA_NO_CUMPLIDO in detalle:
                raise _TransitorioError(f"HTTP 400, {CODIGO_ESQUEMA_NO_CUMPLIDO}") from exc
            # Un 403 con el código 1010 no lo emite el proveedor sino el borde que tiene adelante,
            # y culpar a la credencial, que es lo que hacía esta rama antes, manda a revisar algo
            # que está bien. Los dos rechazos se ven casi iguales y se arreglan de forma opuesta.
            if exc.code == 403 and CODIGO_AGENTE_BLOQUEADO in detalle:
                raise PedidoRechazadoError(
                    f"El borde del proveedor rechazó al cliente, no a la credencial "
                    f"(HTTP 403, código {CODIGO_AGENTE_BLOQUEADO}). Suele ser el User-Agent: "
                    f"este cliente manda '{AGENTE}'. Si volviste a ver esto, el proveedor cambió "
                    f"su política de filtrado."
                )
            if exc.code in (401, 403):
                raise PedidoRechazadoError(
                    f"El proveedor rechazó la credencial (HTTP {exc.code}: {detalle}). "
                    f"Revisá {VARIABLE_DE_CLAVE}: que esté completa, sin espacios ni comillas "
                    f"sobrantes, y que siga activa en la consola del proveedor."
                )
            raise PedidoRechazadoError(
                f"El proveedor rechazó el pedido (HTTP {exc.code}): {detalle}"
            )
        except urllib.error.URLError as exc:
            # Un fallo de verificación de certificados no es "el proveedor no está": es el
            # intérprete que no tiene con qué verificarlo. El mensaje de OpenSSL no nombra ninguna
            # causa accionable, así que se reemplaza por el arreglo concreto.
            if isinstance(exc.reason, ssl.SSLCertVerificationError):
                raise ProveedorInalcanzableError(AYUDA_CERTIFICADOS) from exc
            raise ProveedorInalcanzableError(f"No se pudo alcanzar al proveedor: {exc}") from exc
        except (TimeoutError, ConnectionError) as exc:
            raise ProveedorInalcanzableError(f"No se pudo alcanzar al proveedor: {exc}") from exc

    def _con_reintentos(self, cuerpo: dict[str, Any]) -> dict[str, Any]:
        """Reintenta ante límites de tasa y fallas pasajeras, respetando `retry-after` si viene."""
        ultimo: Exception | None = None
        for intento in range(MAX_REINTENTOS):
            try:
                return self._postear(cuerpo)
            except _LimiteDeTasaError as exc:
                ultimo = exc
                self.consumo.esperas_por_limite += 1
                espera = exc.segundos if exc.segundos is not None else ESPERA_BASE * (2**intento)
            except _TransitorioError as exc:
                ultimo = exc
                espera = ESPERA_BASE * (2**intento)

            if intento == MAX_REINTENTOS - 1:
                break
            time.sleep(min(espera, ESPERA_MAXIMA))

        raise ProveedorInalcanzableError(
            f"El proveedor no respondió tras {MAX_REINTENTOS} intentos: {ultimo}. "
            "El evento vuelve al bus."
        )

    # -- interfaz -------------------------------------------------------------------------

    def completar(
        self,
        sistema: str,
        usuario: str,
        esquema: dict[str, Any],
        nombre_esquema: str = "decision",
        modelo: str | None = None,
        temperatura: float = 0.0,
    ) -> Respuesta:
        """Pide una respuesta que cumpla `esquema`, y contabiliza lo que costó.

        `temperatura` en 0 por defecto: dos corridas sobre el mismo evento tienen que dar lo mismo,
        o la campaña de validación estaría midiendo el azar además del motor.
        """
        elegido = modelo or self.config.modelo
        cuerpo = {
            "model": elegido,
            "temperature": temperatura,
            "messages": [
                {"role": "system", "content": sistema},
                {"role": "user", "content": usuario},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": nombre_esquema,
                    "strict": True,
                    "schema": esquema_estricto(esquema),
                },
            },
        }

        comenzado = time.monotonic()
        datos = self._con_reintentos(cuerpo)
        segundos = time.monotonic() - comenzado

        try:
            contenido = datos["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise PedidoRechazadoError(
                f"Respuesta sin contenido utilizable: {str(datos)[:300]}"
            ) from exc

        uso = datos.get("usage") or {}
        entrada = int(uso.get("prompt_tokens", 0))
        salida = int(uso.get("completion_tokens", 0))
        self.consumo.sumar(entrada, salida, segundos)

        return Respuesta(
            contenido=contenido,
            tokens_entrada=entrada,
            tokens_salida=salida,
            segundos=segundos,
            modelo=elegido,
            crudo=datos,
        )


# Internas: separan los dos motivos por los que conviene reintentar. No salen del módulo, porque el
# llamador solo ve `ProveedorInalcanzableError`, que es la distinción que al grafo le importa.


class _LimiteDeTasaError(Exception):
    def __init__(self, retry_after: str | None) -> None:
        super().__init__("límite de tasa")
        self.segundos: float | None
        try:
            self.segundos = float(retry_after) if retry_after else None
        except ValueError:
            self.segundos = None


class _TransitorioError(Exception):
    pass
