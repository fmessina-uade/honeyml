"""Where the inference provider's credentials and endpoint come from.

Del entorno y solo del entorno. No hay archivo de configuración con la clave, no hay valor por
defecto, y no hay forma de que quede en el repositorio por descuido: si la variable no está, el
motor no arranca y dice exactamente qué exportar.

POR QUÉ ESTO ES UN MÓDULO Y NO UN `os.environ` SUELTO

Tres cosas que se hacen una vez acá y se pierden si cada llamador las improvisa:

1. **La clave nunca se imprime.** `repr` y `str` la tapan. Un `print(config)` puesto para depurar
   —o una excepción que arrastre el objeto— es la vía más común por la que una credencial termina
   en un registro, y desde un registro en cualquier lado.
2. **El error dice qué hacer.** "GROQ_API_KEY no está definida" con el comando exacto, en vez de un
   `KeyError` a treinta líneas de profundidad dentro de un nodo del grafo.
3. **El identificador del modelo tiene un solo lugar.** Hoy es un valor con default; la *selección*
   —cuándo conviene el de más capacidad y cuándo el económico— vive en `servicio.py`, que se
   apoya en esta configuración.

SOBRE GROQ EN PARTICULAR
La clave habilita todos los modelos: en la consola no se elige nada. El modelo viaja en cada
llamada, que es justamente por lo que puede ser una decisión del motor y no de la cuenta.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Archivo opcional con las variables, en la raíz del repositorio. Está en .gitignore desde antes de
# que esto existiera y nunca se versiona; `.env.example` documenta qué va adentro.
ARCHIVO_ENV = Path(".env")

# Modelo por defecto: `openai/gpt-oss-120b`.
#
# Elegido por adherencia garantizada al esquema —Groq lo implementa con decodificación restringida—
# y no por precio ni velocidad. Con 100 % de conformidad, el bucle de reintentos correctivos de la
# ciclo de reintentos correctivos deja de ser el camino habitual y pasa a ser la red de seguridad
# que debería ser.
#
# Es de producción, no preview: la defensa es en diciembre y un modelo discontinuado "con poco
# aviso" a mitad de la campaña de validación sería la segunda sustitución forzada del proyecto.
MODELO_POR_DEFECTO = "openai/gpt-oss-120b"

# Alternativa declarada para tandas masivas o si aparecen límites de tasa: mitad de precio y el
# doble de velocidad, con el mismo modo estricto. La política que elige entre los dos está en
# `servicio.py`.
MODELO_ALTERNATIVO = "openai/gpt-oss-20b"

BASE_URL_POR_DEFECTO = "https://api.groq.com/openai/v1"
VARIABLE_DE_CLAVE = "GROQ_API_KEY"

# Un ciclo de triaje razona sobre un contexto de unos pocos miles de tokens. Sesenta segundos es
# holgado para eso y corto para un proveedor que se colgó: pasado ese punto conviene devolver el
# evento al bus antes que retener un consumidor esperando.
TIMEOUT_SEGUNDOS = 60


class CredencialAusenteError(RuntimeError):
    """The provider key is not in the environment. Carries the fix, not just the fact."""


def _del_archivo(clave: str) -> str | None:
    """Read one variable from `.env`, or None. Never overrides what is already in the environment.

    El orden importa y es el que usa toda herramienta de este tipo: **el entorno le gana al
    archivo**. Poner `GROQ_API_KEY=… make lo-que-sea` para probar con otra clave tiene que
    funcionar, y con la precedencia invertida no funciona: el archivo pisa la variable y la corrida
    usa una credencial distinta de la que se pidió, sin decir nada.

    Se descubrió midiendo. Una prueba con una clave inválida a propósito devolvió éxito, que es
    exactamente el fallo silencioso que esta función existe para evitar.

    El parseo es deliberadamente mínimo —`CLAVE=valor`, comentarios con `#`, comillas opcionales—
    porque el archivo lo escribe una persona a mano y no hay razón para admitir más que eso.
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
    """The value of a variable: the environment first, then `.env`, then empty."""
    return (os.environ.get(clave) or _del_archivo(clave) or "").strip()


@dataclass(frozen=True)
class ConfigInferencia:
    """Everything needed to reach the provider. The key is here and never leaves in a log."""

    # `repr=False` no es cosmético: es lo que impide que la clave salga en un `print`, en un
    # `logging.debug(config)` o en el rastro de una excepción que arrastre el objeto.
    api_key: str = field(repr=False)
    modelo: str = MODELO_POR_DEFECTO
    base_url: str = BASE_URL_POR_DEFECTO
    timeout: int = TIMEOUT_SEGUNDOS

    @classmethod
    def desde_entorno(cls, modelo: str | None = None) -> ConfigInferencia:
        """Read the configuration from environment variables, or fail saying what to export."""
        clave = _variable(VARIABLE_DE_CLAVE)
        if not clave:
            raise CredencialAusenteError(
                f"{VARIABLE_DE_CLAVE} no está definida en el entorno. "
                f"Obtené una clave en https://console.groq.com y exportala:\n"
                f'    export {VARIABLE_DE_CLAVE}="gsk_…"\n'
                f"Nunca la escribas en un archivo del repositorio."
            )
        # Cuatro orígenes en orden de precedencia: lo que pide el llamador, el entorno, el archivo
        # `.env` y el valor por defecto. `_variable` resuelve los dos del medio.
        elegido = modelo or _variable("HONEYML_MODELO") or MODELO_POR_DEFECTO
        url = _variable("HONEYML_INFERENCIA_URL") or BASE_URL_POR_DEFECTO
        espera = _variable("HONEYML_INFERENCIA_TIMEOUT") or str(TIMEOUT_SEGUNDOS)
        return cls(api_key=clave, modelo=elegido, base_url=url, timeout=int(espera))

    def enmascarada(self) -> str:
        """The key as it may be shown: enough to tell two keys apart, never enough to use one."""
        if len(self.api_key) <= 8:
            return "…"
        return f"{self.api_key[:4]}…{self.api_key[-4:]}"
