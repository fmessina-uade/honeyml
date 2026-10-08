"""De dónde salen las credenciales y el punto de acceso del proveedor de inferencia.

Del entorno y solo del entorno, con `.env` como respaldo opcional. Si la variable no está, el motor
no arranca y dice qué exportar.

Es un módulo y no un `os.environ` suelto por dos cosas que se hacen una vez acá y se pierden si cada
llamador las improvisa: que la clave nunca se imprima, y que el error diga qué hacer en vez de ser
un `KeyError` a treinta líneas de profundidad dentro de un nodo del grafo.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Archivo opcional con las variables, en la raíz. Está en .gitignore; `.env.example` dice qué lleva.
ARCHIVO_ENV = Path(".env")

# Elegido por adherencia garantizada al esquema (Groq lo implementa con decodificación restringida)
# y no por precio ni velocidad: con 100 % de conformidad, el ciclo de reintentos correctivos pasa a
# ser la red de seguridad que debería ser, en vez del camino habitual.
#
# Es de producción y no preview: un modelo preview se puede discontinuar con poco aviso, y perderlo
# a mitad de una campaña de validación obliga a cambiar de modelo en el peor momento.
MODELO_POR_DEFECTO = "openai/gpt-oss-120b"

# Para tandas masivas o si aparecen límites de tasa: la mitad de precio y el mismo modo estricto.
# La política que elige entre los dos está en `servicio.py`.
#
# La ventaja que se puede sostener es el precio. Que sea más rápido no está demostrado: en las pocas
# llamadas medidas contra datos reales tarda más que el modelo grande.
MODELO_ALTERNATIVO = "openai/gpt-oss-20b"

BASE_URL_POR_DEFECTO = "https://api.groq.com/openai/v1"

# La clave va con un nombre que no nombra a ningún proveedor: cambiar de proveedor es cambiar la
# dirección y la clave, no el código. `GROQ_API_KEY` se sigue aceptando, pero solo cuando la
# dirección es la de Groq, porque mandarle a otro proveedor una clave que no es suya se la entrega a
# un tercero.
VARIABLE_DE_CLAVE = "HONEYML_INFERENCIA_CLAVE"
VARIABLE_DE_CLAVE_GROQ = "GROQ_API_KEY"
HOST_GROQ = "api.groq.com"

# Un enrutador reparte el mismo modelo entre varios proveedores, y al pedido hay que decirle a
# cuáles puede ir. Ver `preferencias_de_ruteo` en `inferencia.py`.
HOST_OPENROUTER = "openrouter.ai"

# Holgado para un contexto de unos pocos miles de tokens, y corto para un proveedor colgado: pasado
# ese punto conviene devolver el evento al bus antes que retener un consumidor esperando.
TIMEOUT_SEGUNDOS = 60


class CredencialAusenteError(RuntimeError):
    """La clave del proveedor no está en el entorno. El mensaje trae el arreglo, no solo el dato."""


def _del_archivo(clave: str) -> str | None:
    """Lee una variable de `.env`, o None. Nunca pisa lo que ya está en el entorno.

    El orden importa: el entorno le gana al archivo. Con la precedencia invertida, poner
    `HONEYML_INFERENCIA_CLAVE=otra make lo-que-sea` para probar otra clave usaría la del archivo sin
    avisar, y una prueba con una clave inválida a propósito daría éxito.
    """
    if not ARCHIVO_ENV.exists():
        return None
    for linea in ARCHIVO_ENV.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        nombre, _, valor = linea.partition("=")
        if nombre.strip() == clave:
            return valor.strip().strip("\"'")
    return None


def _variable(clave: str) -> str:
    return (os.environ.get(clave) or _del_archivo(clave) or "").strip()


@dataclass(frozen=True)
class ConfigInferencia:
    """Todo lo necesario para alcanzar al proveedor. La clave está acá y no sale en un registro."""

    # `repr=False` es lo que impide que la clave salga en un `print`, en un `logging.debug(config)`
    # o en el rastro de una excepción que arrastre el objeto.
    api_key: str = field(repr=False)
    # El modelo que se pidió por configuración, o None para que elija la política de `servicio.py`.
    # Lo que la desactiva es haberlo pedido y no el valor, así que fijar el modelo capaz, que es al
    # que la política escala, también cuenta.
    modelo: str | None = None
    base_url: str = BASE_URL_POR_DEFECTO
    timeout: int = TIMEOUT_SEGUNDOS
    # A qué proveedores puede ir el pedido, en orden, cuando del otro lado hay un enrutador. Vacío
    # deja que el enrutador elija entre los que cumplen las preferencias fijas.
    proveedores: tuple[str, ...] = ()

    @property
    def es_enrutador(self) -> bool:
        """Si del otro lado hay un enrutador que elige proveedor, y no un proveedor directo."""
        return HOST_OPENROUTER in self.base_url

    @classmethod
    def desde_entorno(cls, modelo: str | None = None) -> ConfigInferencia:
        """Lee la configuración del entorno, o falla diciendo qué hay que definir."""
        url = _variable("HONEYML_INFERENCIA_URL") or BASE_URL_POR_DEFECTO
        clave = _variable(VARIABLE_DE_CLAVE)
        if not clave and HOST_GROQ in url:
            clave = _variable(VARIABLE_DE_CLAVE_GROQ)
        if not clave:
            raise CredencialAusenteError(
                f"{VARIABLE_DE_CLAVE} no está definida. Obtené una clave del proveedor de "
                f"inferencia y definila en .env o exportala:\n"
                f'    export {VARIABLE_DE_CLAVE}="<la clave>"\n'
                f"Con Groq directo también sirve {VARIABLE_DE_CLAVE_GROQ}. "
                f"Nunca la escribas en un archivo del repositorio."
            )
        # Lo que pide el llamador le gana al entorno, y el entorno al archivo `.env`, que es lo que
        # resuelve `_variable`. Si ninguno lo define, no hay modelo fijado.
        elegido = modelo or _variable("HONEYML_MODELO") or None
        espera = _variable("HONEYML_INFERENCIA_TIMEOUT") or str(TIMEOUT_SEGUNDOS)
        proveedores = tuple(
            p.strip() for p in _variable("HONEYML_INFERENCIA_PROVEEDORES").split(",") if p.strip()
        )
        return cls(
            api_key=clave,
            modelo=elegido,
            base_url=url,
            timeout=int(espera),
            proveedores=proveedores,
        )

    def enmascarada(self) -> str:
        """Alcanza para distinguir dos claves, nunca para usar una."""
        if len(self.api_key) <= 8:
            return "..."
        return f"{self.api_key[:4]}...{self.api_key[-4:]}"
