"""La lectura de las decisiones y el veredicto del analista, sin Elasticsearch.

Tres cosas se rompen sin hacer ruido y por eso se fijan acá. Que la revisión sea la única escritura
de la API, y que vaya a su propio índice sin tocar la decisión del motor. Que un veredicto
incoherente (una confirmación con clasificación propia, una corrección sin severidad, una táctica
fuera del vocabulario) no llegue a guardarse. Y que "pendiente" sea lo que requiere revisión y
todavía no la tiene, y no cualquier decisión sin revisar.
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
                "conclusion": {
                    "doc_count": 5,
                    "percentiles": {"values": {"50.0": 4000.0, "90.0": 12000.0}},
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


# Las rutas


def test_la_revision_es_la_unica_escritura_de_la_api() -> None:
    escrituras = {
        ruta.path  # type: ignore[attr-defined]
        for ruta in app.routes
        if set(getattr(ruta, "methods", set())) - {"GET", "HEAD"}
    }
    assert escrituras == {"/api/decisiones/{doc_id}/revision"}


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
