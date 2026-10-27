"""Las restricciones que la imagen cowrie/cowrie:latest le impone al formato de userdb.txt.

Cowrie lo abre con el codec ASCII implícito, así que solo admite bytes de 0x00 a 0x7F. auth.py
ignora el segundo campo pero espera tres, y la convención es poner 'x' en lugar de un UID. Una
contraseña vacía hace fallar a auth.py:115 con un IndexError, porque lee passwd[0].
"""

import pathlib

import pytest

USERDB_PATH = pathlib.Path(__file__).parents[2] / "infra/honeypots/cowrie/userdb.txt"


def _data_lines(text: str) -> list[str]:
    """Devuelve solo las líneas que no son comentarios ni vacías."""
    return [line for line in text.splitlines() if line and not line.startswith("#")]


@pytest.fixture
def userdb_text() -> str:
    return USERDB_PATH.read_text(encoding="ascii")


def test_userdb_exists():
    assert USERDB_PATH.exists(), f"Falta {USERDB_PATH}"


def test_userdb_is_ascii():
    """Cowrie abre userdb.txt sin encoding=, así que falla con un byte mayor que 0x7F."""
    raw = USERDB_PATH.read_bytes()
    non_ascii = [(i, b) for i, b in enumerate(raw) if b > 127]
    assert not non_ascii, (
        f"Bytes no-ASCII encontrados: {non_ascii[:3]} (Cowrie lanzará UnicodeDecodeError)"
    )


def test_userdb_field2_is_x(userdb_text):
    """El segundo campo debe ser 'x'; un UID numérico no es inválido pero
    la convención es 'x' según userdb.example de la imagen."""
    bad = []
    for line in _data_lines(userdb_text):
        parts = line.split(":")
        if len(parts) >= 2 and parts[1] != "x":
            bad.append(line)
    assert not bad, f"Entradas con campo 2 incorrecto (debe ser 'x'): {bad}"


def test_userdb_no_empty_passwords(userdb_text):
    """Una contraseña vacía ('user:x:') causa un IndexError en auth.py:115."""
    bad = [line for line in _data_lines(userdb_text) if line.endswith(":")]
    assert not bad, f"Entradas con contraseña vacía (causan IndexError en Cowrie): {bad}"


def test_userdb_has_minimum_entries(userdb_text):
    """Al menos 10 credenciales para capturar ataques reales."""
    count = len(_data_lines(userdb_text))
    assert count >= 10, f"userdb.txt tiene solo {count} entradas (mínimo esperado: 10)"


def test_userdb_root_entry_present(userdb_text):
    """root:x:root debe estar presente, es la credencial más probada en ataques SSH."""
    assert "root:x:root" in userdb_text, "Falta la entrada root:x:root"


def test_userdb_three_fields(userdb_text):
    """Cada línea de datos debe tener exactamente 3 campos separados por ':'."""
    bad = []
    for line in _data_lines(userdb_text):
        if line.count(":") < 2:
            bad.append(line)
    assert not bad, f"Líneas con menos de 3 campos: {bad}"
