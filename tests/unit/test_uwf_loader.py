"""La verificación de la copia de UWF-ZeekData24 contra la de referencia."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from honeyml.eda import uwf_loader


def _semana(raiz: Path, nombre: str, contenido: bytes) -> None:
    carpeta = raiz / nombre
    carpeta.mkdir()
    (carpeta / "part-00000.snappy.parquet").write_bytes(contenido)


@pytest.fixture
def referencia(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        uwf_loader,
        "HUELLAS",
        {
            "semana-1": hashlib.sha256(b"uno").hexdigest(),
            "semana-2": hashlib.sha256(b"dos").hexdigest(),
        },
    )


@pytest.mark.usefixtures("referencia")
def test_la_misma_copia_no_tiene_diferencias(tmp_path: Path) -> None:
    _semana(tmp_path, "semana-1", b"uno")
    _semana(tmp_path, "semana-2", b"dos")
    assert uwf_loader.verificar(tmp_path) == []


@pytest.mark.usefixtures("referencia")
def test_avisa_contenido_distinto_semana_de_mas_y_semana_faltante(tmp_path: Path) -> None:
    _semana(tmp_path, "semana-1", b"otro contenido")
    _semana(tmp_path, "semana-3", b"tres")
    assert uwf_loader.verificar(tmp_path) == [
        "semana-1: el contenido es distinto",
        "semana-3: no es parte de la copia de referencia",
        "semana-2: falta",
    ]
