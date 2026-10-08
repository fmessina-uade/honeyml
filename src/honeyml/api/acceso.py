"""Quién entra al panel y qué puede hacer.

Los roles van en escalera y cada uno puede lo del anterior: el invitado mira y exporta, el analista
además deja veredictos, el admin además da de alta y de baja usuarios, y el superadmin además ve
la auditoría y la telemetría en vivo. Cada uno administra solo los roles que quedan por debajo
del suyo, así que el primer superadmin se crea por consola en el servidor y nunca desde la web.

La sesión es una cookie firmada con un secreto que se genera al arrancar la API: no hay ninguna
clave que guardar, y un reinicio cierra todas las sesiones. Cada pedido confirma contra el índice
que la cuenta siga activa y con el mismo sello, así una baja, un cambio de rol o de contraseña
cortan las sesiones abiertas sin esperar a que venzan.

El primer superadmin, adentro del contenedor de la API:
    python -m honeyml.api.acceso crear --usuario <nombre> --rol superadmin
"""

from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import hmac
import json
import re
import secrets
import sys
import threading
import time
import urllib.error
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, cast, get_args

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import almacen, auditoria, queries

Rol = Literal["invitado", "analista", "admin", "superadmin"]
ROLES: tuple[str, ...] = get_args(Rol)

USUARIOS = "honeyml-usuarios"
COOKIE = "honeyml_sesion"
DURACION_S = 8 * 60 * 60

_SECRETO = secrets.token_bytes(32)

# scrypt con 2^14 y bloques de 8 tarda unas decenas de milisegundos y pide 16 MB por intento: no se
# nota al ingresar, y encarece mucho probar un diccionario contra un volcado del índice.
_N, _R, _P = 2**14, 8, 1

NOMBRE_VALIDO = re.compile(r"^[a-z0-9][a-z0-9._-]{2,31}$")
MINIMO_CONTRASENA = 10

# Lo que se puede pedir sin sesión: el estado de la API, que no trae datos, y el ingreso mismo.
PUBLICAS = {("GET", "/api/health"), ("POST", "/api/sesion")}


def nivel(rol: str) -> int:
    return ROLES.index(rol)


def _b64(datos: bytes) -> str:
    return base64.urlsafe_b64encode(datos).rstrip(b"=").decode()


def _de_b64(texto: str) -> bytes:
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


def _ahora_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


# Contraseñas


def cifrar(contrasena: str) -> str:
    sal = secrets.token_bytes(16)
    clave = hashlib.scrypt(contrasena.encode(), salt=sal, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${_b64(sal)}${_b64(clave)}"


def coincide(contrasena: str, guardada: str) -> bool:
    try:
        _, n, r, p, sal, clave = guardada.split("$")
        esperada = _de_b64(clave)
        calculada = hashlib.scrypt(
            contrasena.encode(),
            salt=_de_b64(sal),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(esperada),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(calculada, esperada)


# Con un nombre que no es una cuenta igual se calcula un cifrado: así la demora de la respuesta no
# delata qué nombres existen.
_SENUELO = cifrar(secrets.token_hex(16))


# La sesión


def _firma(cuerpo: str) -> str:
    return _b64(hmac.new(_SECRETO, cuerpo.encode(), hashlib.sha256).digest())


def firmar(usuario: str, rol: str, sello: int, ahora: float | None = None) -> str:
    vence = int((time.time() if ahora is None else ahora) + DURACION_S)
    cuerpo = _b64(json.dumps({"u": usuario, "r": rol, "s": sello, "v": vence}).encode())
    return f"{cuerpo}.{_firma(cuerpo)}"


def leer(token: str, ahora: float | None = None) -> dict[str, Any] | None:
    """Lo que dice la cookie, o None si no la firmó esta API o ya venció."""
    cuerpo, _, firma = token.partition(".")
    if not firma or not hmac.compare_digest(firma, _firma(cuerpo)):
        return None
    try:
        datos: dict[str, Any] = json.loads(_de_b64(cuerpo))
    except ValueError:
        return None
    if datos.get("v", 0) < (time.time() if ahora is None else ahora):
        return None
    return datos


# Las cuentas

_VIGENCIA_S = 10.0
_cuentas: dict[str, tuple[float, dict[str, Any] | None]] = {}


def cuenta(nombre: str, es_url: str = queries.ES_URL) -> dict[str, Any] | None:
    """La cuenta como está en el índice. Se recuerda unos segundos: al abrir una sección el panel
    hace varios pedidos juntos, y leer la cuenta en cada uno no agrega nada."""
    ahora = time.monotonic()
    recordada = _cuentas.get(nombre)
    if recordada and ahora - recordada[0] < _VIGENCIA_S:
        return recordada[1]
    datos = almacen.documento(USUARIOS, nombre, es_url)
    _cuentas[nombre] = (ahora, datos)
    return datos


def _guardar(datos: dict[str, Any], es_url: str, nueva: bool = False) -> None:
    accion = "_create" if nueva else "_doc"
    ruta = almacen.ruta_doc(USUARIOS, datos["usuario"]).replace("/_doc/", f"/{accion}/")
    almacen.pedir("PUT", f"{ruta}?refresh=wait_for", datos, es_url)
    _cuentas.pop(datos["usuario"], None)


def publica(datos: dict[str, Any]) -> dict[str, Any]:
    """La cuenta sin lo que no tiene por qué salir de la API: el cifrado y el sello."""
    return {k: v for k, v in datos.items() if k not in ("contrasena", "sello")}


class Intentos:
    """Cinco fallas seguidas traban la cuenta cinco minutos. Va por nombre y no por dirección:
    detrás del túnel todos los pedidos llegan desde la misma."""

    def __init__(self, tope: int = 5, espera_s: float = 300.0) -> None:
        self.tope, self.espera_s = tope, espera_s
        self._fallas: dict[str, list[float]] = {}
        self._candado = threading.Lock()

    def espera(self, nombre: str, ahora: float | None = None) -> float:
        """Cuántos segundos faltan para poder volver a intentar, o cero."""
        ahora = time.monotonic() if ahora is None else ahora
        with self._candado:
            recientes = [t for t in self._fallas.get(nombre, []) if ahora - t < self.espera_s]
            if len(recientes) < self.tope:
                return 0.0
            return self.espera_s - (ahora - recientes[-self.tope])

    def fallo(self, nombre: str, ahora: float | None = None) -> None:
        ahora = time.monotonic() if ahora is None else ahora
        with self._candado:
            # sin el recorte, probar nombres al azar haría crecer esto sin límite
            if len(self._fallas) > 1000:
                self._fallas = {
                    n: ts for n, ts in self._fallas.items() if ahora - ts[-1] < self.espera_s
                }
            self._fallas.setdefault(nombre, []).append(ahora)

    def acierto(self, nombre: str) -> None:
        with self._candado:
            self._fallas.pop(nombre, None)


intentos = Intentos()


class IngresoRechazadoError(Exception):
    """Usuario o contraseña incorrectos, o la cuenta dada de baja. No se dice cuál de las tres."""


class CuentaTrabadaError(Exception):
    def __init__(self, segundos: float) -> None:
        super().__init__(f"Demasiados intentos. Probá de nuevo en {int(segundos) + 1} segundos.")
        self.segundos = segundos


class SinPermisoError(Exception):
    """Se quiso administrar una cuenta de un rol igual o superior al propio."""


class YaExisteError(Exception):
    pass


class NoExisteError(Exception):
    pass


def ingresar(nombre: str, contrasena: str, es_url: str = queries.ES_URL) -> dict[str, Any]:
    """Comprueba la contraseña y devuelve la cuenta. Cada intento queda en la auditoría."""
    nombre = nombre.strip().lower()
    espera = intentos.espera(nombre)
    if espera > 0:
        auditoria.registrar(nombre, None, "ingreso_trabado", es_url=es_url)
        raise CuentaTrabadaError(espera)

    datos = almacen.documento(USUARIOS, nombre, es_url)
    valida = coincide(contrasena, datos["contrasena"] if datos else _SENUELO)
    if not datos or not valida or not datos.get("activo"):
        intentos.fallo(nombre)
        auditoria.registrar(nombre, None, "ingreso_fallido", es_url=es_url)
        raise IngresoRechazadoError("Usuario o contraseña incorrectos.")

    intentos.acierto(nombre)
    datos["ultimo_ingreso"] = _ahora_iso()
    _guardar(datos, es_url)
    auditoria.registrar(nombre, datos["rol"], "ingreso", es_url=es_url)
    return datos


# Lo que llega del panel


def _nombre_valido(nombre: str) -> str:
    nombre = nombre.strip().lower()
    if not NOMBRE_VALIDO.match(nombre):
        raise ValueError(
            "el usuario va en minúsculas, de 3 a 32 caracteres: letras, números, punto, guion o "
            "guion bajo"
        )
    return nombre


def _contrasena_valida(contrasena: str) -> str:
    if len(contrasena) < MINIMO_CONTRASENA:
        raise ValueError(f"la contraseña necesita al menos {MINIMO_CONTRASENA} caracteres")
    return contrasena


class Ingreso(BaseModel):
    model_config = ConfigDict(extra="forbid")

    usuario: str = Field(max_length=64)
    contrasena: str = Field(max_length=256)


class Alta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    usuario: str
    rol: Rol
    contrasena: str = Field(max_length=256)

    _usuario = field_validator("usuario")(_nombre_valido)
    _contrasena = field_validator("contrasena")(_contrasena_valida)


class Cambio(BaseModel):
    """Lo que un admin cambia de otra cuenta. Lo que no viene, no se toca."""

    model_config = ConfigDict(extra="forbid")

    rol: Rol | None = None
    activo: bool | None = None
    contrasena: str | None = Field(default=None, max_length=256)

    @field_validator("contrasena")
    @classmethod
    def _nueva(cls, v: str | None) -> str | None:
        return None if v is None else _contrasena_valida(v)


class CambioPropio(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actual: str = Field(max_length=256)
    nueva: str = Field(max_length=256)

    _nueva = field_validator("nueva")(_contrasena_valida)


@dataclass(frozen=True)
class Sesion:
    usuario: str
    rol: str

    def puede(self, rol: str) -> bool:
        return nivel(self.rol) >= nivel(rol)

    def administra(self, rol: str) -> bool:
        return nivel(rol) < nivel(self.rol) and self.puede("admin")


# La administración de cuentas


def crear(alta: Alta, por: Sesion | None, es_url: str = queries.ES_URL) -> dict[str, Any]:
    """Da de alta una cuenta. Con `por` en None es la consola del servidor, que crea cualquiera."""
    if por is not None and not por.administra(alta.rol):
        raise SinPermisoError("Solo se dan de alta cuentas de un rol menor al propio.")
    datos = {
        "usuario": alta.usuario,
        "rol": alta.rol,
        "contrasena": cifrar(alta.contrasena),
        "activo": True,
        "sello": 1,
        "creada": _ahora_iso(),
        "creada_por": por.usuario if por else "consola",
    }
    try:
        _guardar(datos, es_url, nueva=True)
    except urllib.error.HTTPError as exc:
        if exc.code == almacen.YA_EXISTE:
            raise YaExisteError(f"Ya hay una cuenta {alta.usuario}.") from exc
        raise
    auditoria.registrar(
        por.usuario if por else "consola",
        por.rol if por else None,
        "cuenta_creada",
        objetivo=alta.usuario,
        detalle={"rol": alta.rol},
        es_url=es_url,
    )
    return publica(datos)


def modificar(
    nombre: str, cambio: Cambio, por: Sesion, es_url: str = queries.ES_URL
) -> dict[str, Any]:
    datos = almacen.documento(USUARIOS, nombre, es_url)
    if datos is None:
        raise NoExisteError(f"No hay una cuenta {nombre}.")
    # la propia se cambia por su ruta, que pide la contraseña actual
    if nombre == por.usuario or not por.administra(datos["rol"]):
        raise SinPermisoError("Solo se administran cuentas de un rol menor al propio.")
    if cambio.rol is not None and not por.administra(cambio.rol):
        raise SinPermisoError("No se puede dar un rol igual o mayor al propio.")

    hecho: dict[str, Any] = {}
    if cambio.rol is not None and cambio.rol != datos["rol"]:
        hecho["rol"] = {"antes": datos["rol"], "ahora": cambio.rol}
        datos["rol"] = cambio.rol
    if cambio.activo is not None and cambio.activo != datos.get("activo"):
        hecho["activo"] = cambio.activo
        datos["activo"] = cambio.activo
    if cambio.contrasena is not None:
        hecho["contrasena"] = "restablecida"
        datos["contrasena"] = cifrar(cambio.contrasena)
    if not hecho:
        return publica(datos)

    datos["sello"] = int(datos.get("sello", 0)) + 1
    datos["modificada"] = _ahora_iso()
    datos["modificada_por"] = por.usuario
    _guardar(datos, es_url)
    auditoria.registrar(
        por.usuario, por.rol, "cuenta_modificada", objetivo=nombre, detalle=hecho, es_url=es_url
    )
    return publica(datos)


def cambiar_propia(sesion: Sesion, cambio: CambioPropio, es_url: str = queries.ES_URL) -> int:
    """Cambia la contraseña propia y devuelve el sello nuevo, con el que se firma la sesión que
    sigue: las demás sesiones de la cuenta quedan cerradas."""
    datos = almacen.documento(USUARIOS, sesion.usuario, es_url)
    if datos is None or not coincide(cambio.actual, datos["contrasena"]):
        raise IngresoRechazadoError("La contraseña actual no es esa.")
    datos["contrasena"] = cifrar(cambio.nueva)
    datos["sello"] = int(datos.get("sello", 0)) + 1
    datos["modificada"] = _ahora_iso()
    _guardar(datos, es_url)
    auditoria.registrar(sesion.usuario, sesion.rol, "contrasena_cambiada", es_url=es_url)
    return int(datos["sello"])


def listar(por: Sesion, es_url: str = queries.ES_URL) -> list[dict[str, Any]]:
    r = almacen.buscar(
        USUARIOS, {"size": 500, "sort": [{"usuario": "asc"}], "query": {"match_all": {}}}, es_url
    )
    return [
        {**publica(h["_source"]), "administrable": por.administra(h["_source"]["rol"])}
        for h in r["hits"]["hits"]
        if h["_source"]["usuario"] != por.usuario
    ]


# Las dependencias de las rutas


def sesion_actual(request: Request) -> Sesion:
    datos = leer(request.cookies.get(COOKIE, ""))
    if datos is None:
        raise HTTPException(status_code=401, detail="Hace falta ingresar.")
    try:
        actual = cuenta(datos["u"])
    except urllib.error.HTTPError:
        raise
    except (urllib.error.URLError, ConnectionError, TimeoutError):
        # Sin el índice, la sesión ya abierta sigue con el rol con que se firmó, así el respaldo
        # congelado se sigue viendo. Ingresar de nuevo no se puede hasta que vuelva.
        return Sesion(datos["u"], datos["r"])
    if actual is None or not actual.get("activo") or actual.get("sello") != datos["s"]:
        raise HTTPException(status_code=401, detail="La sesión ya no vale. Volvé a ingresar.")
    return Sesion(actual["usuario"], actual["rol"])


def proteger(request: Request) -> None:
    """Va en toda la API: cualquier ruta nueva nace cerrada, salvo las públicas."""
    if (request.method, request.url.path) not in PUBLICAS:
        sesion_actual(request)


def exigir(rol: str) -> Callable[..., Sesion]:
    def dependencia(sesion: Sesion = Depends(sesion_actual)) -> Sesion:
        if not sesion.puede(rol):
            raise HTTPException(status_code=403, detail="Tu rol no tiene acceso a esto.")
        return sesion

    return dependencia


# La consola


def _pedir_contrasena() -> str:
    primera = getpass.getpass("Contraseña: ")
    if getpass.getpass("Repetila: ") != primera:
        sys.exit("No coinciden.")
    return primera


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cuentas del panel, desde el servidor.")
    sub = parser.add_subparsers(dest="orden", required=True)
    alta = sub.add_parser("crear", help="da de alta una cuenta de cualquier rol")
    alta.add_argument("--usuario", required=True)
    alta.add_argument("--rol", choices=ROLES, default="superadmin")
    nueva = sub.add_parser("restablecer", help="pone una contraseña nueva y cierra sus sesiones")
    nueva.add_argument("--usuario", required=True)
    args = parser.parse_args(argv)

    try:
        if args.orden == "crear":
            cuenta_nueva = Alta(
                usuario=args.usuario, rol=cast(Rol, args.rol), contrasena=_pedir_contrasena()
            )
            crear(cuenta_nueva, None)
            print(f"Cuenta {cuenta_nueva.usuario} creada con rol {cuenta_nueva.rol}.")
            return 0

        nombre = _nombre_valido(args.usuario)
        datos = almacen.documento(USUARIOS, nombre)
        if datos is None:
            sys.exit(f"No hay una cuenta {nombre}.")
        datos["contrasena"] = cifrar(_contrasena_valida(_pedir_contrasena()))
        datos["sello"] = int(datos.get("sello", 0)) + 1
        datos["activo"] = True
        datos["modificada"] = _ahora_iso()
        datos["modificada_por"] = "consola"
        _guardar(datos, queries.ES_URL)
        auditoria.registrar(
            "consola",
            None,
            "cuenta_modificada",
            objetivo=nombre,
            detalle={"contrasena": "restablecida"},
        )
        print(f"Contraseña de {nombre} restablecida.")
        return 0
    except (ValueError, YaExisteError) as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
