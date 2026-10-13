"""Los escenarios de la campaña y la comparación entre lo obtenido y lo esperado."""

from __future__ import annotations

from typing import Any, get_args

from honeyml.agent.state import MotivoSinTactica
from honeyml.medicion import campana
from honeyml.medicion.muestra import transfiere


def test_la_escala_esperada_coincide_con_la_regla_de_transferencia() -> None:
    """La severidad de la escala de cada escenario de comandos es crítica justo cuando la regla
    dice que alguno de sus comandos transfiere. Si no, lo esperado estaría mal fijado."""
    for e in campana.ESCENARIOS:
        if e.sensor != campana.COWRIE:
            continue
        transfiere_alguno = any(transfiere(c) for c in e.comandos)
        critico = e.severidad_escala == "critico"
        assert transfiere_alguno == critico, e.nombre


def test_el_motivo_acompaña_a_la_tactica_nula() -> None:
    """Cada escenario sin táctica declara su motivo, y ninguno con táctica lo lleva."""
    motivos = set(get_args(MotivoSinTactica))
    for e in campana.ESCENARIOS:
        if e.tactica is None:
            assert e.motivo in motivos, e.nombre
        else:
            assert e.motivo is None, e.nombre


def test_cada_comando_apunta_a_un_solo_escenario() -> None:
    """La comparación empareja por comando, así que un comando repetido entre escenarios rompería
    la cuenta."""
    comandos = [c for e in campana.ESCENARIOS for c in e.comandos]
    assert len(comandos) == len(set(comandos))


def test_la_descarga_apunta_a_documentacion() -> None:
    """Ninguna descarga sale a un host real: el rango es el reservado para documentación."""
    for e in campana.ESCENARIOS:
        for c in e.comandos:
            if "http://" in c:
                assert campana.DESTINO in c, e.nombre


def _decision(
    doc_id: str, severidad: str, tactica: str | None, copiada: bool = False
) -> dict[str, Any]:
    return {
        "evento": {"categoria": "process", "doc_id": doc_id, "origen": "10.0.0.5"},
        "decision": {"severidad": severidad, "tactica_mitre": tactica},
        "ciclo": {"reutilizada_de": "otro" if copiada else None},
    }


def _corrida() -> dict[str, Any]:
    return {"desde": "2026-10-12T00:00:00+00:00", "hasta": "2026-10-12T00:10:00+00:00"}


def test_la_comparacion_empareja_y_cuenta_los_aciertos() -> None:
    descarga = f"wget http://{campana.DESTINO}/a"
    decisiones = [
        _decision("a", "alto", "Descubrimiento"),  # acierta en todo
        _decision("b", "alto", "Ejecución"),  # acierta severidad, falla táctica
        _decision("c", "critico", None, copiada=True),
        {  # una autenticación, que se cuenta aparte
            "evento": {"categoria": "authentication", "doc_id": "d", "origen": "10.0.0.5"},
            "decision": {"severidad": "bajo", "tactica_mitre": "Acceso a credenciales"},
            "ciclo": {},
        },
        _decision("e", "alto", "Ejecución"),  # comando que nadie envió: sin emparejar
    ]
    comandos = {"a": "uname -a", "b": "whoami", "c": descarga, "e": "comando que nadie envió"}
    r = campana.comparar(_corrida(), decisiones, comandos)

    assert r["emparejadas"] == 3
    assert r["sin_emparejar"] == 1
    assert r["copiadas"] == 1
    assert r["autenticaciones"] == 1
    # escala: las tres emparejadas aciertan la severidad
    aciertos, total = campana._aciertos(r["severidad_escala"])
    assert (aciertos, total) == (3, 3)
    # táctica: aciertan Descubrimiento y la nula de la descarga, falla whoami
    aciertos, total = campana._aciertos(r["tactica"])
    assert (aciertos, total) == (2, 3)


def test_el_impacto_separa_la_descarga_de_la_escala() -> None:
    """La misma descarga es crítica para la escala y alta para el impacto: la comparación tiene que
    poder mostrar que el motor acierta una referencia y no la otra."""
    decisiones = [_decision("x", "critico", None)]
    comandos = {"x": f"wget http://{campana.DESTINO}/a"}
    r = campana.comparar(_corrida(), decisiones, comandos)

    assert campana._aciertos(r["severidad_escala"]) == (1, 1)  # obtuvo crítico, esperaba crítico
    assert campana._aciertos(r["severidad_impacto"]) == (0, 1)  # esperaba alto


def test_el_informe_en_seco_se_lee() -> None:
    texto = "\n".join(campana.informe_corrida())
    assert "escenarios" in texto
    assert campana.DESTINO in texto
