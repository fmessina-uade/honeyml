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
# Es de producción y no preview. La defensa es en diciembre, y un modelo discontinuado a mitad de la
# campaña de validación sería la segunda sustitución forzada del proyecto.
MODELO_POR_DEFECTO = "openai/gpt-oss-120b"

# Para tandas masivas o si aparecen límites de tasa: la mitad de precio y el mismo modo estricto.
# La política que elige entre los dos está en `servicio.py`.
#
# Decía además que era el doble de velocidad, y la primera medición contra datos reales dio lo
# contrario: 13,6 segundos por llamada contra 1,5 del modelo grande. Son cinco llamadas de cada uno,
# muy poco para concluir algo, pero alcanza para no seguir afirmando lo que no se midió.
MODELO_ALTERNATIVO = "openai/gpt-oss-20b"

BASE_URL_POR_DEFECTO = "https://api.groq.com/openai/v1"
VARIABLE_DE_CLAVE = "GROQ_API_KEY"

# Holgado para un contexto de unos pocos miles de tokens, y corto para un proveedor colgado: pasado
# ese punto conviene devolver el evento al bus antes que retener un consumidor esperando.
TIMEOUT_SEGUNDOS = 60


class CredencialAusenteError(RuntimeError):
    """La clave del proveedor no está en el entorno. El mensaje trae el arreglo, no solo el dato."""


def _del_archivo(clave: str) -> str | None:
    """Lee una variable de `.env`, o None. Nunca pisa lo que ya está en el entorno.

    El orden importa: el entorno le gana al archivo. Con la precedencia invertida, poner
    `GROQ_API_KEY=… make lo-que-sea` para probar otra clave usa la del archivo sin avisar. Lo
    descubrimos midiendo: una prueba con una clave inválida a propósito devolvió éxito.
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
    modelo: str = MODELO_POR_DEFECTO
    base_url: str = BASE_URL_POR_DEFECTO
    timeout: int = TIMEOUT_SEGUNDOS

    @classmethod
    def desde_entorno(cls, modelo: str | None = None) -> ConfigInferencia:
        """Lee la configuración del entorno, o falla diciendo qué hay que exportar."""
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
        """Alcanza para distinguir dos claves, nunca para usar una."""
        if len(self.api_key) <= 8:
            return "…"
        return f"{self.api_key[:4]}…{self.api_key[-4:]}"
