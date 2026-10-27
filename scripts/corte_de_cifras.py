"""Toma en un solo momento las cifras que se publican sobre el sistema en producción.

Corre adentro de la imagen de análisis, con la red del anfitrión, y usa las mismas consultas que la
API y el panel, así cada cifra publicada coincide por construcción con la que muestra el panel. Lee
también los artefactos derivados de data/processed y el repertorio del bus. Escribe un JSON por la
salida estándar.

    python scripts/corte_de_cifras.py > corte.json
    python scripts/corte_de_cifras.py --hasta 2026-10-03T22:00:59Z > corte_recontado.json

Con `--hasta`, la telemetría se cuenta solo hasta ese instante, para recontar un corte ya publicado
con el código actual. El motor queda afuera: sus decisiones y el bus no se pueden llevar a un
momento pasado.
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

import redis

from honeyml import redes
from honeyml.api import decisiones, queries

PROCESADOS = Path("data/processed")

# Un día cuenta como captura efectiva desde este volumen. Por debajo, el sensor está caído y solo
# registra algún evento suelto al volver.
CAPTURA_EFECTIVA = 10

# El filtro del instante tope, vacío sin `--hasta`. Lo usan los conteos que este script arma por su
# cuenta; las consultas del panel lo reciben con `queries.fijar_tope`.
TOPE: list[dict[str, Any]] = []


def _es(path: str, body: dict[str, Any] | None = None) -> Any:
    req = urllib.request.Request(
        f"{queries.ES_URL}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"},
        method="POST" if body is not None else "GET",
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def _pct(parte: float, total: float, decimales: int = 1) -> float:
    return round(100 * parte / total, decimales) if total else 0.0


def _artefacto(nombre: str) -> Any:
    ruta = PROCESADOS / nombre
    return {
        "generado": datetime.datetime.fromtimestamp(ruta.stat().st_mtime, datetime.UTC).isoformat(),
        "datos": json.loads(ruta.read_text(encoding="utf-8")),
    }


def telemetria() -> dict[str, Any]:
    ov = queries.overview()
    todos = _es("/honeypot-*/_count", {"query": {"bool": {"filter": TOPE}}})["count"]
    indices = _es("/_cat/indices/honeypot-*?format=json&bytes=b")
    diario = queries.timeline(interval="day")
    con_captura = [d for d in diario if d["count"] > 0]
    pico = max(diario, key=lambda d: d["count"])
    return {
        "resumen": ov,
        "documentos_indexados": todos,
        "verificaciones_internas": todos - ov["events"],
        "tasa_de_acceso_exitoso_pct": _pct(ov["logins_success"], ov["logins"], 2),
        "aporte_por_sensor_pct": {k: _pct(v, ov["events"]) for k, v in ov["by_sensor"].items()},
        "indices_diarios": len(indices),
        "tamano_del_corpus_bytes": sum(int(i["store.size"]) for i in indices),
        "dia_pico": pico,
        "dias_con_captura": len(con_captura),
        "promedio_por_dia_con_captura": round(
            sum(d["count"] for d in con_captura) / len(con_captura)
        ),
        "diario": diario,
    }


def continuidad(diario: list[dict[str, Any]]) -> dict[str, Any]:
    """Días con captura de cada sensor, desde su primer evento, y los tramos sin ninguno."""
    out: dict[str, Any] = {}
    for sensor in ("cowrie", "dionaea"):
        dias = [(d["date"], d.get(sensor, 0)) for d in diario]
        primero = next(i for i, (_, n) in enumerate(dias) if n > 0)
        ventana = dias[primero:]
        huecos: list[list[str]] = []
        for fecha, n in ventana:
            if n == 0:
                if huecos and huecos[-1][1] == _ayer(fecha):
                    huecos[-1][1] = fecha
                else:
                    huecos.append([fecha, fecha])
        out[sensor] = {
            "desde": ventana[0][0],
            "dias_en_ventana": len(ventana),
            "dias_con_eventos": sum(1 for _, n in ventana if n > 0),
            "dias_con_captura_efectiva": sum(1 for _, n in ventana if n >= CAPTURA_EFECTIVA),
            "dias_con_eventos_sueltos": [f for f, n in ventana if 0 < n < CAPTURA_EFECTIVA],
            "huecos": [{"desde": a, "hasta": b} for a, b in huecos],
        }
    return out


def _ayer(fecha: str) -> str:
    return (datetime.date.fromisoformat(fecha) - datetime.timedelta(days=1)).isoformat()


def protocolos() -> list[dict[str, Any]]:
    return [
        {
            **p,
            "eventos_por_direccion": round(p["count"] / p["sources"], 1) if p["sources"] else None,
        }
        for p in queries.protocol_detail()
    ]


def credenciales() -> dict[str, Any]:
    con_clave = _es(
        "/honeypot-*/_count",
        {
            "query": {
                "bool": {
                    "must": [{"exists": {"field": "cowrie.password"}}],
                    "must_not": redes.TERMINOS,
                    "filter": TOPE,
                }
            }
        },
    )["count"]
    indice = _artefacto("password_index.json")
    return queries.top_credentials(size=12) | {
        "intentos_con_clave_en_vivo": con_clave,
        "indice_de_contrasenas": {
            "generado": indice["generado"],
            "distintas": indice["datos"]["distinct"],
            "intentos": indice["datos"]["attempts"],
        },
    }


def huellas() -> dict[str, Any]:
    a = _artefacto("fingerprints.json")
    d = a["datos"]
    familias = sorted(d["families"], key=lambda f: f["sessions"], reverse=True)
    return {
        "generado": a["generado"],
        "sesiones_con_comandos": d["total_sessions"],
        "familias": d["families_found"],
        "sesiones_agrupadas": d["grouped_sessions"],
        "sesiones_agrupadas_pct": _pct(d["grouped_sessions"], d["total_sessions"]),
        "mayores": [
            {
                "sesiones": f["sessions"],
                "pct": _pct(f["sessions"], d["total_sessions"]),
                "direcciones": f["sources"],
                "por_direccion": round(f["sessions"] / f["sources"], 1) if f["sources"] else None,
                "comandos": f["total_commands"],
                "primer_comando": f["commands"][0][:80] if f["commands"] else "",
            }
            for f in familias[:3]
        ],
        "tres_mayores_pct": _pct(sum(f["sessions"] for f in familias[:3]), d["total_sessions"]),
    }


def arquetipos() -> dict[str, Any]:
    a = _artefacto("arquetipos.json")
    d = a["datos"]
    p = d["perfiles"]
    total = d["direcciones_analizadas"]

    def suma(campo: str) -> int:
        return int(round(sum(x["direcciones"] * x[campo] / 100 for x in p)))

    # El mismo embudo que dibuja el panel, con la misma cuenta.
    escalones = [
        ("golpearon_la_puerta", total),
        (
            "insistieron_con_credenciales",
            sum(x["direcciones"] for x in p if x["nombre"] != "Sondeo"),
        ),
        ("lograron_entrar", suma("pct_logro_acceso")),
        ("ejecutaron_comandos", suma("pct_ejecuto_comandos")),
        ("trajeron_algo", suma("pct_descargo_archivo")),
    ]
    elegido = next(b for b in d["barrido_k"] if b["k"] == d["grupos"])
    return {
        "generado": a["generado"],
        "direcciones": total,
        "caracteristicas": d["caracteristicas"],
        "grupos": d["grupos"],
        "silueta": round(elegido["silueta"], 3),
        "perfiles": [{k: v for k, v in x.items() if k not in ("descripcion",)} for x in p],
        "embudo": [
            {
                "escalon": nombre,
                "direcciones": n,
                "del_total_pct": _pct(n, total),
                "del_anterior_pct": _pct(n, escalones[i - 1][1]) if i else None,
            }
            for i, (nombre, n) in enumerate(escalones)
        ],
    }


def geografia() -> dict[str, Any]:
    g = queries.geography()
    return {
        "pais_resuelto_pct": _pct(g["with_geo"], g["events"]),
        "red_resuelta_pct": _pct(g["with_asn"], g["events"]),
        "paises": [
            {
                "pais": c["country"],
                "eventos": c["count"],
                "de_lo_localizado_pct": _pct(c["count"], g["with_geo"]),
                "direcciones": c["sources"],
                "por_direccion": round(c["count"] / c["sources"]) if c["sources"] else None,
            }
            for c in g["countries"][:10]
        ],
        "redes": g["autonomous_systems"][:5],
    }


def ritmo() -> dict[str, Any]:
    horas = queries.hourly()
    pico = max(horas, key=lambda h: h["count"])
    valle = min(horas, key=lambda h: h["count"])
    semana = queries.weekly_rhythm()

    def promedio(celdas: list[tuple[int, int]]) -> float:
        eventos = sum(semana["total"][d][h] for d, h in celdas)
        observadas = sum(semana["observed"][d][h] for d, h in celdas)
        return round(eventos / observadas) if observadas else 0

    oficina = promedio([(d, h) for d in range(5) for h in range(9, 18)])
    madrugada = promedio([(d, h) for d in range(7) for h in range(0, 6)])
    fin_de_semana = promedio([(d, h) for d in (5, 6) for h in range(24)])
    return {
        "hora_pico_utc": pico,
        "hora_valle_utc": valle,
        "pico_sobre_valle": round(pico["count"] / valle["count"], 2) if valle["count"] else None,
        "por_hora_de_oficina": oficina,
        "por_hora_de_madrugada": madrugada,
        "por_hora_de_fin_de_semana": fin_de_semana,
        "madrugada_sobre_oficina": round(madrugada / oficina, 2) if oficina else None,
        "fin_de_semana_sobre_oficina": round(fin_de_semana / oficina, 2) if oficina else None,
        "definiciones": (
            "oficina: lunes a viernes de 9 a 18 UTC; madrugada: todos los días de 0 a 6 UTC; "
            "fin de semana: sábado y domingo completos. Promedios por hora observada."
        ),
    }


def etapas(total: int) -> list[dict[str, Any]]:
    return [{**e, "pct": _pct(e["count"], total, 2)} for e in queries.attack_stages()]


def sesiones() -> dict[str, Any]:
    a = _artefacto("replay_sessions.json")
    pasos = [p for s in a["datos"] for p in s["steps"]]
    return {
        "generado": a["generado"],
        "sesiones": len(a["datos"]),
        "pasos": len(pasos),
        "por_tactica": Counter(p["tactic"] for p in pasos).most_common(),
        "por_tecnica": Counter(p["technique"] for p in pasos if p.get("technique")).most_common(),
    }


def motor() -> dict[str, Any]:
    r = decisiones.resumen()
    razonadas = r["razonadas"]
    bus = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True, socket_timeout=10)
    firmas = sum(1 for _ in bus.scan_iter(match="honeyml:firma:*", count=1000))
    indice = _es(f"/_cat/indices/{decisiones.DECISIONES}*?format=json&bytes=b")
    grupo = next((g for g in bus.xinfo_groups("honeyml:events") if g["name"] == "triaje"), {})
    return {
        "actividad": {k: v for k, v in r["actividad"].items() if k != "por_minuto"},
        "copiadas_pct": _pct(r["copiadas"], r["total"]),
        "razonadas_pct": _pct(razonadas, r["total"]),
        "costo_por_razonada_usd": round(r["costo_usd"] / razonadas, 5) if razonadas else None,
        "conductas_con_decision_vigente": firmas,
        "indice_de_decisiones": {
            "documentos": sum(int(i["docs.count"]) for i in indice),
            "bytes": sum(int(i["store.size"]) for i in indice),
        },
        "bus": {
            "largo": bus.xlen("honeyml:events"),
            "pendientes": grupo.get("pending"),
            "atraso": grupo.get("lag"),
            "consumidores": grupo.get("consumers"),
            "descartados": bus.xlen("honeyml:events:muertos"),
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Las cifras publicadas, tomadas en un solo momento.")
    ap.add_argument("--hasta", help="cuenta la telemetría solo hasta este instante, en ISO 8601")
    args = ap.parse_args()
    if args.hasta:
        TOPE.append({"range": {"@timestamp": {"lte": args.hasta}}})
        queries.fijar_tope(args.hasta)

    inicio = datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")
    t = telemetria()
    corte = {
        "inicio": inicio,
        "hasta": args.hasta,
        "telemetria": {k: v for k, v in t.items() if k != "diario"},
        "continuidad": continuidad(t["diario"]),
        "protocolos": protocolos(),
        "credenciales": credenciales(),
        "huellas": huellas(),
        "arquetipos": arquetipos(),
        "geografia": geografia(),
        "ritmo": ritmo(),
        "etapas": etapas(t["resumen"]["events"]),
        "sesiones": sesiones(),
        "motor": None if args.hasta else motor(),
        "fin": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
    }
    json.dump(corte, sys.stdout, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
