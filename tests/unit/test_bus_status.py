"""El chequeo del bus se presenta con la clave solo cuando la hay, y antes de cualquier pedido."""

from __future__ import annotations

import importlib.util
import io
from pathlib import Path
from types import ModuleType

import pytest


def _cargar() -> ModuleType:
    # `scripts/` no es un paquete: el módulo se carga desde su archivo.
    ruta = Path(__file__).resolve().parents[2] / "scripts" / "bus_status.py"
    spec = importlib.util.spec_from_file_location("bus_status", ruta)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


bus_status = _cargar()


class _SocketFalso:
    def __init__(self) -> None:
        self.enviado = b""

    def sendall(self, datos: bytes) -> None:
        self.enviado += datos


def test_sin_clave_no_manda_nada() -> None:
    sock = _SocketFalso()
    bus_status.autenticar(io.BytesIO(b""), sock, None)
    assert sock.enviado == b""


def test_con_clave_manda_auth_en_el_protocolo_del_bus() -> None:
    sock = _SocketFalso()
    bus_status.autenticar(io.BytesIO(b"+OK\r\n"), sock, "clave")
    assert sock.enviado == b"*2\r\n$4\r\nAUTH\r\n$5\r\nclave\r\n"


def test_una_clave_rechazada_levanta() -> None:
    respuesta = io.BytesIO(b"-WRONGPASS invalid username-password pair\r\n")
    with pytest.raises(bus_status.BusError, match="WRONGPASS"):
        bus_status.autenticar(respuesta, _SocketFalso(), "equivocada")


def test_la_clave_sale_del_entorno(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUS_PASSWORD", "del-entorno")
    assert _cargar().PASSWORD == "del-entorno"
    monkeypatch.setenv("BUS_PASSWORD", "")
    assert _cargar().PASSWORD is None
