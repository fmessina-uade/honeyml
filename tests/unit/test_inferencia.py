"""Las credenciales y el cliente de inferencia, sin tocar la red ni una clave de verdad.

Lo que se fija acá son las propiedades que, si se rompen, se rompen en silencio:

- la clave no aparece en ninguna representación del objeto que la guarda, ni viaja a quien no es
- el esquema que se le manda al proveedor cumple lo que el modo estricto exige
- un límite de tasa y una caída se distinguen de un pedido mal formado, porque el motor los trata
  distinto: los dos primeros devuelven el evento al bus, el tercero es un defecto nuestro
- con un enrutador, el pedido solo puede ir a proveedores que respeten el esquema
"""

from __future__ import annotations

import io
import json
import ssl
import urllib.error
from typing import Any

import pytest

from honeyml.agent.adapters import config, inferencia
from honeyml.agent.adapters.config import (
    MODELO_POR_DEFECTO,
    ConfigInferencia,
    CredencialAusenteError,
)
from honeyml.agent.state import Decision

CLAVE = "gsk_1234567890abcdefGHIJ"

VARIABLES = (
    "HONEYML_INFERENCIA_CLAVE",
    "GROQ_API_KEY",
    "HONEYML_INFERENCIA_URL",
    "HONEYML_INFERENCIA_PROVEEDORES",
    "HONEYML_MODELO",
)


def _config() -> ConfigInferencia:
    return ConfigInferencia(
        api_key=CLAVE, modelo=MODELO_POR_DEFECTO, base_url="http://proveedor.invalido/v1"
    )


@pytest.fixture
def entorno_limpio(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> pytest.MonkeyPatch:
    """Sin variables del proveedor ni `.env`: cada prueba define solo lo que usa."""
    for nombre in VARIABLES:
        monkeypatch.delenv(nombre, raising=False)
    monkeypatch.setattr(config, "ARCHIVO_ENV", tmp_path / "no-existe")
    return monkeypatch


# Credenciales
def test_sin_clave_no_arranca_y_dice_como_arreglarlo(entorno_limpio: pytest.MonkeyPatch) -> None:
    with pytest.raises(CredencialAusenteError) as exc:
        ConfigInferencia.desde_entorno()
    assert config.VARIABLE_DE_CLAVE in str(exc.value)
    assert "export" in str(exc.value)  # el mensaje trae el arreglo, no solo el hecho


def test_el_entorno_le_gana_al_archivo(entorno_limpio: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """Poner la variable a mano para probar otra clave tiene que funcionar.

    Con la precedencia invertida, una corrida con `HONEYML_INFERENCIA_CLAVE=otra make algo` usaría
    en silencio la clave del archivo, y una prueba con una clave inválida a propósito daría éxito.
    """
    env = tmp_path / ".env"
    env.write_text("HONEYML_INFERENCIA_CLAVE=del_archivo\n", encoding="utf-8")
    entorno_limpio.setattr(config, "ARCHIVO_ENV", env)

    entorno_limpio.setenv("HONEYML_INFERENCIA_CLAVE", "del_entorno")
    assert ConfigInferencia.desde_entorno().api_key == "del_entorno"

    entorno_limpio.delenv("HONEYML_INFERENCIA_CLAVE")
    assert ConfigInferencia.desde_entorno().api_key == "del_archivo"


def test_el_archivo_admite_comentarios_comillas_y_lineas_vacias(
    entorno_limpio: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """Lo escribe una persona a mano: tiene que tolerar cómo escribe una persona."""
    env = tmp_path / ".env"
    env.write_text(
        '\n# un comentario\n\nHONEYML_INFERENCIA_CLAVE="con_comillas"\n'
        "HONEYML_MODELO = otro/modelo \n"
        "HONEYML_INFERENCIA_PROVEEDORES = groq, cerebras ,\n",
        encoding="utf-8",
    )
    entorno_limpio.setattr(config, "ARCHIVO_ENV", env)

    c = ConfigInferencia.desde_entorno()
    assert c.api_key == "con_comillas"
    assert c.modelo == "otro/modelo"
    assert c.proveedores == ("groq", "cerebras")


def test_la_clave_de_groq_solo_viaja_a_groq(entorno_limpio: pytest.MonkeyPatch) -> None:
    """Mandarle a otro proveedor una clave que no es suya se la entrega a un tercero."""
    entorno_limpio.setenv("GROQ_API_KEY", "gsk_de_groq")
    assert ConfigInferencia.desde_entorno().api_key == "gsk_de_groq"

    entorno_limpio.setenv("HONEYML_INFERENCIA_URL", "https://openrouter.ai/api/v1")
    with pytest.raises(CredencialAusenteError):
        ConfigInferencia.desde_entorno()


def test_la_clave_neutral_le_gana_a_la_de_groq(entorno_limpio: pytest.MonkeyPatch) -> None:
    entorno_limpio.setenv("GROQ_API_KEY", "gsk_de_groq")
    entorno_limpio.setenv("HONEYML_INFERENCIA_CLAVE", "la_neutral")
    assert ConfigInferencia.desde_entorno().api_key == "la_neutral"


def test_solo_un_enrutador_cuenta_como_enrutador() -> None:
    assert ConfigInferencia(api_key=CLAVE, base_url="https://openrouter.ai/api/v1").es_enrutador
    assert not _config().es_enrutador


def test_la_clave_no_aparece_en_la_representacion() -> None:
    """Un `print` de depuración es la vía más común por la que una clave llega a un registro."""
    texto = f"{_config()!r} {_config()}"
    assert CLAVE not in texto


def test_enmascarada_distingue_dos_claves_sin_revelar_ninguna() -> None:
    m = _config().enmascarada()
    assert CLAVE not in m
    assert m.startswith("gsk_")


def test_el_modelo_fijado_sale_del_entorno_y_sin_definirlo_no_hay(
    entorno_limpio: pytest.MonkeyPatch,
) -> None:
    entorno_limpio.setenv("HONEYML_INFERENCIA_CLAVE", "k")
    assert ConfigInferencia.desde_entorno().modelo is None

    entorno_limpio.setenv("HONEYML_MODELO", MODELO_POR_DEFECTO)
    assert ConfigInferencia.desde_entorno().modelo == MODELO_POR_DEFECTO


def test_sin_modelo_pedido_ni_fijado_el_cliente_usa_el_de_produccion() -> None:
    sin_fijar = ConfigInferencia(api_key=CLAVE, base_url="http://proveedor.invalido/v1")
    cliente, enviados = _cliente_con([_ok()], sin_fijar)
    r = cliente.completar("s", "u", {"type": "object"})

    assert enviados[0]["model"] == MODELO_POR_DEFECTO
    assert r.modelo == MODELO_POR_DEFECTO
    assert MODELO_POR_DEFECTO in inferencia.PRECIOS  # y tiene precio conocido


# Esquema estricto
def test_el_esquema_de_la_decision_cumple_el_modo_estricto() -> None:
    """Todo obligatorio y objetos cerrados: los dos requisitos que impone el proveedor."""
    estricto = inferencia.esquema_estricto(Decision.model_json_schema())

    assert estricto["additionalProperties"] is False
    assert set(estricto["required"]) == set(estricto["properties"].keys())
    # `tactica_mitre` es opcional en el dominio y por eso viaja como unión con null, no omitido.
    assert "tactica_mitre" in estricto["required"]
    assert {"type": "null"} in estricto["properties"]["tactica_mitre"]["anyOf"]
    # El motivo viaja igual, y con su vocabulario cerrado en el esquema.
    motivo = estricto["properties"]["motivo_sin_tactica"]["anyOf"]
    assert {"type": "null"} in motivo
    assert any(set(opcion.get("enum", [])) >= {"fuera_del_catalogo"} for opcion in motivo)


def test_no_quedan_valores_por_defecto_en_el_esquema() -> None:
    """La decodificación restringida no rellena: un default solo confunde sobre quién decide."""

    def sin_default(nodo: Any) -> bool:
        if isinstance(nodo, dict):
            return "default" not in nodo and all(sin_default(v) for v in nodo.values())
        if isinstance(nodo, list):
            return all(sin_default(v) for v in nodo)
        return True

    assert sin_default(inferencia.esquema_estricto(Decision.model_json_schema()))


def test_no_se_muta_el_esquema_original() -> None:
    """Pydantic cachea el esquema por clase: mutarlo afectaría a todo el proceso."""
    original = Decision.model_json_schema()
    antes = json.dumps(original, sort_keys=True)
    inferencia.esquema_estricto(original)
    assert json.dumps(original, sort_keys=True) == antes


# Consumo
def test_la_contabilidad_traduce_tokens_a_dinero() -> None:
    c = inferencia.Consumo()
    c.sumar(entrada=1_000_000, salida=1_000_000, segundos=1.0)
    # 0,15 de entrada + 0,60 de salida por millón
    assert c.costo_estimado(MODELO_POR_DEFECTO) == pytest.approx(0.75)


def test_un_modelo_sin_precio_conocido_no_inventa_uno() -> None:
    c = inferencia.Consumo()
    c.sumar(entrada=1000, salida=1000, segundos=1.0)
    assert c.costo_estimado("modelo/que-no-existe") is None
    assert "USD" not in c.resumen("modelo/que-no-existe")


def test_un_costo_informado_a_medias_no_se_usa() -> None:
    """Si una llamada no lo informó, el total informado quedaría por debajo de lo que se gastó."""
    c = inferencia.Consumo()
    c.sumar(entrada=1_000_000, salida=1_000_000, segundos=1.0, costo=0.01)
    c.sumar(entrada=0, salida=0, segundos=1.0)
    assert c.costo_estimado(MODELO_POR_DEFECTO) == pytest.approx(0.75)


def _cliente_con(
    respuestas: list[Any], configuracion: ConfigInferencia | None = None
) -> tuple[inferencia.ClienteDeInferencia, list[dict]]:
    """Cliente cuyo transporte devuelve, o levanta, lo que se le indique, en orden."""
    cliente = inferencia.ClienteDeInferencia(configuracion or _config())
    enviados: list[dict] = []

    def falso(cuerpo: dict[str, Any]) -> dict[str, Any]:
        enviados.append(cuerpo)
        siguiente = respuestas.pop(0)
        if isinstance(siguiente, Exception):
            raise siguiente
        return siguiente

    cliente._postear = falso  # type: ignore[method-assign]
    return cliente, enviados


def _ok(contenido: str = '{"severidad":"alto"}') -> dict[str, Any]:
    return {
        "choices": [{"message": {"content": contenido}}],
        "usage": {"prompt_tokens": 1500, "completion_tokens": 250},
    }


def test_el_camino_feliz_contabiliza_lo_que_costo() -> None:
    cliente, enviados = _cliente_con([_ok()])
    r = cliente.completar("sos un motor de triaje", "clasificá esto", {"type": "object"})

    assert r.tokens_entrada == 1500
    assert cliente.consumo.llamadas == 1
    assert enviados[0]["response_format"]["json_schema"]["strict"] is True
    # Temperatura cero: dos corridas sobre el mismo evento tienen que dar lo mismo.
    assert enviados[0]["temperature"] == 0.0


def test_un_limite_de_tasa_se_espera_y_se_reintenta(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(inferencia.time, "sleep", lambda _: None)
    cliente, enviados = _cliente_con([inferencia._LimiteDeTasaError("1"), _ok()])

    cliente.completar("s", "u", {"type": "object"})
    assert len(enviados) == 2
    assert cliente.consumo.esperas_por_limite == 1


def test_un_limite_que_no_cede_devuelve_el_evento_al_bus(monkeypatch: pytest.MonkeyPatch) -> None:
    """Es transitorio: tiene que reintentarse más tarde, no persistirse como no concluyente."""
    monkeypatch.setattr(inferencia.time, "sleep", lambda _: None)
    cliente, _ = _cliente_con([inferencia._LimiteDeTasaError("1")] * inferencia.MAX_REINTENTOS)

    with pytest.raises(inferencia.ProveedorInalcanzableError):
        cliente.completar("s", "u", {"type": "object"})


def test_un_pedido_mal_formado_no_se_reintenta(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un 4xx que no es 429 es un defecto nuestro: reintentarlo tres veces solo demora el aviso."""
    cliente = inferencia.ClienteDeInferencia(_config())
    intentos = {"n": 0}

    def falso(*_: Any, **__: Any) -> Any:
        intentos["n"] += 1
        raise urllib.error.HTTPError("u", 400, "Bad Request", {}, None)  # type: ignore[arg-type]

    monkeypatch.setattr(inferencia.urllib.request, "urlopen", falso)
    with pytest.raises(inferencia.PedidoRechazadoError):
        cliente.completar("s", "u", {"type": "object"})

    assert intentos["n"] == 1


# Enrutador
def test_con_un_enrutador_el_pedido_exige_esquema_y_privacidad() -> None:
    """El pedido a un enrutador pide proveedores que cumplan el esquema y no guarden datos.

    Sin `require_parameters`, el enrutador puede elegir un proveedor que tome el esquema como
    sugerencia. Sin `data_collection`, uno que guarde telemetría de ataques.
    """
    enrutado = ConfigInferencia(
        api_key=CLAVE, base_url="https://openrouter.ai/api/v1", proveedores=("groq", "cerebras")
    )
    cliente, enviados = _cliente_con([_ok()], enrutado)
    cliente.completar("s", "u", {"type": "object"})

    assert enviados[0]["provider"] == {
        "require_parameters": True,
        "data_collection": "deny",
        "order": ["groq", "cerebras"],
        "allow_fallbacks": False,
    }
    assert enviados[0]["usage"] == {"include": True}


def test_sin_lista_elige_el_enrutador_entre_los_que_cumplen() -> None:
    enrutado = ConfigInferencia(api_key=CLAVE, base_url="https://openrouter.ai/api/v1")
    cliente, enviados = _cliente_con([_ok()], enrutado)
    cliente.completar("s", "u", {"type": "object"})

    assert enviados[0]["provider"] == {"require_parameters": True, "data_collection": "deny"}


def test_un_proveedor_directo_no_recibe_preferencias_de_ruteo() -> None:
    """Un proveedor directo no conoce esos campos, y mandarlos igual es exponerse a un 400."""
    cliente, enviados = _cliente_con([_ok()])
    cliente.completar("s", "u", {"type": "object"})

    assert "provider" not in enviados[0]
    assert "usage" not in enviados[0]


def test_el_costo_informado_le_gana_a_la_tabla() -> None:
    """Un enrutador cobra lo que cobra el proveedor que eligió, que no es el precio de la tabla."""
    respuesta = _ok()
    respuesta["usage"]["cost"] = 0.00042
    respuesta["provider"] = "Groq"
    cliente, _ = _cliente_con([respuesta])
    r = cliente.completar("s", "u", {"type": "object"})

    assert r.proveedor == "Groq"
    assert r.costo_informado == pytest.approx(0.00042)
    assert inferencia.costo_de(r) == pytest.approx(0.00042)
    assert cliente.consumo.costo_estimado(MODELO_POR_DEFECTO) == pytest.approx(0.00042)


# Verificación TLS
def test_nunca_se_desactiva_la_verificacion() -> None:
    """Por esta conexión viaja la credencial: no verificar no es una opción, ni para depurar."""
    ctx = inferencia._contexto_tls()
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True


def test_hay_certificados_cargados() -> None:
    """El síntoma del entorno roto es un almacén vacío, y el error de OpenSSL no lo dice."""
    assert inferencia._contexto_tls().cert_store_stats()["x509_ca"] > 0


def test_un_fallo_de_certificado_explica_como_arreglarlo(monkeypatch: pytest.MonkeyPatch) -> None:
    """`CERTIFICATE_VERIFY_FAILED` a secas no nombra ninguna causa accionable."""
    cliente = inferencia.ClienteDeInferencia(_config())

    def cae(*_: Any, **__: Any) -> Any:
        raise urllib.error.URLError(ssl.SSLCertVerificationError("certificate verify failed"))

    monkeypatch.setattr(inferencia.urllib.request, "urlopen", cae)
    with pytest.raises(inferencia.ProveedorInalcanzableError) as exc:
        cliente.completar("s", "u", {"type": "object"})

    assert "Install Certificates.command" in str(exc.value)
    assert "certifi" in str(exc.value)


def _rechazo(codigo: int, cuerpo: bytes) -> Any:
    """Un HTTPError con cuerpo legible, como el que devuelve el proveedor de verdad."""

    def cae(*_: Any, **__: Any) -> Any:
        raise urllib.error.HTTPError("u", codigo, "no", {}, io.BytesIO(cuerpo))  # type: ignore[arg-type]

    return cae


def test_una_credencial_invalida_apunta_a_la_credencial(monkeypatch: pytest.MonkeyPatch) -> None:
    cliente = inferencia.ClienteDeInferencia(_config())
    monkeypatch.setattr(
        inferencia.urllib.request, "urlopen", _rechazo(401, b'{"error":{"code":"invalid_api_key"}}')
    )
    with pytest.raises(inferencia.PedidoRechazadoError) as exc:
        cliente.completar("s", "u", {"type": "object"})

    assert config.VARIABLE_DE_CLAVE in str(exc.value)


def test_un_agente_bloqueado_no_se_confunde_con_una_credencial_mala(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Los dos son 4xx y se ven casi iguales, pero se arreglan de forma opuesta.

    `urllib` manda `Python-urllib/3.12`, el borde de Cloudflare del proveedor lo rechaza con
    403/1010 antes de que el proveedor vea nada, y un mensaje que culpe a la credencial manda a
    revisar algo que está perfecto.
    """
    cliente = inferencia.ClienteDeInferencia(_config())
    monkeypatch.setattr(inferencia.urllib.request, "urlopen", _rechazo(403, b"error code: 1010"))
    with pytest.raises(inferencia.PedidoRechazadoError) as exc:
        cliente.completar("s", "u", {"type": "object"})

    assert "User-Agent" in str(exc.value)
    assert config.VARIABLE_DE_CLAVE not in str(exc.value)  # no manda a revisar lo que está bien


def test_el_cliente_se_identifica(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sin User-Agent propio, el borde del proveedor rechaza la petición antes de mirarla."""
    cliente = inferencia.ClienteDeInferencia(_config())
    capturado: dict[str, Any] = {}

    def falso(pedido: Any, **_: Any) -> Any:
        capturado["headers"] = pedido.headers
        raise urllib.error.URLError("corte deliberado")

    monkeypatch.setattr(inferencia.urllib.request, "urlopen", falso)
    with pytest.raises(inferencia.ProveedorInalcanzableError):
        cliente.completar("s", "u", {"type": "object"})

    # urllib normaliza los nombres de cabecera a Capitalizado.
    assert capturado["headers"]["User-agent"] == inferencia.AGENTE


def test_una_respuesta_sin_contenido_se_reporta_como_defecto() -> None:
    cliente, _ = _cliente_con([{"choices": []}])
    with pytest.raises(inferencia.PedidoRechazadoError):
        cliente.completar("s", "u", {"type": "object"})


def test_el_esquema_no_cumplido_es_pasajero_y_se_reintenta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un 400 con `json_validate_failed` se reintenta en el acto, no se devuelve el evento al bus.

    El mismo pedido reenviado sin cambios pasa. Clasificado como rechazo, cada uno costaría los diez
    minutos de la ventana de reclamo antes de que otro consumidor lo tome.
    """
    cli = inferencia.ClienteDeInferencia(
        config=ConfigInferencia(api_key="k", modelo="m", base_url="http://x", timeout=1)
    )
    llamadas: list[int] = []
    bueno = {"choices": [{"message": {"content": "{}"}}], "usage": {}}

    class Respuesta:
        def read(self) -> bytes:
            return json.dumps(bueno).encode()

        def __enter__(self) -> Respuesta:
            return self

        def __exit__(self, *_a: Any) -> None:
            return None

    def falla_una_vez(*_a: Any, **_k: Any) -> Any:
        # Se parchea `urlopen` y no `_postear` a propósito: lo que se prueba es la clasificación del
        # error, y vive adentro de `_postear`.
        llamadas.append(1)
        if len(llamadas) == 1:
            raise urllib.error.HTTPError(
                "http://x",
                400,
                "Bad Request",
                {},  # type: ignore[arg-type]
                io.BytesIO(
                    b'{"error":{"code":"' + inferencia.CODIGO_ESQUEMA_NO_CUMPLIDO.encode() + b'"}}'
                ),
            )
        return Respuesta()

    monkeypatch.setattr(inferencia.urllib.request, "urlopen", falla_una_vez)
    monkeypatch.setattr(inferencia.time, "sleep", lambda _s: None)

    assert cli._con_reintentos({}) == bueno
    assert len(llamadas) == 2


class _RespuestaHTTP:
    """Lo mínimo que `urlopen` devuelve: un objeto de contexto con `read`."""

    def __init__(self, datos: dict[str, Any]) -> None:
        self._datos = datos

    def read(self) -> bytes:
        return json.dumps(self._datos).encode()

    def __enter__(self) -> _RespuestaHTTP:
        return self

    def __exit__(self, *_a: Any) -> None:
        return None


def test_un_contenido_nulo_se_reintenta_en_vez_de_romper(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un modelo que razona puede devolver la elección con el razonamiento y `content` en nulo.

    Sin esta guarda, ese nulo llega al nodo, que lo parsea como JSON y revienta con un error de tipo
    en vez de una falla clasificada.
    """
    cliente = inferencia.ClienteDeInferencia(_config())
    vacia = {"choices": [{"finish_reason": "stop", "message": {"content": None}}], "usage": {}}
    buena = {
        "choices": [{"finish_reason": "stop", "message": {"content": "{}"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 2},
    }
    pendientes = [vacia, buena]

    def responde(*_a: Any, **_k: Any) -> Any:
        return _RespuestaHTTP(pendientes.pop(0))

    monkeypatch.setattr(inferencia.urllib.request, "urlopen", responde)
    monkeypatch.setattr(inferencia.time, "sleep", lambda _s: None)

    assert cliente.completar("s", "u", {"type": "object"}).contenido == "{}"
    assert pendientes == []


def test_una_respuesta_cortada_por_tamano_es_un_rechazo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Si no entró en el presupuesto de salida, reintentar vuelve al mismo lugar tres veces."""
    cliente = inferencia.ClienteDeInferencia(_config())
    cortada = {"choices": [{"finish_reason": "length", "message": {"content": None}}], "usage": {}}
    intentos = {"n": 0}

    def responde(*_a: Any, **_k: Any) -> Any:
        intentos["n"] += 1
        return _RespuestaHTTP(cortada)

    monkeypatch.setattr(inferencia.urllib.request, "urlopen", responde)
    with pytest.raises(inferencia.PedidoRechazadoError) as exc:
        cliente.completar("s", "u", {"type": "object"})

    assert intentos["n"] == 1
    assert "tamaño" in str(exc.value)


def test_un_400_cualquiera_sigue_siendo_un_rechazo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Solo ese código es pasajero. Un pedido mal armado de verdad no se reintenta tres veces."""
    cli = inferencia.ClienteDeInferencia(
        config=ConfigInferencia(api_key="k", modelo="m", base_url="http://x", timeout=1)
    )

    def rechaza(*_a: Any, **_k: Any) -> Any:
        raise urllib.error.HTTPError(
            "http://x",
            400,
            "Bad Request",
            {},  # type: ignore[arg-type]
            io.BytesIO(b'{"error":{"code":"model_not_found"}}'),
        )

    monkeypatch.setattr(inferencia.urllib.request, "urlopen", rechaza)
    with pytest.raises(inferencia.PedidoRechazadoError):
        cli._postear({})


# Cuota
def test_una_espera_mas_larga_que_el_techo_es_cuota_y_no_se_reintenta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un `retry-after` de una hora no es una ráfaga: se corta sin esperar ni reintentar.

    Reintentarlo devolvería el evento al bus, y con la cuota agotada eso le pasa a todos los que
    siguen: a la tercera entrega terminarían en la cola de muertos sin tener nada malo.
    """
    esperas: list[float] = []
    monkeypatch.setattr(inferencia.time, "sleep", esperas.append)
    cliente, enviados = _cliente_con([inferencia._LimiteDeTasaError("3600"), _ok()])

    with pytest.raises(inferencia.CuotaAgotadaError):
        cliente.completar("s", "u", {"type": "object"})

    assert len(enviados) == 1
    assert esperas == []


def test_el_bloqueo_por_limite_de_gasto_es_cuota(monkeypatch: pytest.MonkeyPatch) -> None:
    """El 400 `blocked_api_access` llega cuando la organización tocó su límite mensual de gasto."""
    cliente = inferencia.ClienteDeInferencia(_config())
    intentos = {"n": 0}
    cuerpo = b'{"error":{"code":"' + inferencia.CODIGO_GASTO_BLOQUEADO.encode() + b'"}}'

    def bloqueado(*_a: Any, **_k: Any) -> Any:
        intentos["n"] += 1
        raise urllib.error.HTTPError(
            "http://x",
            400,
            "Bad Request",
            {},  # type: ignore[arg-type]
            io.BytesIO(cuerpo),
        )

    monkeypatch.setattr(inferencia.urllib.request, "urlopen", bloqueado)
    with pytest.raises(inferencia.CuotaAgotadaError):
        cliente.completar("s", "u", {"type": "object"})
    assert intentos["n"] == 1


def test_sin_credito_es_cuota(monkeypatch: pytest.MonkeyPatch) -> None:
    """El 402 llega cuando se acabó el saldo o el tope de la clave: reintentar no lo arregla."""
    cliente = inferencia.ClienteDeInferencia(_config())
    intentos = {"n": 0}

    def sin_saldo(*_a: Any, **_k: Any) -> Any:
        intentos["n"] += 1
        raise urllib.error.HTTPError(
            "http://x",
            inferencia.CODIGO_SIN_CREDITO,
            "Payment Required",
            {},  # type: ignore[arg-type]
            io.BytesIO(b'{"error":{"code":402}}'),
        )

    monkeypatch.setattr(inferencia.urllib.request, "urlopen", sin_saldo)
    with pytest.raises(inferencia.CuotaAgotadaError):
        cliente.completar("s", "u", {"type": "object"})
    assert intentos["n"] == 1
