"""Base de conocimiento que convierte un comando crudo del atacante en algo de lo que se aprende.

Cada entrada explica qué hace el comando, por qué lo corre un atacante y a qué táctica de MITRE
ATT&CK corresponde. Es la capa que hace que el panel sea educativo y no analítico: los datos solos
muestran qué pasó, estas anotaciones explican por qué importa.

Cada entrada viene en español y en inglés porque el panel tiene selector de idioma, y dejar las
explicaciones del replay sin traducir rompería su sección más distintiva.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Annotation:
    """Lo que quien lee tiene que entender cuando ve este comando."""

    what: str  # qué hace el comando, en palabras simples
    why: str  # por qué lo corre un atacante en este punto de la intrusión
    tactic: str  # táctica de MITRE ATT&CK
    technique: str  # id de técnica MITRE ATT&CK; vacío cuando no mapea limpio
    what_en: str = ""  # lo mismo, en inglés
    why_en: str = ""


# Las tácticas que este señuelo puede observar, y por lo tanto las únicas que el motor de triaje
# tiene permitido asignar. Están acá porque acá se asignan por comando, y el nodo de validación las
# importa en vez de escribir una segunda copia que se desincronice.
#
# Las otras tres del panel (acceso a credenciales, movimiento lateral, impacto) quedan afuera a
# propósito: la sección MITRE las muestra en gris justamente para explicar que un señuelo de baja
# interacción no las ve. Si el motor pudiera asignarlas, esa explicación dejaría de ser cierta.
TACTICAS_OBSERVABLES = (
    "Descubrimiento",
    "Ejecución",
    "Evasión de defensas",
    "Persistencia",
)


# El orden importa: gana el primer patrón que coincide, así que los específicos van arriba.
RULES: list[tuple[re.Pattern[str], Annotation]] = [
    (
        re.compile(r"\buname\b", re.I),
        Annotation(
            what="Consulta el nombre y la versión del núcleo del sistema.",
            why="Identifica el sistema operativo para elegir un exploit compatible. Es casi "
            "siempre el primer comando: antes de atacar hay que saber dónde se está parado.",
            what_en="Queries the system's kernel name and version.",
            why_en=(
                "Identifies the operating system in order to pick a compatible exploit. It is "
                "almost always the first command: before attacking you need to know where you are "
                "standing."
            ),
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
            what_en="Reads the processor's characteristics and the available memory.",
            why_en=(
                "Measures the machine's compute capacity. This is the reconnaissance typically "
                "done before installing a cryptocurrency miner: the more powerful, the more "
                "profitable."
            ),
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
            what_en="Invokes BusyBox, the minimal utility set of embedded systems.",
            why_en=(
                "A signature move of the Mirai family of botnets: they use its presence to "
                "confirm this is an internet-of-things device and not a trap."
            ),
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
            what_en="Downloads a file from a remote server.",
            why_en=(
                "Brings the malicious payload onto the compromised machine. This is the moment "
                "the intrusion stops being exploratory and starts installing software."
            ),
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
            what_en="Changes a file's permissions, normally to make it executable.",
            why_en=(
                "A mandatory step after downloading the payload: without execute permission the "
                "downloaded file is harmless."
            ),
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
            what_en="Writes a test file and checks that it was created.",
            why_en=(
                "Works out which directories it can write to. It needs somewhere to drop the "
                "malicious payload, and not every directory will allow it."
            ),
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
            what_en="Walks through the system's running processes.",
            why_en=(
                "Looks for competition: other malicious programs already installed, or security "
                "tools that could give it away. Several botnets kill their rivals."
            ),
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
            what_en="Shows which user and permissions the session is running as.",
            why_en=(
                "Determines whether it already holds administrator privileges or needs to "
                "escalate before continuing."
            ),
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
            what_en="Manipulates scheduled tasks or start-up services.",
            why_en=(
                "Aims to survive a reboot. Without this, powering the machine off removes the "
                "intruder; with it, the intruder comes back on its own."
            ),
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
            what_en="Manipulates the user's SSH access keys.",
            why_en=(
                "Installs its own key so it can get back in even if the password is changed. It "
                "is one of the quietest forms of persistence."
            ),
            tactic="Persistencia",
            technique="T1098",
        ),
    ),
    (
        re.compile(r"\brm\s+-[rf]|history\s+-c|>\s*/dev/null.*history|shred\b", re.I),
        Annotation(
            what="Borra archivos o limpia el historial de comandos.",
            why="Elimina rastros de la intrusión para dificultar el análisis forense posterior.",
            what_en="Deletes files or clears the command history.",
            why_en=("Removes traces of the intrusion to make later forensic analysis harder."),
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
            what_en="Modifies system passwords or user accounts.",
            why_en=(
                "Creates an account of its own, or changes the administrator's, to lock out the "
                "legitimate owner and secure its access."
            ),
            tactic="Persistencia",
            technique="T1136",
        ),
    ),
    (
        re.compile(r"^\s*(cd|ls|pwd|cat|echo)\b", re.I),
        Annotation(
            what="Navega por el sistema de archivos o inspecciona su contenido.",
            why="Reconocimiento básico del entorno: ubicarse, ver qué hay y dónde dejar la carga.",
            what_en="Navigates the file system or inspects its contents.",
            why_en=(
                "Basic reconnaissance of the environment: getting oriented, seeing what is there "
                "and where to drop the payload."
            ),
            tactic="Descubrimiento",
            technique="T1083",
        ),
    ),
    (
        re.compile(r"\bulimit\b", re.I),
        Annotation(
            what="Eleva al máximo la cantidad de archivos y conexiones que el proceso puede abrir.",
            why="Una botnet necesita miles de sockets simultáneos para escanear o para sumarse a "
            "un ataque de denegación de servicio. El límite por defecto del sistema se lo "
            "impediría, así que lo levanta antes de arrancar.",
            what_en=(
                "Raises to the maximum the number of files and connections the process can open."
            ),
            why_en=(
                "A botnet needs thousands of simultaneous sockets to scan or to join a denial-of- "
                "service attack. The system's default limit would prevent that, so it raises the "
                "ceiling before starting."
            ),
            tactic="Evasión de defensas",
            technique="T1562.001",
        ),
    ),
    (
        re.compile(r"\blscpu\b|\bnproc\b.*grep|grep.*\bModel\b", re.I),
        Annotation(
            what="Consulta el modelo exacto del procesador.",
            why="Determina la arquitectura para descargar el binario que corresponde: la misma "
            "botnet mantiene versiones para ARM, MIPS y x86. Es el paso previo a elegir la carga.",
            what_en="Queries the exact processor model.",
            why_en=(
                "Determines the architecture in order to download the matching binary: the same "
                "botnet keeps versions for ARM, MIPS and x86. It is the step before choosing the "
                "payload."
            ),
            tactic="Descubrimiento",
            technique="T1082",
        ),
    ),
    (
        re.compile(r"\bdf\b\s+-", re.I),
        Annotation(
            what="Mide el espacio disponible en disco.",
            why="Confirma que hay lugar para descargar la carga maliciosa, y de paso distingue un "
            "servidor real de un contenedor mínimo o de un señuelo con poco disco.",
            what_en="Measures the available disk space.",
            why_en=(
                "Confirms there is room to download the malicious payload, and incidentally tells "
                "a real server apart from a minimal container or a decoy with little disk."
            ),
            tactic="Descubrimiento",
            technique="T1082",
        ),
    ),
    (
        re.compile(r"\btop\b|\bhtop\b|\bps\b\s+(aux|-ef)", re.I),
        Annotation(
            what="Lista los procesos en ejecución y su consumo de recursos.",
            why="Busca dos cosas: si el equipo ya está infectado por una botnet rival a la que "
            "conviene matar, y si hay vigilancia corriendo. El cómputo robado no se comparte.",
            what_en="Lists the running processes and their resource usage.",
            why_en=(
                "It is after two things: whether the machine is already infected by a rival "
                "botnet worth killing, and whether any monitoring is running. Stolen compute is "
                "not shared."
            ),
            tactic="Descubrimiento",
            technique="T1057",
        ),
    ),
    (
        re.compile(r"\bwhich\b|\bcommand\s+-v\b|\btype\s+\w", re.I),
        Annotation(
            what="Verifica si una herramienta está instalada y dónde.",
            why="Antes de depender de wget, curl o python, comprueba que existan. Si el señuelo "
            "responde que sí a todo, el atacante puede sospechar que no es un sistema real.",
            what_en="Checks whether a tool is installed, and where.",
            why_en=(
                "Before relying on wget, curl or python, it verifies they exist. If the decoy "
                "answers yes to everything, the attacker may suspect it is not a real system."
            ),
            tactic="Descubrimiento",
            technique="T1082",
        ),
    ),
    (
        re.compile(r"^\s*\./|\bchmod\b.*&&.*\./", re.I),
        Annotation(
            what="Ejecuta el binario que acaba de descargar.",
            why="Es el momento en que el equipo pasa a estar comprometido de verdad: hasta acá "
            "era reconocimiento, a partir de acá corre código del atacante.",
            what_en="Runs the binary it has just downloaded.",
            why_en=(
                "This is the moment the machine becomes genuinely compromised: up to here it was "
                "reconnaissance, from here on it is running the attacker's code."
            ),
            tactic="Ejecución",
            technique="T1059.004",
        ),
    ),
]

FALLBACK = Annotation(
    what="Comando ejecutado por el atacante durante la sesión.",
    why="Forma parte de la secuencia de reconocimiento posterior al acceso.",
    tactic="Descubrimiento",
    technique="",
    what_en="Command executed by the attacker during the session.",
    why_en="Part of the reconnaissance sequence that follows access.",
)


def annotate(command: str) -> Annotation:
    """Devuelve la anotación de un comando; si no coincide ninguna, cae en la genérica."""
    for pattern, annotation in RULES:
        if pattern.search(command):
            return annotation
    return FALLBACK
