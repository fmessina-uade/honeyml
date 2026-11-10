"""La lectura de las decisiones y el veredicto del analista, sin Elasticsearch.

Tres cosas se rompen sin hacer ruido y por eso se fijan acá. Que la API no escriba más que lo
previsto, y que el veredicto vaya a su propio índice sin tocar la decisión del motor. Que un
veredicto incoherente (una confirmación con clasificación propia, una corrección sin severidad, una
táctica fuera del vocabulario) no llegue a guardarse. Y que "pendiente" sea lo que requiere
revisión y todavía no la tiene, y no cualquier decisión sin revisar.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from honeyml.api import decisiones, queries
from honeyml.api.main import app

pytestmark = pytest.mark.usefixtures("como_analista")

DECISION = {
    "@timestamp": "2026-09-24T12:00:05+00:00",
    "evento": {"doc_id": "d1", "momento": "2026-09-24T12:00:00Z", "sensor": "cowrie"},
    "decision": {"severidad": "medio", "tactica_mitre": None, "concluyente": True},
    "ciclo": {"requiere_revision": True, "consultas_fallidas": ["historial"]},
}


# El veredicto


def test_una_confirmacion_no_trae_clasificacion_propia() -> None:
    with pytest.raises(ValidationError):
        decisiones.Veredicto(veredicto="confirma", severidad="alto")


def test_una_correccion_dice_que_severidad_corresponde() -> None:
    with pytest.raises(ValidationError):
        decisiones.Veredicto(veredicto="corrige", tactica_mitre="Acceso inicial")


def test_la_tactica_corregida_sale_del_vocabulario_del_motor() -> None:
    """Una corrección con un nombre que el motor no puede asignar no se compara con nada."""
    with pytest.raises(ValidationError):
        decisiones.Veredicto(veredicto="corrige", severidad="alto", tactica_mitre="Impacto")


def test_una_correccion_puede_decir_que_no_aplica_ninguna_tactica() -> None:
    v = decisiones.Veredicto(veredicto="corrige", severidad="bajo", tactica_mitre=None)
    assert v.tactica_mitre is None


# La escritura


def _con_decision(monkeypatch: pytest.MonkeyPatch, decision: dict[str, Any] | None) -> list[Any]:
    pedidos: list[Any] = []

    def documento(indice: str, doc_id: str, es_url: str) -> dict[str, Any] | None:
        return decision if indice == decisiones.DECISIONES else None

    def pedir(metodo: str, ruta: str, cuerpo: Any = None, es_url: str = "") -> dict[str, Any]:
        pedidos.append((metodo, ruta, cuerpo))
        return {"result": "created"}

    monkeypatch.setattr(decisiones, "_documento", documento)
    monkeypatch.setattr(decisiones, "_pedir", pedir)
    return pedidos


def test_el_veredicto_va_a_su_indice_y_guarda_lo_que_dijo_el_motor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pedidos = _con_decision(monkeypatch, DECISION)
    v = decisiones.Veredicto(veredicto="corrige", severidad="alto", tactica_mitre="Acceso inicial")
    guardado = decisiones.revisar("d1", v)

    [(metodo, ruta, cuerpo)] = pedidos
    assert metodo == "PUT"
    assert ruta.startswith("/honeyml-revisiones/_doc/d1")
    assert cuerpo["severidad"] == "alto"
    # la clasificación del motor queda como estaba, para comparar después
    assert cuerpo["motor"]["severidad"] == "medio"
    assert cuerpo["motor"]["consultas_fallidas"] == ["historial"]
    assert guardado == cuerpo


def test_corregir_olvida_la_firma_para_que_no_se_siga_copiando(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _con_decision(monkeypatch, DECISION)
    olvidadas: list[dict[str, Any]] = []
    monkeypatch.setattr(decisiones, "_olvidar_firma", olvidadas.append)

    v = decisiones.Veredicto(veredicto="corrige", severidad="alto", tactica_mitre="Acceso inicial")
    decisiones.revisar("d1", v)
    assert olvidadas == [DECISION]


def test_confirmar_no_olvida_la_firma(monkeypatch: pytest.MonkeyPatch) -> None:
    _con_decision(monkeypatch, DECISION)
    olvidadas: list[dict[str, Any]] = []
    monkeypatch.setattr(decisiones, "_olvidar_firma", olvidadas.append)

    decisiones.revisar("d1", decisiones.Veredicto(veredicto="confirma"))
    assert olvidadas == []


def test_olvidar_firma_borra_la_del_documento(monkeypatch: pytest.MonkeyPatch) -> None:
    borradas: list[str] = []

    class RepertorioFalso:
        def olvidar(self, firma: str) -> None:
            borradas.append(firma)

    monkeypatch.setattr(decisiones, "RepertorioEnElBus", RepertorioFalso)
    monkeypatch.setattr(decisiones, "_repertorio", None)
    decisiones._olvidar_firma({"ciclo": {"firma": "abc123"}})
    assert borradas == ["abc123"]

    # sin firma no intenta nada
    decisiones._olvidar_firma({"ciclo": {}})
    assert borradas == ["abc123"]


def test_no_se_confirma_lo_que_el_motor_no_clasifico(monkeypatch: pytest.MonkeyPatch) -> None:
    sin_clasificar = {**DECISION, "decision": {"concluyente": False}}
    pedidos = _con_decision(monkeypatch, sin_clasificar)
    with pytest.raises(decisiones.SinClasificacionError):
        decisiones.revisar("d1", decisiones.Veredicto(veredicto="confirma"))
    assert pedidos == []


def test_sin_decision_del_motor_no_hay_nada_que_revisar(monkeypatch: pytest.MonkeyPatch) -> None:
    pedidos = _con_decision(monkeypatch, None)
    assert decisiones.revisar("d1", decisiones.Veredicto(veredicto="confirma")) is None
    assert pedidos == []


def test_todo_campo_del_veredicto_esta_en_la_plantilla(monkeypatch: pytest.MonkeyPatch) -> None:
    """El índice es estricto: un campo sin declarar hace que Elasticsearch rechace el veredicto."""
    plantilla = json.loads(
        (
            Path(__file__).parents[2] / "infra/elastic/templates/honeyml-revisiones-template.json"
        ).read_text(encoding="utf-8")
    )["template"]["mappings"]

    def campos(mapeo: dict[str, Any], prefijo: str = "") -> set[str]:
        salida: set[str] = set()
        for nombre, spec in mapeo["properties"].items():
            salida |= (
                campos(spec, f"{prefijo}{nombre}.") if "properties" in spec else {prefijo + nombre}
            )
        return salida

    def planos(doc: dict[str, Any], prefijo: str = "") -> set[str]:
        salida: set[str] = set()
        for k, v in doc.items():
            salida |= planos(v, f"{prefijo}{k}.") if isinstance(v, dict) else {prefijo + k}
        return salida

    _con_decision(monkeypatch, DECISION)
    guardado = decisiones.revisar(
        "d1", decisiones.Veredicto(veredicto="corrige", severidad="alto", nota="x")
    )
    assert plantilla["dynamic"] == "strict"
    assert guardado is not None
    assert planos(guardado) <= campos(plantilla)


# Los filtros


def test_pendiente_es_lo_que_requiere_revision_y_no_la_tiene() -> None:
    q = decisiones._filtros(None, None, None, "pendientes", ["d1"])
    assert {"term": {"ciclo.requiere_revision": True}} in q["bool"]["filter"]
    assert {"ids": {"values": ["d1"]}} in q["bool"]["must_not"]


def test_sin_tactica_se_filtra_por_ausencia() -> None:
    q = decisiones._filtros(None, decisiones.SIN_TACTICA, None, "todas", [])
    assert {"exists": {"field": "decision.tactica_mitre"}} in q["bool"]["must_not"]


def test_el_resumen_descuenta_de_pendientes_lo_ya_revisado(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def falsa(body: dict[str, Any], es_url: str = "", index: str = "") -> dict[str, Any]:
        if index == decisiones.REVISIONES:
            if body.get("aggs"):
                return {"aggregations": {"v": {"buckets": [{"key": "corrige", "doc_count": 1}]}}}
            return {"hits": {"hits": [{"_id": "d1"}]}}
        cubos = {"buckets": [{"key": "alto", "doc_count": 3}, {"key": "bajo", "doc_count": 2}]}
        return {
            "hits": {"total": {"value": 5}},
            "aggregations": {
                "severidad": cubos,
                "tactica": {"buckets": []},
                "sensor": {"buckets": []},
                "modelo": {"buckets": []},
                "copiadas": {"doc_count": 4},
                "corregidas_por_el_motor": {"doc_count": 0},
                "no_concluyentes": {"doc_count": 0},
                "costo": {"value": 0.001},
                "requieren_revision": {"doc_count": 2, "ya_revisadas": {"doc_count": 1}},
                "en_vivo": {
                    "ultima": {"value_as_string": "2026-09-24T12:00:05.000Z"},
                    "hora": {
                        "doc_count": 7,
                        "copiadas": {"doc_count": 6},
                        "por_minuto": {
                            "buckets": [
                                {
                                    "key_as_string": "2026-09-24T11:59:00.000Z",
                                    "doc_count": 0,
                                    "copiadas": {"doc_count": 0},
                                },
                                {
                                    "key_as_string": "2026-09-24T12:00:00.000Z",
                                    "doc_count": 7,
                                    "copiadas": {"doc_count": 6},
                                },
                            ]
                        },
                    },
                },
                "conclusion": {
                    "doc_count": 5,
                    "percentiles": {"values": {"50.0": 4000.0, "90.0": 12000.0}},
                    "media": {"value": 5500.0},
                    "copiadas": {"doc_count": 4, "media": {"value": 3000.0}},
                    "razonadas": {
                        "doc_count": 1,
                        "media": {"value": 15000.0},
                        "modelo_s": {"value": 2.8},
                    },
                },
            },
        }

    monkeypatch.setattr(queries, "_search", falsa)
    r = decisiones.resumen()

    assert r["revision"] == {
        "requieren": 2,
        "pendientes": 1,
        "revisadas": 1,
        "confirmadas": 0,
        "corregidas": 1,
    }
    assert [c["key"] for c in r["por_severidad"]] == ["bajo", "alto"]  # en el orden de la escala
    assert r["conclusion"]["mediana_s"] == 4.0
    assert r["conclusion"]["media_s"] == 5.5
    assert r["conclusion"]["copiadas_s"] == 3.0
    assert r["conclusion"]["razonadas_s"] == 15.0
    assert r["conclusion"]["modelo_s"] == 2.8
    assert r["sin_saldo"] is None
    assert r["actividad"] == {
        "ultima": "2026-09-24T12:00:05.000Z",
        "ultima_hora": 7,
        "copiadas_ultima_hora": 6,
        # el minuto sin decisiones viene igual: el gráfico tiene que mostrar el silencio
        "por_minuto": [
            {"minuto": "2026-09-24T11:59:00.000Z", "decisiones": 0, "copiadas": 0},
            {"minuto": "2026-09-24T12:00:00.000Z", "decisiones": 7, "copiadas": 6},
        ],
    }


# Las rutas


def test_la_api_escribe_solo_lo_previsto() -> None:
    """Los veredictos, las cuentas y la sesión. Ninguna ruta escribe telemetría ni decisiones."""
    escrituras = {
        ruta.path  # type: ignore[attr-defined]
        for ruta in app.routes
        if set(getattr(ruta, "methods", set())) - {"GET", "HEAD"}
    }
    assert escrituras == {
        "/api/decisiones/{doc_id}/revision",
        "/api/decisiones/{doc_id}/revision-a-ciegas",
        "/api/sesion",
        "/api/sesion/contrasena",
        "/api/usuarios",
        "/api/usuarios/{nombre}",
        "/api/reporte",
    }


def test_un_veredicto_incoherente_se_rechaza_antes_de_llegar_al_indice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pedidos = _con_decision(monkeypatch, DECISION)
    r = TestClient(app).put(
        "/api/decisiones/d1/revision", json={"veredicto": "confirma", "severidad": "alto"}
    )
    assert r.status_code == 422
    assert pedidos == []


def test_confirmar_lo_no_clasificado_contesta_422(monkeypatch: pytest.MonkeyPatch) -> None:
    _con_decision(monkeypatch, {**DECISION, "decision": {"concluyente": False}})
    r = TestClient(app).put("/api/decisiones/d1/revision", json={"veredicto": "confirma"})
    assert r.status_code == 422
    assert "no hay nada que confirmar" in r.json()["detail"]


def test_revisar_un_evento_sin_decision_contesta_404(monkeypatch: pytest.MonkeyPatch) -> None:
    _con_decision(monkeypatch, None)
    r = TestClient(app).put("/api/decisiones/zz/revision", json={"veredicto": "confirma"})
    assert r.status_code == 404


def test_el_tiempo_de_conclusion_deja_afuera_lo_vuelto_a_triar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Una tanda de retriaje sobre eventos viejos lleva la mediana a días."""
    capturado: dict[str, Any] = {}

    def falsa(body: dict[str, Any], es_url: str = "", index: str = "") -> dict[str, Any]:
        if index == decisiones.REVISIONES:
            return {"hits": {"hits": []}, "aggregations": {"v": {"buckets": []}}}
        capturado.update(body)
        raise RuntimeError("alcanza con el pedido")

    monkeypatch.setattr(queries, "_search", falsa)
    with pytest.raises(RuntimeError):
        decisiones.resumen()

    filtro = capturado["aggs"]["conclusion"]["filter"]["bool"]
    assert {"term": {"ciclo.retriaje": True}} in filtro["must_not"]


def _con_tanda(
    monkeypatch: pytest.MonkeyPatch, despues: int
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Una tanda sobre el atraso y `despues` decisiones en marcha desde que terminó."""
    pedidos: list[dict[str, Any]] = []
    principal: dict[str, Any] = {}

    def falsa(body: dict[str, Any], es_url: str = "", index: str = "") -> dict[str, Any]:
        if index == decisiones.REVISIONES:
            return {"hits": {"hits": []}, "aggregations": {"v": {"buckets": []}}}
        aggs = body.get("aggs", {})
        if "conclusion" in aggs:
            principal.update(body)
            raise RuntimeError("alcanza con el pedido")
        pedidos.append(body)
        if "inicio" in aggs:
            return {
                "aggregations": {
                    "inicio": {"value_as_string": "2026-11-10T06:00:00.000Z"},
                    "fin": {"value_as_string": "2026-11-10T14:00:00.000Z"},
                }
            }
        if "ultima" in aggs:
            return {"aggregations": {"ultima": {"value_as_string": "2026-10-30T18:00:00.000Z"}}}
        return {"hits": {"total": {"value": despues}}}

    monkeypatch.setattr(queries, "_search", falsa)
    with pytest.raises(RuntimeError):
        decisiones.resumen()
    return pedidos, principal


def _filtro_de_conclusion(principal: dict[str, Any]) -> list[dict[str, Any]]:
    filtro: list[dict[str, Any]] = principal["aggs"]["conclusion"]["filter"]["bool"]["filter"]
    return filtro


def test_recien_terminada_una_tanda_se_mide_la_semana_de_antes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Después de una pausa, ni la tanda ni la cola que se formó detrás miden al motor."""
    _, principal = _con_tanda(monkeypatch, despues=3)
    filtro = _filtro_de_conclusion(principal)
    assert {"range": {"demora_ms": {"lt": decisiones.UMBRAL_ATRASO_MS}}} in filtro
    ventana = {"gte": "2026-10-30T18:00:00.000Z||-7d", "lte": "2026-10-30T18:00:00.000Z"}
    assert {"range": {"@timestamp": ventana}} in filtro
    # Lo que se deja afuera es la tanda entera, con la hora de cola que sigue a su última decisión.
    afuera = principal["aggs"]["atrasadas"]["filter"]["bool"]["filter"]
    tanda = {"gte": "2026-11-10T06:00:00.000Z", "lte": "2026-11-10T15:00:00+00:00"}
    assert afuera == [{"range": {"@timestamp": tanda}}]


def test_con_decisiones_de_sobra_despues_de_la_tanda_se_mide_desde_ahi(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, principal = _con_tanda(monkeypatch, despues=decisiones.MIN_EN_MARCHA)
    filtro = _filtro_de_conclusion(principal)
    assert {"range": {"@timestamp": {"gt": "2026-11-10T15:00:00+00:00"}}} in filtro


def test_el_resumen_avisa_cuando_el_motor_esta_sin_saldo(monkeypatch: pytest.MonkeyPatch) -> None:
    marca = {"desde": "2026-10-13T10:00:00+00:00", "ultimo_intento": "2026-10-13T10:05:00+00:00"}

    class _Puesta:
        def leer(self) -> dict[str, Any]:
            return marca

    monkeypatch.setattr(decisiones, "_marca", _Puesta())
    assert decisiones._sin_saldo() == marca


def test_si_el_bus_falla_el_resumen_no_inventa_el_aviso(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Rota:
        def leer(self) -> None:
            raise RuntimeError("bus caído")

    monkeypatch.setattr(decisiones, "_marca", _Rota())
    assert decisiones._sin_saldo() is None


# El camino por el grafo


def test_una_copia_sale_por_el_atajo_de_memoria() -> None:
    d = {"ciclo": {"reutilizada_de": "otro", "intentos": 0}}
    assert decisiones.camino(d) == ["memoria", "persistencia"]


def test_sin_contexto_corta_despues_de_contexto() -> None:
    d = {"ciclo": {"motivo_de_corte": "sin_contexto", "intentos": 0}}
    assert decisiones.camino(d) == ["memoria", "contexto", "persistencia"]


def test_cada_intento_es_una_vuelta_por_inferencia_y_validacion() -> None:
    """Un rechazo de la validación devuelve el borrador a inferencia: dos intentos, dos vueltas."""
    d = {"ciclo": {"intentos": 2, "rechazos": 1}}
    assert decisiones.camino(d) == [
        "memoria",
        "contexto",
        "historial",
        "inferencia",
        "validacion",
        "inferencia",
        "validacion",
        "persistencia",
    ]


def test_el_listado_en_vivo_ordena_por_decision_y_deja_afuera_el_retriaje(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capturado: dict[str, Any] = {}

    def falsa(body: dict[str, Any], es_url: str = "", index: str = "") -> dict[str, Any]:
        if index == decisiones.REVISIONES:
            return {"hits": {"hits": []}}
        capturado.update(body)
        return {"hits": {"total": {"value": 1}, "hits": [{"_id": "d1", "_source": DECISION}]}}

    monkeypatch.setattr(queries, "_search", falsa)
    r = decisiones.listar(orden="decision")

    assert capturado["sort"] == [{"@timestamp": {"order": "desc", "missing": "_last"}}]
    assert {"term": {"ciclo.retriaje": True}} in capturado["query"]["bool"]["must_not"]
    assert r["items"][0]["camino"][0] == "memoria"


def test_razonadas_deja_afuera_las_copias(monkeypatch: pytest.MonkeyPatch) -> None:
    capturado: dict[str, Any] = {}

    def falsa(body: dict[str, Any], es_url: str = "", index: str = "") -> dict[str, Any]:
        if index == decisiones.REVISIONES:
            return {"hits": {"hits": []}}
        capturado.update(body)
        return {"hits": {"total": {"value": 0}, "hits": []}}

    monkeypatch.setattr(queries, "_search", falsa)
    decisiones.listar(orden="decision", razonadas=True)
    assert {"exists": {"field": "ciclo.reutilizada_de"}} in capturado["query"]["bool"]["must_not"]
