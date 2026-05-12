"""
Tests de integración (smoke tests) para el stack de honeypots.

Requieren que los contenedores estén corriendo (make dev-up).
Ejecutar con: pytest tests/integration/ -v -m integration

Marcados con @pytest.mark.integration para poder saltearse en CI
sin Docker (pytest tests/unit/ -v).
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


@pytest.mark.integration
def test_cowrie_ssh_port_open():
    assert _tcp_open(COWRIE_HOST, COWRIE_SSH_PORT), (
        f"Cowrie SSH no responde en {COWRIE_HOST}:{COWRIE_SSH_PORT}. "
        "¿Está corriendo? Ejecutar: make dev-up"
    )


@pytest.mark.integration
def test_cowrie_telnet_port_open():
    assert _tcp_open(COWRIE_HOST, COWRIE_TELNET_PORT), (
        f"Cowrie Telnet no responde en {COWRIE_HOST}:{COWRIE_TELNET_PORT}"
    )


@pytest.mark.integration
def test_dionaea_http_responds():
    try:
        with urllib.request.urlopen(
            f"http://{COWRIE_HOST}:{DIONAEA_HTTP_PORT}/", timeout=5
        ) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        assert "Directory listing" in body or resp.status == 200, (
            "Dionaea HTTP respondió pero sin el contenido esperado"
        )
    except OSError as e:
        pytest.fail(
            f"Dionaea HTTP no responde en {COWRIE_HOST}:{DIONAEA_HTTP_PORT}: {e}. "
            "¿Está corriendo? Ejecutar: make dev-up"
        )


@pytest.mark.integration
def test_dionaea_smb_port_open():
    assert _tcp_open(COWRIE_HOST, DIONAEA_SMB_PORT), (
        f"Dionaea SMB no responde en {COWRIE_HOST}:{DIONAEA_SMB_PORT}"
    )
