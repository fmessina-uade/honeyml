"""Cliente del proveedor de inferencia, con límites de tasa y contabilidad de consumo.

Habla el dialecto compatible con OpenAI que exponen Groq y OpenRouter, por HTTP con `urllib`, así
el motor no carga ningún cliente HTTP. Lo único que se agrega es `certifi`, el paquete de
certificados raíz, para cuando el intérprete no trae almacén propio (ver `_contexto_tls`).

Ante un 429 o un 5xx se reintenta con retroceso acotado, respetando el `retry-after`. Si no alcanza,
o si la red se cae o vence el timeout, se levanta `ProveedorInalcanzableError` y el evento vuelve al
bus sin confirmar, en vez de persistirse como no concluyente. Un `retry-after` por encima de
`ESPERA_MAXIMA`, el bloqueo por límite de gasto o la falta de crédito dan `CuotaAgotadaError`, y el
motor corta la corrida. Un 4xx que no sea 429 es un defecto nuestro y da `PedidoRechazadoError`.

Cada respuesta suma sus tokens y su costo en dólares, el que informa el proveedor o el de `PRECIOS`
si no lo informa: cuánto sale clasificar un evento es una métrica operativa que se reporta.

La salida se pide como `json_schema` con `strict: true`, y la decodificación restringida garantiza
que cumpla el esquema. A cambio exige propiedades obligatorias y objetos cerrados (de eso se ocupa
`esquema_estricto`) y no admite herramientas ni streaming. Con un enrutador, `preferencias_de_ruteo`
descarta a los proveedores que no respetan el modo estricto.
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

# Precio por millón de tokens, en dólares, según la lista de Groq. Solo se usa cuando el proveedor
# no informa el costo de la llamada. Está acá y no en un cálculo suelto para que actualizarlo sea
# una línea, y un modelo que no figure se contabiliza en tokens y no en dinero: preferible a
# inventar un precio.
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
# pésima idea para un consumidor. Una espera así de larga quiere decir que se agotó la cuota, y eso
# afecta igual a todos los eventos que siguen: devolverlos al bus uno por uno los llevaría, a la
# tercera entrega, a la cola de muertos. Por encima de este techo no se reintenta, se corta la
# corrida.
ESPERA_MAXIMA = 30.0


# Identificación del cliente. Sin ella `urllib` manda `Python-urllib/3.12`, y el borde de
# Cloudflare que el proveedor tiene adelante lo rechaza con un 403 y el código 1010 ("navegador
# vedado") antes de que el proveedor llegue a ver la petición.
#
# El síntoma confunde, porque la misma petición por `curl` funciona y entonces todo apunta a la
# credencial cuando la credencial está perfecta. Con una clave inválida se ve la diferencia: con el
# agente por defecto contesta 403/1010, y con este contesta 401 "Invalid API Key", que es el error
# honesto de alguien que sí llegó al proveedor.
AGENTE = "honeyml/0.1 (+https://www.honeyml.com.ar)"

# Código de Cloudflare para "agente bloqueado". Se distingue de un rechazo de credencial porque
# mandan a revisar cosas distintas.
CODIGO_AGENTE_BLOQUEADO = "1010"

# El proveedor devuelve este código, con un 400, cuando su decodificación restringida no logra
# producir una respuesta que cumpla el esquema. Parece un pedido mal armado y no lo es: el mismo
# pedido, reenviado tal cual, pasa. Es una falla pasajera del proveedor.
#
# Importa clasificarlo bien. Como rechazo, el evento sale del grafo sin confirmar y hay que esperar
# los diez minutos de la ventana de reclamo para que otro consumidor lo tome, y con la frecuencia
# con que aparece eso convierte una puesta al día en una espera. Como pasajero, se reintenta en el
# acto y el evento sigue.
CODIGO_ESQUEMA_NO_CUMPLIDO = "json_validate_failed"

# Lo que devuelve el proveedor, con un 400, cuando la organización llegó a su límite de gasto
# mensual: bloquea todas las claves hasta el mes siguiente o hasta que se suba el límite.
CODIGO_GASTO_BLOQUEADO = "blocked_api_access"

# Lo que devuelve un enrutador cuando no hay saldo o la clave llegó a su tope de gasto. Igual que el
# bloqueo por gasto, esperar unos segundos no lo arregla.
CODIGO_SIN_CREDITO = 402

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
    apunta su almacén de certificados a `<prefijo>/etc/openssl/cert.pem`, un archivo que su
    instalador crea recién cuando se corre `Install Certificates.command`. Sin ese paso, toda
    conexión HTTPS falla con un mensaje de OpenSSL que no nombra ninguna causa.

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


class CuotaAgotadaError(RuntimeError):
    """El proveedor dejó de aceptar pedidos por cuota, por límite de gasto o por falta de crédito.

    No es un problema del evento ni del pedido, y no se arregla en segundos: afecta igual a todo lo
    que venga detrás. Por eso no se reintenta y va separado de `ProveedorInalcanzableError`, que sí
    es pasajero y devuelve el evento al bus.
    """


@dataclass
class Consumo:
    """Acumulado de lo que gastó el motor. Alimenta las métricas operativas que hay que reportar."""

    llamadas: int = 0
    tokens_entrada: int = 0
    tokens_salida: int = 0
    segundos: float = 0.0
    esperas_por_limite: int = 0
    # Lo que el proveedor informó que costaron las llamadas, y cuántas lo informaron. Solo se usa si
    # lo informaron todas: un total a medias se leería como más barato de lo que fue.
    costo_informado: float = 0.0
    con_costo_informado: int = 0

    def sumar(self, entrada: int, salida: int, segundos: float, costo: float | None = None) -> None:
        self.llamadas += 1
        self.tokens_entrada += entrada
        self.tokens_salida += salida
        self.segundos += segundos
        if costo is not None:
            self.costo_informado += costo
            self.con_costo_informado += 1

    def costo_estimado(self, modelo: str) -> float | None:
        """Costo en dólares: el que informó el proveedor, o el de la tabla, o None si no hay."""
        if self.llamadas and self.con_costo_informado == self.llamadas:
            return self.costo_informado
        precios = PRECIOS.get(modelo)
        if precios is None:
            return None
        p_entrada, p_salida = precios
        return (self.tokens_entrada * p_entrada + self.tokens_salida * p_salida) / 1_000_000

    def resumen(self, modelo: str) -> str:
        costo = self.costo_estimado(modelo)
        linea = (
            f"{self.llamadas} llamadas, {self.tokens_entrada:,} tokens de entrada, "
            f"{self.tokens_salida:,} de salida, {self.segundos:.1f}s"
        ).replace(",", ".")
        if costo is not None:
            linea += f", unos USD {costo:.4f}"
        if self.esperas_por_limite:
            linea += f", {self.esperas_por_limite} esperas por límite de tasa"
        return linea


@dataclass
class Respuesta:
    """Una respuesta y lo que costó. El contenido viene crudo: parsearlo es tarea de quien llama."""

    contenido: str
    tokens_entrada: int
    tokens_salida: int
    segundos: float
    modelo: str
    # Qué proveedor atendió, cuando un enrutador reparte el modelo entre varios.
    proveedor: str = ""
    # Lo que el proveedor dice que costó la llamada, en dólares, cuando lo informa.
    costo_informado: float | None = None
    # Lo que devolvió el proveedor sin tocar, para poder auditar una decisión después.
    crudo: dict[str, Any] = field(default_factory=dict, repr=False)


def costo_de(respuesta: Respuesta) -> float | None:
    """Cuánto costó una respuesta: lo que informó el proveedor, o la tabla, o None.

    `Consumo.costo_estimado` responde lo mismo sobre un acumulado. Esto existe para el nodo de
    persistencia, que guarda el costo de la llamada que produjo cada decisión. Lo informado le gana
    a la tabla porque un enrutador cobra lo que cobra el proveedor que eligió, y eso no es un precio
    fijo.
    """
    if respuesta.costo_informado is not None:
        return respuesta.costo_informado
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


def preferencias_de_ruteo(proveedores: tuple[str, ...]) -> dict[str, Any]:
    """Lo que se le pide a un enrutador sobre a quién mandar el pedido.

    `require_parameters` descarta a los proveedores que no aceptan todo lo que el pedido lleva,
    esquema estricto incluido: sin eso, el enrutador puede elegir uno que trate el esquema como una
    sugerencia. `data_collection: deny` descarta a los que guardan los pedidos, que acá llevan
    telemetría de ataques. Con una lista de proveedores se va solo a esos y en ese orden, así una
    campaña de medición no mezcla servidores sin saberlo.
    """
    preferencias: dict[str, Any] = {"require_parameters": True, "data_collection": "deny"}
    if proveedores:
        preferencias["order"] = list(proveedores)
        preferencias["allow_fallbacks"] = False
    return preferencias


def _exigir_contenido(datos: dict[str, Any]) -> None:
    """Levanta si la respuesta vino bien formada pero sin nada que parsear.

    Pasa con los modelos que razonan: la elección trae el razonamiento y `content` en nulo. Si el
    motivo es que se agotó el presupuesto de salida, reintentar gasta tres llamadas para volver al
    mismo lugar, así que se corta con un rechazo que nombra la causa. Con cualquier otro motivo se
    trata como pasajero, igual que el resto de las respuestas inservibles.
    """
    eleccion = (datos.get("choices") or [{}])[0]
    if (eleccion.get("message") or {}).get("content"):
        return
    motivo = str(eleccion.get("finish_reason") or eleccion.get("native_finish_reason") or "")
    if motivo == "length":
        raise PedidoRechazadoError(
            "El proveedor cortó la respuesta por tamaño y no devolvió contenido: el contexto del "
            "evento no entra en el presupuesto de salida del modelo."
        )
    raise _TransitorioError(f"respuesta sin contenido (motivo: {motivo or 'sin declarar'})")


class ClienteDeInferencia:
    """Habla con el proveedor. Una instancia por consumidor: la contabilidad es por instancia."""

    def __init__(self, config: ConfigInferencia | None = None) -> None:
        self.config = config or ConfigInferencia.desde_entorno()
        self.consumo = Consumo()

    # El transporte

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
                _exigir_contenido(datos)
                return datos
        except urllib.error.HTTPError as exc:
            detalle = exc.read().decode("utf-8", "replace")[:400]
            if exc.code == 429:
                raise _LimiteDeTasaError(exc.headers.get("retry-after")) from exc
            if 500 <= exc.code < 600:
                raise _TransitorioError(f"HTTP {exc.code}") from exc
            if exc.code == 400 and CODIGO_ESQUEMA_NO_CUMPLIDO in detalle:
                raise _TransitorioError(f"HTTP 400, {CODIGO_ESQUEMA_NO_CUMPLIDO}") from exc
            if exc.code == 400 and CODIGO_GASTO_BLOQUEADO in detalle:
                raise CuotaAgotadaError(
                    f"El proveedor bloqueó la organización por límite de gasto "
                    f"({CODIGO_GASTO_BLOQUEADO}). Se reanuda al subir el límite o al empezar "
                    "el mes."
                ) from exc
            if exc.code == CODIGO_SIN_CREDITO:
                raise CuotaAgotadaError(
                    f"El proveedor no tiene crédito para este pedido (HTTP {CODIGO_SIN_CREDITO}): "
                    "se agotó el saldo o el tope de gasto de la clave. Se reanuda al cargar "
                    "crédito o cuando el tope se reinicie."
                ) from exc
            # Un 403 con el código 1010 no lo emite el proveedor sino el borde que tiene adelante,
            # y culpar a la credencial manda a revisar algo que está bien. Los dos rechazos se ven
            # casi iguales y se arreglan de forma opuesta.
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
                if exc.segundos is not None and exc.segundos > ESPERA_MAXIMA:
                    raise CuotaAgotadaError(
                        f"El proveedor pide esperar {exc.segundos:.0f} s antes de volver a "
                        "pedir: se agotó la cuota, no es una ráfaga."
                    ) from exc
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

    # La interfaz

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
        elegido = modelo or self.config.modelo or MODELO_POR_DEFECTO
        cuerpo: dict[str, Any] = {
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
        if self.config.es_enrutador:
            # Un proveedor directo no conoce estos campos. A un enrutador se le pide además que
            # informe el costo real de la llamada, que depende del proveedor que eligió.
            cuerpo["provider"] = preferencias_de_ruteo(self.config.proveedores)
            cuerpo["usage"] = {"include": True}

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
        informado = uso.get("cost")
        costo = float(informado) if isinstance(informado, int | float) else None
        self.consumo.sumar(entrada, salida, segundos, costo)

        return Respuesta(
            contenido=contenido,
            tokens_entrada=entrada,
            tokens_salida=salida,
            segundos=segundos,
            modelo=elegido,
            proveedor=str(datos.get("provider") or ""),
            costo_informado=costo,
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
