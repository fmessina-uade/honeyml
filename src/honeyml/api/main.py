"""Servicio FastAPI detrás del panel educativo.

Se pone entre el navegador y Elasticsearch para que la API de búsqueda nunca quede expuesta al
cliente, y además sirve las sesiones anotadas del replay. Corre al lado de Elasticsearch en la red
privada y se alcanza por el túnel SSH, nunca publicado.

Sobre la telemetría y las decisiones solo lee. Escribe tres cosas, cada una en su propio índice: el
veredicto del analista sobre una decisión del motor, común o a ciegas (`decisiones.py`), las cuentas
del panel (`acceso.py`) y la auditoría de lo que hace cada una (`auditoria.py`).

Toda ruta pide sesión salvo las de `acceso.PUBLICAS`, y cada una declara el rol mínimo que exige.

En desarrollo se levanta con `uvicorn honeyml.api.main:app --reload --port 8000`.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.error import HTTPError, URLError

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

from ..education import fingerprints, password_index
from ..features import arquetipos
from . import (
    acceso,
    auditoria,
    decisiones,
    exportar,
    offline,
    queries,
    registros,
    reporte,
    telemetria,
)
from .acceso import Sesion
from .privacidad import credenciales_de_sesiones, sin_contrasenas, sin_direcciones

REPLAY_FILE = Path("data/processed/replay_sessions.json")


def _live_or_frozen[T](fetch: Callable[[], T], key: str) -> T:
    """Corre la consulta en vivo y cae al respaldo congelado si no se alcanza a Elasticsearch.

    Solo caen al respaldo los errores de conexión. Una consulta mal armada es un error nuestro y
    tiene que aparecer como tal, no quedar tapada por datos viejos que justo estaban en disco.
    """
    try:
        return fetch()
    except (URLError, ConnectionError, TimeoutError) as exc:
        frozen = offline.load()
        if frozen is None or key not in frozen:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Elasticsearch no responde y no hay snapshot congelado. "
                    "Levantá el stack con 'make elastic-dev-up', o generá el snapshot "
                    "con 'make snapshot' mientras esté disponible."
                ),
            ) from exc
        value: T = frozen[key]
        return value


app = FastAPI(
    title="HoneyML API",
    description="Telemetría normalizada del honeypot para el panel educativo",
    version="0.1.0",
    dependencies=[Depends(acceso.proteger)],
)

# Durante el desarrollo el panel corre en el servidor de Vite, que reenvía /api: el navegador ve un
# solo origen y la cookie de sesión viaja sola. Esto cubre al panel abierto contra la API directa.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["*"],
    allow_credentials=True,
)

Invitado = Annotated[Sesion, Depends(acceso.exigir("invitado"))]
Analista = Annotated[Sesion, Depends(acceso.exigir("analista"))]
Admin = Annotated[Sesion, Depends(acceso.exigir("admin"))]
Superadmin = Annotated[Sesion, Depends(acceso.exigir("superadmin"))]


def _en_vivo[T](fetch: Callable[[], T]) -> T:
    """Para lo que no tiene respaldo congelado: las decisiones y las revisiones se leen en vivo.

    `HTTPError` va primero porque hereda de `URLError`: un pedido que Elasticsearch rechaza no es
    Elasticsearch caído, y decirlo así mandaría a buscar el problema en el lugar equivocado.
    """
    try:
        return fetch()
    except HTTPError as exc:
        raise HTTPException(
            status_code=502, detail=f"Elasticsearch rechazó la consulta ({exc.code})."
        ) from exc
    except (URLError, ConnectionError, TimeoutError) as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "Elasticsearch no responde. Las decisiones del motor se leen solo en vivo: el "
                "respaldo congelado no las guarda."
            ),
        ) from exc


def _tapar_si_invitado[T](sesion: Sesion, datos: T) -> T:
    """El invitado ve las decisiones sin ninguna dirección y sin las contraseñas de los eventos:
    está para mirar el panel en una demostración, y no necesita ni lo uno ni lo otro. Desde el
    analista para arriba se ven, porque revisar una clasificación pide el evento como llegó."""
    tapados: T = sin_contrasenas(sin_direcciones(datos)) if not sesion.puede("analista") else datos
    return tapados


@app.get("/api/health")
def health() -> dict[str, Any]:
    """Informa si lo que se está sirviendo es en vivo o sale del respaldo congelado."""
    try:
        queries.overview()
        return {"status": "ok", "mode": "live"}
    except (URLError, ConnectionError, TimeoutError):
        frozen = offline.load()
        if frozen is None:
            return {"status": "down", "mode": "none"}
        return {
            "status": "ok",
            "mode": "snapshot",
            "generated_at": frozen.get("generated_at", ""),
        }


@app.get("/api/overview")
def get_overview() -> dict[str, Any]:
    """Headline counters."""
    return _live_or_frozen(queries.overview, "overview")


@app.get("/api/timeline")
def get_timeline(
    interval: str = "day",
    sensor: str | None = None,
    desde: str | None = None,
    hasta: str | None = None,
) -> list[dict[str, Any]]:
    """Eventos en el tiempo, con filtro opcional por sensor y por rango de fechas.

    Con Elasticsearch abajo, el respaldo contesta lo que puede calcular desde sus cubos diarios (un
    rango, un sensor, un agrupado semanal) y rechaza la vista por hora, cuyos cubos nunca guardó.
    El rechazo es un 503 con el motivo adentro y no una traza: el panel muestra ese motivo, así un
    filtro que no se puede cumplir lo dice, en vez de dejar el gráfico sin filtrar en pantalla.
    """
    filtrado = bool(sensor or desde or hasta) or interval != "day"
    if not filtrado:
        return _live_or_frozen(queries.timeline, "timeline")

    try:
        return queries.timeline(interval=interval, sensor=sensor, desde=desde, hasta=hasta)
    except (URLError, ConnectionError, TimeoutError) as exc:
        congelado = offline.timeline(interval=interval, sensor=sensor, desde=desde, hasta=hasta)
        if congelado is not None:
            return congelado
        raise HTTPException(
            status_code=503,
            detail=(
                "La vista por hora necesita Elasticsearch: el respaldo congelado guarda un punto "
                "por día y esas horas nunca se almacenaron. Las vistas por día y por semana sí "
                "funcionan sobre el respaldo."
            ),
        ) from exc


# El ranking más largo que se entrega. Cualquier sesión puede pedirlo, invitados incluidos, y cada
# puesto pedido le cuesta a Elasticsearch cubos en todos los índices diarios: sin tope, un solo
# pedido grande alcanza para cargarlo. El panel pide pocos.
RANKING_MAXIMO = 50


@app.get("/api/credentials")
def get_credentials(
    size: int = Query(10, ge=1, le=RANKING_MAXIMO),
) -> dict[str, list[dict[str, Any]]]:
    """Los usuarios y contraseñas más intentados."""
    return _live_or_frozen(lambda: queries.top_credentials(size=size), "credentials")


@app.get("/api/commands")
def get_commands(size: int = Query(12, ge=1, le=RANKING_MAXIMO)) -> list[dict[str, Any]]:
    """Los comandos más ejecutados."""
    return _live_or_frozen(lambda: queries.top_commands(size=size), "commands")


@app.get("/api/protocol-detail")
def get_protocol_detail() -> list[dict[str, Any]]:
    """Tráfico por protocolo en el sensor multiprotocolo, con direcciones distintas."""
    return _live_or_frozen(queries.protocol_detail, "protocol_detail")


@app.get("/api/protocols")
def get_protocols() -> list[dict[str, Any]]:
    """Superficie de ataque por protocolo."""
    return _live_or_frozen(queries.protocols, "protocols")


@app.get("/api/stages")
def get_stages() -> list[dict[str, Any]]:
    """Eventos por etapa de la intrusión."""
    return _live_or_frozen(queries.attack_stages, "stages")


@app.get("/api/hourly")
def get_hourly() -> list[dict[str, Any]]:
    """Ataques por hora del día: muestra que no hay ritmo humano detrás."""
    return _live_or_frozen(queries.hourly, "hourly")


# El panel vuelve a pedir el snapshot cada minuto para mostrar lo que llega, y en una demostración
# puede haber varios teléfonos abiertos a la vez. La consulta recorre el corpus entero, así que
# dentro de esta ventana todos reciben la misma respuesta.
SNAPSHOT_VIGENCIA_S = 30.0
_snapshot: dict[str, Any] = {"momento": 0.0, "datos": None}
_snapshot_candado = threading.Lock()


def _snapshot_reciente() -> dict[str, Any]:
    with _snapshot_candado:
        if (
            _snapshot["datos"] is None
            or time.monotonic() - _snapshot["momento"] > SNAPSHOT_VIGENCIA_S
        ):
            _snapshot["datos"] = queries.snapshot()
            _snapshot["momento"] = time.monotonic()
        datos: dict[str, Any] = _snapshot["datos"]
        return datos


@app.get("/api/snapshot")
def get_snapshot() -> dict[str, Any]:
    """Todo junto: un solo viaje para la carga del panel y para cada refresco."""
    try:
        return _snapshot_reciente()
    except (URLError, ConnectionError, TimeoutError) as exc:
        frozen = offline.load()
        if frozen is None:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Elasticsearch no responde y no hay snapshot congelado. "
                    "Levantá el stack con 'make elastic-dev-up', o generá el snapshot "
                    "con 'make snapshot' mientras esté disponible."
                ),
            ) from exc
        return frozen


@app.get("/api/weekly-rhythm")
def get_weekly_rhythm() -> dict[str, Any]:
    """Eventos por día de la semana y hora: si hay algún ritmo humano, acá se vería."""
    return _live_or_frozen(queries.weekly_rhythm, "weekly_rhythm")


@app.get("/api/geography")
def get_geography() -> dict[str, Any]:
    """Origen de los ataques por país y por sistema autónomo."""
    return _live_or_frozen(queries.geography, "geography")


@app.get("/api/archetypes")
def get_archetypes() -> dict[str, Any]:
    """Grupos de conducta de las direcciones observadas.

    Sale del archivo precalculado y no de una consulta en vivo: el agrupamiento corre sobre toda la
    tabla de características y tarda segundos, que está bien como paso por lotes y no en una carga
    de página.
    """
    data = arquetipos.load()
    if data is None:
        raise HTTPException(
            status_code=503,
            detail="Faltan los arquetipos. Generalos con: make arquetipos",
        )
    return data


@app.get("/api/fingerprints")
def get_fingerprints() -> dict[str, Any]:
    """Familias de sesiones que corren una secuencia de comandos idéntica byte a byte."""
    data = fingerprints.load()
    if data is None:
        raise HTTPException(
            status_code=503,
            detail="Faltan las familias. Generalas con: make fingerprints",
        )
    return data


@app.get("/api/password-check/resumen")
def password_summary() -> dict[str, int]:
    """Cuántas contraseñas distintas y cuántos intentos tiene el índice, sin ningún hash.

    El panel lo usa para decir contra cuántas se compara antes de que nadie pregunte nada, y así
    el número sale del índice vigente y no de un texto escrito a mano.
    """
    index = password_index.load()
    if index is None:
        raise HTTPException(
            status_code=503,
            detail="Falta el índice de contraseñas. Generalo con: make passwords",
        )
    return {"distintas": int(index.get("distinct", 0)), "intentos": int(index.get("attempts", 0))}


@app.get("/api/password-check")
def check_password(prefix: str) -> dict[str, Any]:
    """Consulta con k-anonimato: recibe un prefijo de hash, nunca una contraseña.

    En honeyml/education/password_index está el porqué de partir así la comparación.
    """
    if not prefix or len(prefix) > 8 or not all(c in "0123456789abcdefABCDEF" for c in prefix):
        raise HTTPException(status_code=400, detail="Prefijo inválido.")
    index = password_index.load()
    if index is None:
        raise HTTPException(
            status_code=503,
            detail="Falta el índice de contraseñas. Generalo con: make passwords",
        )
    return password_index.lookup(prefix, index)


@app.get("/api/replays")
def get_replays() -> list[dict[str, Any]]:
    """Sesiones de ataque anotadas, para el replay paso a paso."""
    if not REPLAY_FILE.exists():
        raise HTTPException(
            status_code=503,
            detail="Faltan las sesiones. Generalas con: python -m honeyml.education.session_replay",
        )
    data: list[dict[str, Any]] = json.loads(REPLAY_FILE.read_text(encoding="utf-8"))
    credenciales = [s["credentials"] for s in data if s.get("credentials")]
    usuarios = sorted({c["user"] for c in credenciales if c.get("user")})
    contrasenas = sorted({c["password"] for c in credenciales if c.get("password")})
    try:
        aceptados, aceptadas = queries.credenciales_probadas(usuarios, contrasenas)
    except (URLError, ConnectionError, TimeoutError):
        # Sin el índice no se puede saber cuántos probaron cada una, y ante la duda se tapan todas.
        aceptados, aceptadas = set(), set()
    return credenciales_de_sesiones(data, aceptados, aceptadas)


@app.get("/api/decisiones/resumen")
def get_resumen_de_decisiones() -> dict[str, Any]:
    """Cuánto decidió el motor, cómo, a qué costo, en cuánto tiempo y qué espera revisión."""
    return _en_vivo(decisiones.resumen)


@app.get("/api/decisiones")
def get_decisiones(
    sesion: Invitado,
    severidad: str | None = None,
    tactica: str | None = None,
    sensor: str | None = None,
    estado: Literal["todas", "pendientes", "revisadas"] = "todas",
    desde: int = 0,
    tamano: int = 25,
    orden: Literal["evento", "decision"] = "evento",
    razonadas: bool = False,
) -> dict[str, Any]:
    """Las decisiones del motor, filtradas y de a páginas. `tactica=ninguna` trae las que no
    tienen, `orden=decision` las ordena por cuándo decidió el motor, para seguirlo en vivo, y
    `razonadas` deja solo las que pasaron por el modelo."""
    return _tapar_si_invitado(
        sesion,
        _en_vivo(
            lambda: decisiones.listar(
                severidad=severidad,
                tactica=tactica,
                sensor=sensor,
                estado=estado,
                desde=desde,
                tamano=tamano,
                orden=orden,
                razonadas=razonadas,
            )
        ),
    )


@app.get("/api/decisiones/a-ciegas/siguiente")
def get_siguiente_a_ciegas(sesion: Analista) -> dict[str, Any]:
    """La próxima conducta de la muestra para revisar a ciegas, sin la clasificación del motor."""
    try:
        return _en_vivo(decisiones.siguiente_a_ciegas)
    except decisiones.SinMuestraError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/decisiones/{doc_id}")
def get_decision(doc_id: str, sesion: Invitado) -> dict[str, Any]:
    """Una decisión con su evento y el veredicto del analista, si lo hay."""
    encontrada = _en_vivo(lambda: decisiones.detalle(doc_id))
    if encontrada is None:
        raise HTTPException(status_code=404, detail="Ese evento no tiene decisión del motor.")
    return _tapar_si_invitado(sesion, encontrada)


@app.put("/api/decisiones/{doc_id}/revision")
def put_revision(doc_id: str, veredicto: decisiones.Veredicto, sesion: Analista) -> dict[str, Any]:
    """El veredicto del analista, firmado con su cuenta y anotado en la auditoría."""
    try:
        guardada = _en_vivo(lambda: decisiones.revisar(doc_id, veredicto, usuario=sesion.usuario))
    except decisiones.SinClasificacionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except decisiones.RevisadaACiegasError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if guardada is None:
        raise HTTPException(status_code=404, detail="Ese evento no tiene decisión del motor.")
    auditoria.registrar(
        sesion.usuario,
        sesion.rol,
        "veredicto",
        objetivo=doc_id,
        detalle={"veredicto": guardada["veredicto"]},
    )
    return guardada


@app.put("/api/decisiones/{doc_id}/revision-a-ciegas")
def put_revision_a_ciegas(
    doc_id: str, clasificacion: decisiones.ClasificacionACiegas, sesion: Analista
) -> dict[str, Any]:
    """La clasificación elegida a ciegas; la respuesta trae la del motor para mostrarla después."""
    try:
        guardada = _en_vivo(
            lambda: decisiones.revisar_a_ciegas(doc_id, clasificacion, usuario=sesion.usuario)
        )
    except decisiones.RevisadaACiegasError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if guardada is None:
        raise HTTPException(status_code=404, detail="Ese evento no tiene decisión del motor.")
    auditoria.registrar(
        sesion.usuario,
        sesion.rol,
        "revision_a_ciegas",
        objetivo=doc_id,
        detalle={"veredicto": guardada["veredicto"]},
    )
    return guardada


# La sesión


def _abrir_sesion(respuesta: Response, cuenta: dict[str, Any]) -> dict[str, Any]:
    # Sin `secure`: en la demostración el panel se sirve por HTTP en la red local. Lo que la cubre
    # es que la red es propia y con clave; `samesite=strict` corta que otro sitio la use.
    respuesta.set_cookie(
        acceso.COOKIE,
        acceso.firmar(cuenta["usuario"], cuenta["rol"], int(cuenta["sello"])),
        max_age=acceso.DURACION_S,
        httponly=True,
        samesite="strict",
        path="/api",
    )
    return {"usuario": cuenta["usuario"], "rol": cuenta["rol"]}


@app.post("/api/sesion")
def post_sesion(ingreso: acceso.Ingreso, respuesta: Response) -> dict[str, Any]:
    """El ingreso. La respuesta no dice si falló el usuario o la contraseña."""
    try:
        cuenta = _en_vivo(lambda: acceso.ingresar(ingreso.usuario, ingreso.contrasena))
    except acceso.CuentaTrabadaError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except acceso.IngresoRechazadoError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return _abrir_sesion(respuesta, cuenta)


@app.get("/api/sesion")
def get_sesion(sesion: Invitado) -> dict[str, Any]:
    """Quién está adentro: el panel lo pregunta al abrir para saber si mostrar el ingreso."""
    return {"usuario": sesion.usuario, "rol": sesion.rol}


@app.delete("/api/sesion")
def delete_sesion(respuesta: Response, sesion: Invitado) -> dict[str, bool]:
    _en_vivo(lambda: acceso.cerrar(sesion))
    respuesta.delete_cookie(acceso.COOKIE, path="/api")
    return {"ok": True}


@app.put("/api/sesion/contrasena")
def put_contrasena(
    cambio: acceso.CambioPropio, respuesta: Response, sesion: Invitado
) -> dict[str, Any]:
    """Cambia la contraseña propia. Las demás sesiones de la cuenta quedan cerradas y esta sigue."""
    try:
        sello = _en_vivo(lambda: acceso.cambiar_propia(sesion, cambio))
    except acceso.IngresoRechazadoError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _abrir_sesion(respuesta, {"usuario": sesion.usuario, "rol": sesion.rol, "sello": sello})


# Las cuentas


@app.get("/api/usuarios")
def get_usuarios(sesion: Admin) -> list[dict[str, Any]]:
    """Las demás cuentas, cada una con si quien pregunta la puede administrar."""
    return _en_vivo(lambda: acceso.listar(sesion))


@app.post("/api/usuarios", status_code=201)
def post_usuario(alta: acceso.Alta, sesion: Admin) -> dict[str, Any]:
    try:
        return _en_vivo(lambda: acceso.crear(alta, sesion))
    except acceso.SinPermisoError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except acceso.YaExisteError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.patch("/api/usuarios/{nombre}")
def patch_usuario(nombre: str, cambio: acceso.Cambio, sesion: Admin) -> dict[str, Any]:
    try:
        return _en_vivo(lambda: acceso.modificar(nombre, cambio, sesion))
    except acceso.SinPermisoError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except acceso.NoExisteError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# La auditoría y la telemetría en vivo


@app.get("/api/auditoria")
def get_auditoria(
    sesion: Superadmin,
    desde: int = 0,
    tamano: int = 50,
    accion: str | None = None,
    usuario: str | None = None,
) -> dict[str, Any]:
    """Lo que hizo cada cuenta en el panel, de lo más nuevo a lo más viejo."""
    return _en_vivo(
        lambda: auditoria.listar(desde=desde, tamano=tamano, accion=accion, usuario=usuario)
    )


@app.get("/api/auditoria/servidor")
def get_registros_del_servidor(sesion: Superadmin, cuantas: int = 150) -> dict[str, Any]:
    """Los despliegues, el vigilante, la salud y el respaldo, como los escribe el servidor."""
    return registros.ultimas(cuantas=min(max(cuantas, 1), 500))


@app.get("/api/telemetria/en-vivo")
def get_telemetria(
    sesion: Superadmin, despues: str | None = None, tamano: int = 40
) -> dict[str, Any]:
    """Los eventos normalizados a medida que llegan, sin direcciones."""
    return _en_vivo(lambda: telemetria.en_vivo(despues=despues, tamano=tamano))


# Los reportes


def _adjunto(contenido: str, nombre: str, extra: dict[str, str] | None = None) -> Response:
    sello = datetime.now(UTC).strftime("%Y%m%d-%H%M")
    return Response(
        content=contenido.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="honeyml-{nombre}-{sello}.csv"'}
        | (extra or {}),
    )


def _rango(desde: str | None, hasta: str | None) -> tuple[str | None, str | None]:
    try:
        return reporte.validar(desde, hasta)
    except reporte.RangoInvalidoError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/exportar/decisiones.csv")
def get_exportar_decisiones(
    sesion: Invitado,
    severidad: str | None = None,
    tactica: str | None = None,
    sensor: str | None = None,
    estado: Literal["todas", "pendientes", "revisadas"] = "todas",
    desde: str | None = None,
    hasta: str | None = None,
) -> Response:
    """Las decisiones del filtro, hasta diez mil. `X-Total` dice cuántas había en el filtro. El
    rango es sobre el momento del evento, el mismo del reporte general."""
    desde, hasta = _rango(desde, hasta)
    datos = _en_vivo(
        lambda: decisiones.para_exportar(
            severidad=severidad,
            tactica=tactica,
            sensor=sensor,
            estado=estado,
            desde=f"{desde}T00:00:00Z" if desde else None,
            hasta=f"{hasta}T23:59:59.999Z" if hasta else None,
        )
    )
    pedido = {
        "severidad": severidad,
        "tactica": tactica,
        "sensor": sensor,
        "desde": desde,
        "hasta": hasta,
        "estado": estado,
    }
    detalle = {k: v for k, v in pedido.items() if v} | {"filas": len(datos["items"])}
    auditoria.registrar(
        sesion.usuario, sesion.rol, "exportacion", objetivo="decisiones", detalle=detalle
    )
    return _adjunto(
        exportar.decisiones_csv(datos["items"]),
        "decisiones",
        {"X-Total": str(datos["total"]), "Access-Control-Expose-Headers": "X-Total"},
    )


@app.get("/api/exportar/revisiones.csv")
def get_exportar_revisiones(sesion: Invitado) -> Response:
    """Todos los veredictos del analista, comunes y a ciegas, con lo que había dicho el motor."""
    filas = _en_vivo(decisiones.revisiones)
    auditoria.registrar(
        sesion.usuario,
        sesion.rol,
        "exportacion",
        objetivo="revisiones",
        detalle={"filas": len(filas)},
    )
    return _adjunto(exportar.revisiones_csv(filas), "revisiones")


@app.get("/api/reporte")
def get_reporte(
    sesion: Invitado, desde: str | None = None, hasta: str | None = None
) -> dict[str, Any]:
    """Todo lo que lleva el reporte general para un rango de fechas, sin direcciones."""
    desde, hasta = _rango(desde, hasta)
    return _en_vivo(lambda: reporte.general(desde, hasta))


class AvisoDeReporte(BaseModel):
    model_config = ConfigDict(extra="forbid")

    formato: Literal["pdf", "csv"]
    conjunto: str | None = Field(default=None, max_length=40)
    desde: str | None = Field(default=None, max_length=10)
    hasta: str | None = Field(default=None, max_length=10)


@app.post("/api/reporte")
def post_reporte(aviso: AvisoDeReporte, sesion: Invitado) -> dict[str, bool]:
    """La versión impresa y los CSV los arma el navegador con lo que devolvió `get_reporte`;
    esto solo deja anotado en la auditoría qué se llevó y de qué rango."""
    auditoria.registrar(
        sesion.usuario,
        sesion.rol,
        "exportacion",
        objetivo=aviso.conjunto or "reporte",
        detalle=aviso.model_dump(exclude_none=True),
    )
    return {"ok": True}


# Cuándo se calculó cada artefacto

ARTEFACTOS = {
    "huellas": Path("data/processed/fingerprints.json"),
    "arquetipos": Path("data/processed/arquetipos.json"),
    "sesiones": REPLAY_FILE,
    "contrasenas": Path("data/processed/password_index.json"),
}


@app.get("/api/artefactos")
def get_artefactos() -> dict[str, str | None]:
    """El momento en que se generó cada artefacto por lotes. Esas secciones no son en vivo, y el
    panel lo dice con esta fecha. Es la del archivo: la publicación la conserva al copiarlo."""
    return {
        nombre: (
            datetime.fromtimestamp(ruta.stat().st_mtime, UTC).isoformat(timespec="seconds")
            if ruta.exists()
            else None
        )
        for nombre, ruta in ARTEFACTOS.items()
    }
