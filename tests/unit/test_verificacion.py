"""La verificación por firma: agrupar por firma, muestrear fijo, y contar coincidencias."""

from __future__ import annotations

from typing import Any

import pytest

from honeyml.agent.severidad import Severidad
from honeyml.medicion import verificacion
from honeyml.medicion.verificacion import Conducta, Contraste


def _decision(
    doc_id: str,
    firma: str,
    severidad: str,
    tactica: str | None,
    momento: str,
    reutilizada: str | None,
) -> tuple[str, dict[str, Any]]:
    return doc_id, {
        "@timestamp": momento,
        "evento": {
            "doc_id": doc_id,
            "sensor": "cowrie",
            "categoria": "process",
            "accion": "command",
            "resultado": "",
            "protocolo": "ssh",
        },
        "decision": {"severidad": severidad, "tactica_mitre": tactica},
        "ciclo": {"firma": firma, "reutilizada_de": reutilizada},
    }


def test_agrupar_toma_la_copia_mas_reciente_como_representante() -> None:
    decisiones = [
        _decision("razonada", "f1", "alto", "ejecucion", "2026-10-01T00:00:00Z", None),
        _decision("copia_vieja", "f1", "alto", "ejecucion", "2026-10-02T00:00:00Z", "razonada"),
        _decision("copia_nueva", "f1", "alto", "ejecucion", "2026-10-03T00:00:00Z", "razonada"),
    ]
    conductas = verificacion.agrupar(decisiones)
    c = conductas["f1"]
    assert c.decisiones == 3
    assert c.reutilizadas == 2
    # El representante es un evento copiado, no la decisión razonada, y es el más reciente.
    assert c.representante == "copia_nueva"
    assert c.severidad == "alto"
    assert c.tactica == "ejecucion"


def test_poblacion_deja_afuera_las_firmas_sin_copias() -> None:
    decisiones = [
        _decision("sola", "solo_razonada", "alto", None, "2026-10-01T00:00:00Z", None),
        _decision("razonada", "con_copia", "alto", None, "2026-10-01T00:00:00Z", None),
        _decision("copia", "con_copia", "alto", None, "2026-10-02T00:00:00Z", "razonada"),
    ]
    conductas = verificacion.agrupar(decisiones)
    poblada = verificacion.poblacion(conductas.values())
    assert [c.firma for c in poblada] == ["con_copia"]


def test_elegir_es_fijo_por_semilla_y_se_acota() -> None:
    conductas = [Conducta(firma=f"f{i}", representante=f"d{i}", reutilizadas=1) for i in range(20)]
    una = verificacion.elegir(conductas, cuantas=5, semilla=42)
    otra = verificacion.elegir(conductas, cuantas=5, semilla=42)
    assert len(una) == 5
    assert [c.firma for c in una] == [c.firma for c in otra]


def _contraste(
    sev_g: str, sev_f: str, dentro: bool, tac_g: str | None, tac_f: str | None
) -> Contraste:
    return Contraste(
        firma="f",
        severidad_guardada=sev_g,
        severidad_fresca=sev_f,
        dentro_de_limites=dentro,
        tactica_guardada=tac_g,
        tactica_fresca=tac_f,
    )


def test_comparar_separa_mismo_nivel_de_dentro_de_limites() -> None:
    contrastes = [
        _contraste("alto", "alto", True, "ejecucion", "ejecucion"),  # todo igual
        _contraste("alto", "critico", True, "ejecucion", None),  # sube, dentro, táctica se va
        _contraste("alto", "medio", False, "ejecucion", "ejecucion"),  # fuera del piso
    ]
    r = verificacion.comparar(contrastes)
    assert r["verificadas"] == 3
    assert r["severidad_mismo_nivel"] == 1
    assert r["severidad_distinto_dentro"] == 1
    assert r["severidad_fuera"] == 1
    assert r["tactica_coincide"] == 2
    assert r["derivas_de_tactica"] == {("ejecucion", verificacion.SIN_TACTICA): 1}


def test_contrastar_descarta_cuando_la_telemetria_no_reconstruye_la_firma(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conducta = Conducta(
        firma="esperada",
        representante="d1",
        evento={"sensor": "cowrie", "categoria": "process"},
        severidad="alto",
    )
    # La telemetría trae otro comando: el evento firma distinto y no corresponde a esta decisión.
    monkeypatch.setattr(verificacion.firma, "de_evento", lambda e: "otra")
    assert verificacion.contrastar(conducta, {}, compilado=object()) is None


def test_contrastar_arma_el_contraste_con_la_clasificacion_fresca(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conducta = Conducta(
        firma="f1",
        representante="d1",
        evento={
            "doc_id": "d1",
            "sensor": "cowrie",
            "categoria": "process",
            "accion": "command",
            "resultado": "",
            "protocolo": "ssh",
        },
        severidad="alto",
        tactica="ejecucion",
    )

    class _Fresca:
        severidad = Severidad.CRITICO
        tactica_mitre = "persistencia"

    monkeypatch.setattr(verificacion.firma, "de_evento", lambda e: "f1")
    monkeypatch.setattr(verificacion, "ejecutar", lambda compilado, estado: {"decision": _Fresca()})
    contraste = verificacion.contrastar(conducta, {"process": {"command_line": "x"}}, object())
    assert contraste is not None
    assert contraste.severidad_guardada == "alto"
    assert contraste.severidad_fresca == "critico"
    assert contraste.tactica_fresca == "persistencia"


def test_informe_nombra_la_poblacion_y_el_desglose() -> None:
    resumen = verificacion.comparar([_contraste("alto", "alto", True, "ejecucion", "ejecucion")])
    texto = verificacion.informe(resumen, poblada=123)
    assert "123 firmas reutilizadas" in texto
    assert "mismo nivel que lo copiado: 1/1" in texto
    assert "coincide: 1/1" in texto
