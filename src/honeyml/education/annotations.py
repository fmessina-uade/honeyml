"""Knowledge base that turns a raw attacker command into something a reader learns from.

Each entry explains what the command does, why an attacker runs it, and which MITRE ATT&CK
tactic it maps to. This is the layer that makes the dashboard educational rather than analytical:
the data alone shows *what* happened, these annotations explain *why it matters*.

Text is in Spanish because it is user-facing content for the dashboard and the thesis.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Annotation:
    """What a reader should understand when they see this command."""

    what: str  # what the command does, in plain language
    why: str  # why an attacker runs it at this point of the intrusion
    tactic: str  # MITRE ATT&CK tactic
    technique: str  # MITRE ATT&CK technique id, empty when it doesn't map cleanly


# Ordered: the first pattern that matches wins, so put the specific ones first.
RULES: list[tuple[re.Pattern[str], Annotation]] = [
    (
        re.compile(r"\buname\b", re.I),
        Annotation(
            what="Consulta el nombre y la versión del núcleo del sistema.",
            why="Identifica el sistema operativo para elegir un exploit compatible. Es casi "
            "siempre el primer comando: antes de atacar hay que saber dónde se está parado.",
            tactic="Descubrimiento",
            technique="T1082",
        ),
    ),
    (
        re.compile(r"/proc/cpuinfo|\bnproc\b|/proc/meminfo|\bfree\b", re.I),
        Annotation(
            what="Lee las características del procesador y la memoria disponible.",
            why="Mide la capacidad de cómputo del equipo. Es el reconocimiento típico previo a "
            "instalar un minero de criptomonedas: cuanto más potente, más rentable.",
            tactic="Descubrimiento",
            technique="T1082",
        ),
    ),
    (
        re.compile(r"\bbusybox\b", re.I),
        Annotation(
            what="Invoca BusyBox, el conjunto de utilidades mínimo de los sistemas embebidos.",
            why="Señal característica de las botnets de la familia Mirai: usan su presencia para "
            "confirmar que es un dispositivo de internet de las cosas y no una trampa.",
            tactic="Descubrimiento",
            technique="T1082",
        ),
    ),
    (
        re.compile(r"\b(wget|curl|tftp)\b", re.I),
        Annotation(
            what="Descarga un archivo desde un servidor remoto.",
            why="Trae la carga maliciosa al equipo comprometido. Es el momento en que la "
            "intrusión deja de ser exploratoria y pasa a instalar software.",
            tactic="Ejecución",
            technique="T1105",
        ),
    ),
    (
        re.compile(r"\bchmod\b", re.I),
        Annotation(
            what="Cambia los permisos de un archivo, normalmente para hacerlo ejecutable.",
            why="Paso obligado después de descargar la carga: sin permiso de ejecución el "
            "archivo descargado es inofensivo.",
            tactic="Ejecución",
            technique="T1222",
        ),
    ),
    (
        re.compile(r"WRITABLE|\.testfile", re.I),
        Annotation(
            what="Escribe un archivo de prueba y verifica que haya quedado creado.",
            why="Comprueba en qué directorios puede escribir. Necesita un lugar donde dejar la "
            "carga maliciosa, y no todos los directorios se lo permiten.",
            tactic="Descubrimiento",
            technique="T1083",
        ),
    ),
    (
        re.compile(r"/proc/\[?[0-9]", re.I),
        Annotation(
            what="Recorre los procesos en ejecución del sistema.",
            why="Busca competencia: otros programas maliciosos ya instalados, o herramientas de "
            "seguridad que puedan delatarlo. Varias botnets eliminan a sus rivales.",
            tactic="Descubrimiento",
            technique="T1057",
        ),
    ),
    (
        re.compile(r"\b(whoami|\bid\b|groups)\b", re.I),
        Annotation(
            what="Muestra con qué usuario y permisos se está ejecutando la sesión.",
            why="Determina si ya tiene privilegios de administrador o si necesita escalarlos "
            "antes de continuar.",
            tactic="Descubrimiento",
            technique="T1033",
        ),
    ),
    (
        re.compile(r"\bcrontab\b|/etc/cron|rc\.local|systemctl\s+enable", re.I),
        Annotation(
            what="Manipula las tareas programadas o los servicios de arranque.",
            why="Busca sobrevivir al reinicio del equipo. Sin esto, apagar la máquina elimina al "
            "intruso; con esto, vuelve solo.",
            tactic="Persistencia",
            technique="T1053",
        ),
    ),
    (
        re.compile(r"authorized_keys|\.ssh/|ssh-rsa", re.I),
        Annotation(
            what="Manipula las claves de acceso por SSH del usuario.",
            why="Instala una llave propia para volver a entrar aunque se cambie la contraseña. "
            "Es una de las formas de persistencia más silenciosas.",
            tactic="Persistencia",
            technique="T1098",
        ),
    ),
    (
        re.compile(r"\brm\s+-[rf]|history\s+-c|>\s*/dev/null.*history|shred\b", re.I),
        Annotation(
            what="Borra archivos o limpia el historial de comandos.",
            why="Elimina rastros de la intrusión para dificultar el análisis forense posterior.",
            tactic="Evasión de defensas",
            technique="T1070",
        ),
    ),
    (
        re.compile(r"\b(passwd|useradd|adduser|usermod)\b", re.I),
        Annotation(
            what="Modifica contraseñas o cuentas de usuario del sistema.",
            why="Crea una cuenta propia o cambia la del administrador para bloquear al dueño "
            "legítimo y asegurarse el acceso.",
            tactic="Persistencia",
            technique="T1136",
        ),
    ),
    (
        re.compile(r"^\s*(cd|ls|pwd|cat|echo)\b", re.I),
        Annotation(
            what="Navega por el sistema de archivos o inspecciona su contenido.",
            why="Reconocimiento básico del entorno: ubicarse, ver qué hay y dónde dejar la carga.",
            tactic="Descubrimiento",
            technique="T1083",
        ),
    ),
]

FALLBACK = Annotation(
    what="Comando ejecutado por el atacante durante la sesión.",
    why="Forma parte de la secuencia de reconocimiento posterior al acceso.",
    tactic="Descubrimiento",
    technique="",
)


def annotate(command: str) -> Annotation:
    """Return the annotation for a command; falls back to a generic one when nothing matches."""
    for pattern, annotation in RULES:
        if pattern.search(command):
            return annotation
    return FALLBACK
