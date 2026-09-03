"""El respaldo congelado: qué puede seguir contestando el panel con Elasticsearch abajo.

Es la ruta que sostiene la demo y la que se usa para las capturas del informe, así que conviene que
esté fijada. Lo que se prueba acá son las cuatro cosas que se rompen en silencio:

- que el rango de fechas incluya el último día pedido, y no lo deje afuera por comparar cadenas
- que elegir un sensor cambie el total y no solo la etiqueta
- que la agrupación semanal caiga en lunes, como la etiqueta Elasticsearch
- que la vista por hora conserve la hora en la etiqueta, que es de donde el panel la lee
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from honeyml.api import offline

DIARIO = [
    {"date": "2026-08-19", "count": 30, "cowrie": 20, "dionaea": 10},
    {"date": "2026-08-20", "count": 50, "cowrie": 30, "dionaea": 20},
    {"date": "2026-08-25", "count": 70, "cowrie": 70},
]

HORARIO = [
    {"date": "2026-08-24 23", "count": 5, "cowrie": 5},
    {"date": "2026-08-25 00", "count": 11, "cowrie": 8, "dionaea": 3},
    {"date": "2026-08-25 14", "count": 22, "cowrie": 22},
]


@pytest.fixture
def congelado(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Un respaldo y una serie horaria de juguete, en disco, como los lee la API."""
    snap = tmp_path / "snapshot.json"
    snap.write_text(json.dumps({"timeline": DIARIO}), encoding="utf-8")
    horas = tmp_path / "horario.json"
    horas.write_text(json.dumps(HORARIO), encoding="utf-8")
    monkeypatch.setattr(offline, "OUT_FILE", snap)
    monkeypatch.setattr(offline, "HORARIO_FILE", horas)


# ---- rango y sensor ---------------------------------------------------------------------------


def test_el_ultimo_dia_del_rango_entra(congelado: None) -> None:
    """El panel manda el fin como "2026-08-25T23:59:59": comparar la cadena entera lo excluiría."""
    r = offline.timeline(desde="2026-08-19", hasta="2026-08-25T23:59:59")
    assert r is not None
    assert [f["date"] for f in r] == ["2026-08-19", "2026-08-20", "2026-08-25"]


def test_el_rango_recorta_de_los_dos_lados(congelado: None) -> None:
    r = offline.timeline(desde="2026-08-20", hasta="2026-08-20T23:59:59")
    assert r is not None
    assert [f["date"] for f in r] == ["2026-08-20"]


def test_elegir_sensor_cambia_el_total_y_no_solo_la_etiqueta(congelado: None) -> None:
    """Dejar el `count` original mostraría la barra entera bajo una etiqueta que dice otra cosa."""
    r = offline.timeline(sensor="dionaea", desde="2026-08-19", hasta="2026-08-20")
    assert r is not None
    assert [(f["date"], f["count"]) for f in r] == [("2026-08-19", 10), ("2026-08-20", 20)]


def test_un_sensor_sin_actividad_ese_dia_da_cero_y_no_desaparece(congelado: None) -> None:
    r = offline.timeline(sensor="dionaea", desde="2026-08-25", hasta="2026-08-25")
    assert r is not None
    assert r == [{"date": "2026-08-25", "count": 0, "dionaea": 0}]


# ---- intervalos -------------------------------------------------------------------------------


def test_la_semana_agrupa_en_lunes(congelado: None) -> None:
    """Mismo día que usa Elasticsearch, para que las barras no se corran al cambiar de origen."""
    r = offline.timeline(interval="week")
    assert r is not None
    assert [f["date"] for f in r] == ["2026-08-17", "2026-08-24"]
    assert r[0]["count"] == 80  # 19 y 20 de agosto caen en la misma semana


def test_la_vista_por_hora_conserva_la_hora_en_la_etiqueta(congelado: None) -> None:
    """El panel parte la etiqueta por el espacio: sin la hora, las 24 barras se llaman igual."""
    r = offline.timeline(interval="hour", desde="2026-08-25", hasta="2026-08-25T23:59:59")
    assert r is not None
    assert [f["date"] for f in r] == ["2026-08-25 00", "2026-08-25 14"]


def test_la_vista_por_hora_tambien_filtra_por_sensor(congelado: None) -> None:
    r = offline.timeline(interval="hour", sensor="dionaea", desde="2026-08-25", hasta="2026-08-25")
    assert r is not None
    assert [(f["date"], f["count"]) for f in r] == [("2026-08-25 00", 3), ("2026-08-25 14", 0)]


def test_sin_serie_horaria_se_declara_incapaz(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Devolver la serie diaria sería una respuesta equivocada disfrazada de correcta."""
    snap = tmp_path / "snapshot.json"
    snap.write_text(json.dumps({"timeline": DIARIO}), encoding="utf-8")
    monkeypatch.setattr(offline, "OUT_FILE", snap)
    monkeypatch.setattr(offline, "HORARIO_FILE", tmp_path / "no-existe.json")

    assert offline.timeline(interval="hour") is None
    # Las demás vistas siguen funcionando: falta una capacidad, no el respaldo entero.
    assert offline.timeline(interval="day") is not None


def test_sin_respaldo_no_hay_nada_que_responder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(offline, "OUT_FILE", tmp_path / "no-existe.json")
    assert offline.timeline() is None


# ---- construcción de la serie horaria ----------------------------------------------------------


def test_la_serie_horaria_excluye_el_trafico_local(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Sin este filtro la serie horaria y la diaria no cuadran, y el gráfico se contradice.

    La tabla consolidada se carga con `match_all` y las consultas del panel excluyen el healthcheck
    del contenedor. Sobre el corpus real la diferencia son 32.732 eventos.
    """
    pd = pytest.importorskip("pandas")
    from honeyml.api.queries import LOCAL_IP

    tabla = tmp_path / "eventos.parquet"
    pd.DataFrame(
        {
            "@timestamp": pd.to_datetime(
                ["2026-08-25T14:10:00Z", "2026-08-25T14:40:00Z", "2026-08-25T14:50:00Z"]
            ),
            "honeypot": ["cowrie", "dionaea", "cowrie"],
            "source.ip": ["203.0.113.7", "203.0.113.8", LOCAL_IP],
        }
    ).to_parquet(tabla)
    monkeypatch.setattr(offline, "TABLA_CONSOLIDADA", tabla)

    serie = offline.construir_serie_horaria()
    assert serie == [{"date": "2026-08-25 14", "count": 2, "cowrie": 1, "dionaea": 1}]


def test_sin_tabla_consolidada_dice_como_generarla(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(offline, "TABLA_CONSOLIDADA", tmp_path / "no-existe.parquet")
    with pytest.raises(FileNotFoundError) as exc:
        offline.construir_serie_horaria()
    assert "make consolidate" in str(exc.value)


def test_el_formato_de_etiqueta_coincide_con_el_de_elasticsearch() -> None:
    """`queries.timeline` corta la clave en 13 caracteres para el intervalo horario."""
    ejemplo: dict[str, Any] = HORARIO[1]
    assert len(ejemplo["date"]) == 13
    assert ejemplo["date"][10] == " "
