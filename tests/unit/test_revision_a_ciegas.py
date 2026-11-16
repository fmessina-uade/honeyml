"""La revisión a ciegas, sin Elasticsearch.

La clasificación del motor no puede llegar al panel antes de tiempo, el veredicto lo calcula el
servidor, y ni un veredicto común ni otra revisión a ciegas pisan la referencia de la medición.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from honeyml.api import decisiones
from honeyml.api.main import app

pytestmark = pytest.mark.usefixtures("como_analista")

DECISION = {
    "@timestamp": "2026-10-01T12:00:05+00:00",
    "evento": {
        "doc_id": "d2",
        "momento": "2026-10-01T12:00:00Z",
        "sensor": "cowrie",
        "categoria": "process",
        "accion": "command-input",
        "resultado": "unknown",
        "protocolo": "telnet",
        "resumen": "cowrie/process telnet: wget algo",
    },
    "decision": {
        "piso": "alto",
        "techo": "critico",
        "severidad": "critico",
        "tactica_mitre": "Ejecución",
        "justificacion": "trae un binario",
        "evidencia": ["comando: wget"],
        "confianza": 0.9,
    },
    "ciclo": {"requiere_revision": False, "consultas_fallidas": []},
}


@pytest.fixture
def muestra(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    archivo = tmp_path / "muestra.json"
    conductas = [
        {"doc_id": "d1", "estrato": "escalada_sin_transferencia"},
        {"doc_id": "d2", "estrato": "escalada_con_transferencia"},
    ]
    archivo.write_text(json.dumps({"conductas": conductas}), encoding="utf-8")
    monkeypatch.setattr(decisiones, "MUESTRA_FILE", archivo)
    return archivo


def _sin_red(
    monkeypatch: pytest.MonkeyPatch,
    hechas: set[str],
    revision: dict[str, Any] | None = None,
) -> list[Any]:
    guardados: list[Any] = []

    def documento(indice: str, doc_id: str, es_url: str) -> dict[str, Any] | None:
        if indice == decisiones.DECISIONES:
            return DECISION
        return revision

    def pedir(metodo: str, ruta: str, cuerpo: Any = None, es_url: str = "") -> dict[str, Any]:
        guardados.append((metodo, ruta, cuerpo))
        return {"result": "created"}

    monkeypatch.setattr(decisiones, "_documento", documento)
    monkeypatch.setattr(decisiones, "_pedir", pedir)
    monkeypatch.setattr(decisiones, "_revisadas_a_ciegas", lambda ids, es_url: hechas)
    monkeypatch.setattr(
        decisiones, "_atributos_del_evento", lambda doc_id, es_url: {"user.name": "root"}
    )
    return guardados


def test_la_clasificacion_a_ciegas_exige_severidad_y_vocabulario() -> None:
    with pytest.raises(ValidationError):
        decisiones.ClasificacionACiegas.model_validate({"tactica_mitre": "Ejecución"})
    with pytest.raises(ValidationError):
        decisiones.ClasificacionACiegas(severidad="alto", tactica_mitre="Impacto")


def test_la_siguiente_llega_sin_lo_que_dijo_el_motor(
    muestra: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sin_red(monkeypatch, hechas={"d1"})

    item = TestClient(app).get("/api/decisiones/a-ciegas/siguiente").json()

    assert item["doc_id"] == "d2"
    assert (item["total"], item["revisadas"], item["terminada"]) == (2, 1, False)
    assert (item["piso"], item["techo"]) == ("alto", "critico")
    texto = json.dumps(item, ensure_ascii=False)
    # ni la clasificación, ni su justificación, ni el estrato, que dice si el motor escaló
    for delator in ("Ejecución", "trae un binario", "confianza", "evidencia", "escalada"):
        assert delator not in texto
    assert '"critico"' not in texto.replace('"techo": "critico"', "")


def test_con_toda_la_muestra_revisada_avisa_que_termino(
    muestra: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sin_red(monkeypatch, hechas={"d1", "d2"})

    item = TestClient(app).get("/api/decisiones/a-ciegas/siguiente").json()

    assert item == {"total": 2, "revisadas": 2, "terminada": True}


def test_sin_muestra_dice_como_generarla(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(decisiones, "MUESTRA_FILE", tmp_path / "no_existe.json")

    r = TestClient(app).get("/api/decisiones/a-ciegas/siguiente")

    assert r.status_code == 503
    assert "make muestra" in r.json()["detail"]


@pytest.mark.parametrize(
    ("elegida", "veredicto"),
    [
        ({"severidad": "critico", "tactica_mitre": "Ejecución"}, "confirma"),
        ({"severidad": "alto", "tactica_mitre": "Ejecución"}, "corrige"),
        ({"severidad": "critico", "tactica_mitre": None}, "corrige"),
    ],
)
def test_el_veredicto_lo_calcula_el_servidor(
    muestra: Path, monkeypatch: pytest.MonkeyPatch, elegida: dict[str, Any], veredicto: str
) -> None:
    guardados = _sin_red(monkeypatch, hechas=set())

    r = TestClient(app).put("/api/decisiones/d2/revision-a-ciegas", json=elegida)

    assert r.status_code == 200
    [(metodo, ruta, cuerpo)] = guardados
    assert metodo == "PUT" and ruta.startswith(f"/{decisiones.REVISIONES}/_doc/d2")
    assert cuerpo["veredicto"] == veredicto
    assert cuerpo["a_ciegas"] is True
    assert cuerpo["estrato"] == "escalada_con_transferencia"
    # la clasificación propia se guarda siempre, también cuando coincide
    assert cuerpo["severidad"] == elegida["severidad"]
    assert cuerpo["motor"]["severidad"] == "critico"
    assert r.json()["motor"]["tactica_mitre"] == "Ejecución"


def test_un_veredicto_comun_no_pisa_uno_a_ciegas(monkeypatch: pytest.MonkeyPatch) -> None:
    guardados = _sin_red(monkeypatch, hechas=set(), revision={"a_ciegas": True})

    r = TestClient(app).put("/api/decisiones/d2/revision", json={"veredicto": "confirma"})

    assert r.status_code == 409
    assert guardados == []


def test_una_revision_a_ciegas_no_pisa_otra(muestra: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """El panel no la ofrece dos veces, pero la API tiene que negarse igual a un pedido armado."""
    guardados = _sin_red(monkeypatch, hechas={"d2"}, revision={"a_ciegas": True})

    r = TestClient(app).put(
        "/api/decisiones/d2/revision-a-ciegas",
        json={"severidad": "alto", "tactica_mitre": "Ejecución"},
    )

    assert r.status_code == 409
    assert guardados == []


def test_una_revision_a_ciegas_si_reemplaza_un_veredicto_comun(
    muestra: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """La a ciegas es la referencia de la medición: puede llegar después de un veredicto común."""
    guardados = _sin_red(monkeypatch, hechas=set(), revision={"veredicto": "confirma"})

    r = TestClient(app).put(
        "/api/decisiones/d2/revision-a-ciegas",
        json={"severidad": "critico", "tactica_mitre": "Ejecución"},
    )

    assert r.status_code == 200
    [(_, _, cuerpo)] = guardados
    assert cuerpo["a_ciegas"] is True


def test_las_revisadas_a_ciegas_se_buscan_por_marca(monkeypatch: pytest.MonkeyPatch) -> None:
    pedido: dict[str, Any] = {}

    def buscar(indice: str, cuerpo: dict[str, Any], es_url: str) -> dict[str, Any]:
        pedido.update(indice=indice, cuerpo=cuerpo)
        return {"hits": {"hits": [{"_id": "d1"}]}}

    monkeypatch.setattr(decisiones, "_buscar", buscar)

    assert decisiones._revisadas_a_ciegas(["d1", "d2"], "") == {"d1"}
    assert pedido["indice"] == decisiones.REVISIONES
    filtros = pedido["cuerpo"]["query"]["bool"]["filter"]
    assert {"term": {"a_ciegas": True}} in filtros
    assert {"ids": {"values": ["d1", "d2"]}} in filtros
