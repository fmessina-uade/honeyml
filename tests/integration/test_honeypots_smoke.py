"""
Tests de integración (smoke tests) para el stack de honeypots.

Requieren que los contenedores estén corriendo (make dev-up).
Ejecutar con: pytest tests/integration/ -v -m integration

Marcados con @pytest.mark.integration para poder saltearse en CI
sin Docker (pytest tests/unit/ -v).

Si los sensores no están levantados en esta máquina, se saltean en lugar de fallar. La distinción
importa: un sensor apagado es una precondición que no se cumple, no un defecto. Antes fallaban, y
como los sensores viven en el servidor, la suite de integración quedaba en rojo permanente por un
motivo que no era un problema. Una puerta que siempre está roja deja de mirarse.
"""

import socket
import urllib.request

import pytest

pytestmark = pytest.mark.integration

COWRIE_HOST = "127.0.0.1"
COWRIE_SSH_PORT = 2222
COWRIE_TELNET_PORT = 2323
DIONAEA_HTTP_PORT = 8080
DIONAEA_SMB_PORT = 4445


def _tcp_open(host: str, port: int, timeout: float = 5.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _requiere_sensor(host: str, port: int, nombre: str) -> None:
    """Salta la prueba si el sensor no está escuchando acá."""
    if not _tcp_open(host, port, timeout=2.0):
        pytest.skip(f"{nombre} no está levantado en {host}:{port} (make dev-up)")


@pytest.mark.integration
def test_cowrie_ssh_port_open():
    _requiere_sensor(COWRIE_HOST, COWRIE_SSH_PORT, "Cowrie SSH")
    assert _tcp_open(COWRIE_HOST, COWRIE_SSH_PORT)


@pytest.mark.integration
def test_cowrie_telnet_port_open():
    _requiere_sensor(COWRIE_HOST, COWRIE_TELNET_PORT, "Cowrie Telnet")
    assert _tcp_open(COWRIE_HOST, COWRIE_TELNET_PORT)


@pytest.mark.integration
def test_dionaea_http_responds():
    _requiere_sensor(COWRIE_HOST, DIONAEA_HTTP_PORT, "Dionaea HTTP")
    try:
        with urllib.request.urlopen(
            f"http://{COWRIE_HOST}:{DIONAEA_HTTP_PORT}/", timeout=5
        ) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        assert "Directory listing" in body or resp.status == 200, (
            "Dionaea HTTP respondió pero sin el contenido esperado"
        )
    except OSError as e:
        pytest.fail(f"Dionaea HTTP acepta conexiones pero no sirve la respuesta esperada: {e}")


@pytest.mark.integration
def test_dionaea_smb_port_open():
    _requiere_sensor(COWRIE_HOST, DIONAEA_SMB_PORT, "Dionaea SMB")
    assert _tcp_open(COWRIE_HOST, DIONAEA_SMB_PORT)
