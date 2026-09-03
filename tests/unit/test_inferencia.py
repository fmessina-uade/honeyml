"""Las credenciales y el cliente de inferencia, sin tocar la red ni una clave de verdad.

Lo que se fija acá son las tres propiedades que, si se rompen, se rompen en silencio:

- la clave no aparece en ninguna representación del objeto que la guarda
- el esquema que se le manda al proveedor cumple lo que el modo estricto exige
- un límite de tasa y una caída se distinguen de un pedido mal formado, porque el motor los trata
  distinto: los dos primeros devuelven el evento al bus, el tercero es un defecto nuestro
"""

from __future__ import annotations

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


def _config() -> ConfigInferencia:
    return ConfigInferencia(
        api_key=CLAVE, modelo=MODELO_POR_DEFECTO, base_url="http://proveedor.invalido/v1"
    )


# ---- credenciales ----------------------------------------------------------------------------


def test_sin_variable_de_entorno_no_arranca_y_dice_como_arreglarlo(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setattr(config, "ARCHIVO_ENV", tmp_path / "no-existe")
    with pytest.raises(CredencialAusenteError) as exc:
        ConfigInferencia.desde_entorno()
    assert "GROQ_API_KEY" in str(exc.value)
    assert "export" in str(exc.value)  # el mensaje trae el arreglo, no solo el hecho


def test_el_entorno_le_gana_al_archivo(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    """Poner la variable a mano para probar otra clave tiene que funcionar.

    Con la precedencia invertida, que es como estaba mientras esto vivía en el Makefile, una
    corrida con `GROQ_API_KEY=… make …` usaba en silencio la clave del archivo. Lo destapó una
    prueba con una clave inválida a propósito que devolvió éxito.
    """
    env = tmp_path / ".env"
    env.write_text("GROQ_API_KEY=del_archivo\n", encoding="utf-8")
    monkeypatch.setattr(config, "ARCHIVO_ENV", env)

    monkeypatch.setenv("GROQ_API_KEY", "del_entorno")
    assert ConfigInferencia.desde_entorno().api_key == "del_entorno"

    monkeypatch.delenv("GROQ_API_KEY")
    assert ConfigInferencia.desde_entorno().api_key == "del_archivo"


def test_el_archivo_admite_comentarios_comillas_y_lineas_vacias(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """Lo escribe una persona a mano: tiene que tolerar cómo escribe una persona."""
    env = tmp_path / ".env"
    env.write_text(
        '\n# un comentario\n\nGROQ_API_KEY="con_comillas"\nHONEYML_MODELO = otro/modelo \n',
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "ARCHIVO_ENV", env)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("HONEYML_MODELO", raising=False)

    c = ConfigInferencia.desde_entorno()
    assert c.api_key == "con_comillas"
    assert c.modelo == "otro/modelo"


def test_la_clave_no_aparece_en_la_representacion() -> None:
    """Un `print` de depuración es la vía más común por la que una clave llega a un registro."""
    texto = f"{_config()!r} {_config()}"
    assert CLAVE not in texto


def test_enmascarada_distingue_dos_claves_sin_revelar_ninguna() -> None:
    m = _config().enmascarada()
    assert CLAVE not in m
    assert m.startswith("gsk_")


def test_el_modelo_por_defecto_es_el_de_produccion_con_esquema_estricto() -> None:
    assert ConfigInferencia(api_key=CLAVE).modelo == MODELO_POR_DEFECTO
    assert MODELO_POR_DEFECTO in inferencia.PRECIOS  # y tiene precio conocido


# ---- esquema estricto -----------------------------------------------------------------------


def test_el_esquema_de_la_decision_cumple_el_modo_estricto() -> None:
    """Todo obligatorio y objetos cerrados: los dos requisitos que impone el proveedor."""
    estricto = inferencia.esquema_estricto(Decision.model_json_schema())

    assert estricto["additionalProperties"] is False
    assert set(estricto["required"]) == set(estricto["properties"].keys())
    # `tactica_mitre` es opcional en el dominio y por eso viaja como unión con null, no omitido.
    assert "tactica_mitre" in estricto["required"]
    assert {"type": "null"} in estricto["properties"]["tactica_mitre"]["anyOf"]


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


# ---- consumo ---------------------------------------------------------------------------------


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


def _cliente_con(respuestas: list[Any]) -> tuple[inferencia.ClienteDeInferencia, list[dict]]:
    """Cliente cuyo transporte devuelve, o levanta, lo que se le indique, en orden."""
    cliente = inferencia.ClienteDeInferencia(_config())
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


# ---- verificación TLS -----------------------------------------------------------------------


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
    import io

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

    assert "GROQ_API_KEY" in str(exc.value)


def test_un_agente_bloqueado_no_se_confunde_con_una_credencial_mala(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Los dos son 4xx y se ven casi iguales, pero se arreglan de forma opuesta.

    Pasó de verdad: `urllib` manda `Python-urllib/3.12`, el borde de Cloudflare del proveedor lo
    rechaza con 403/1010 antes de que el proveedor vea nada, y el mensaje mandaba a revisar una
    credencial que estaba perfecta.
    """
    cliente = inferencia.ClienteDeInferencia(_config())
    monkeypatch.setattr(inferencia.urllib.request, "urlopen", _rechazo(403, b"error code: 1010"))
    with pytest.raises(inferencia.PedidoRechazadoError) as exc:
        cliente.completar("s", "u", {"type": "object"})

    assert "User-Agent" in str(exc.value)
    assert "GROQ_API_KEY" not in str(exc.value)  # no manda a revisar lo que está bien


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
