"""La tasa de falsos positivos y la de falsos negativos del motor, auditadas a ciegas.

La positiva es la alerta crítica. Se mide solo sobre las conductas con piso alto, que es la única
frontera donde el motor decide algo: debajo de alto nunca llega a crítico y con un archivo
transferido el piso ya es crítico, así que contarlas inflaría el resultado por construcción.

Se calcula con dos referencias. La regla (crítico si el comando transfiere un archivo) se aplica a
todas las conductas de la población muestreada. El analista, que revisó a ciegas una muestra
estratificada, da la otra: su tasa se estima pesando cada estrato por su tamaño, con un intervalo
por remuestreo dentro de cada estrato. Un estrato revisado entero no aporta variación. Además se
informa cuánto coinciden la regla y el analista, y la táctica del motor contra la del analista.

Solo lee. Se corre en el servidor con `make tasa`; con `--json` imprime el resultado sin formato.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import urllib.request
from typing import Any

from ..api import queries
from ..api.decisiones import MUESTRA_FILE, REVISIONES
from .muestra import ESTRATOS

CRITICO = "critico"
REMUESTREOS = 4000
SEMILLA = 42


def _motor_critico(estrato: str) -> bool:
    return estrato.startswith("escalada")


def _regla_critica(estrato: str) -> bool:
    return estrato.endswith("con_transferencia")


def _tasa(parte: float, resto: float) -> float | None:
    total = parte + resto
    return parte / total if total else None


def wilson(exitos: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """Intervalo de Wilson para una proporción; se porta bien con muestras chicas y con 0 o n."""
    if not n:
        return None
    p = exitos / n
    centro = (p + z * z / (2 * n)) / (1 + z * z / n)
    margen = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centro - margen), min(1.0, centro + margen)


def _por_referencia(n: dict[str, float], p_critico: dict[str, float]) -> dict[str, float | None]:
    """Falsos positivos y negativos esperados en la población, dado el tamaño de cada estrato y la
    proporción de conductas que la referencia considera críticas en él."""
    fp = vn = fn = vp = 0.0
    for estrato in ESTRATOS:
        criticas = n[estrato] * p_critico[estrato]
        no_criticas = n[estrato] - criticas
        if _motor_critico(estrato):
            vp, fp = vp + criticas, fp + no_criticas
        else:
            fn, vn = fn + criticas, vn + no_criticas
    return {"falsos_positivos": _tasa(fp, vn), "falsos_negativos": _tasa(fn, vp)}


def _intervalo(valores: list[float]) -> tuple[float, float] | None:
    valores = sorted(v for v in valores if v is not None)
    if not valores:
        return None
    return valores[int(0.025 * (len(valores) - 1))], valores[int(0.975 * (len(valores) - 1))]


def calcular(muestra: dict[str, Any], revisiones: list[dict[str, Any]]) -> dict[str, Any]:
    estratos = muestra["estratos"]
    de_la_muestra = {c["doc_id"]: c["estrato"] for c in muestra["conductas"]}
    revisadas = [r for r in revisiones if r.get("a_ciegas") and r.get("doc_id") in de_la_muestra]

    # la regla, sobre toda la población muestreada
    regla = {}
    for unidad in ("conductas", "decisiones"):
        n = {e: float(estratos[e][unidad]) for e in ESTRATOS}
        regla[unidad] = _por_referencia(n, {e: 1.0 if _regla_critica(e) else 0.0 for e in ESTRATOS})

    # el analista, estrato por estrato
    juicios: dict[str, list[bool]] = {e: [] for e in ESTRATOS}
    coincide_regla: dict[str, int] = {e: 0 for e in ESTRATOS}
    tacticas: dict[str, list[bool]] = {e: [] for e in ESTRATOS}
    motor_distinto = 0
    for r in revisadas:
        estrato = de_la_muestra[r["doc_id"]]
        critica = r.get("severidad") == CRITICO
        juicios[estrato].append(critica)
        coincide_regla[estrato] += critica == _regla_critica(estrato)
        motor = r.get("motor") or {}
        tacticas[estrato].append(
            (r.get("tactica_mitre") or None) == (motor.get("tactica_mitre") or None)
        )
        motor_distinto += (motor.get("severidad") == CRITICO) != _motor_critico(estrato)

    detalle = {}
    for e in ESTRATOS:
        n_rev, criticas = len(juicios[e]), sum(juicios[e])
        detalle[e] = {
            "poblacion_conductas": estratos[e]["conductas"],
            "poblacion_decisiones": estratos[e]["decisiones"],
            "revisadas": n_rev,
            "criticas_segun_el_analista": criticas,
            "proporcion_critica": criticas / n_rev if n_rev else None,
            "intervalo_wilson": wilson(criticas, n_rev),
            "coincide_con_la_regla": coincide_regla[e],
            "misma_tactica": sum(tacticas[e]),
        }

    analista: dict[str, Any] = {}
    generador = random.Random(SEMILLA)
    for unidad in ("conductas", "decisiones"):
        n = {e: float(estratos[e][unidad]) for e in ESTRATOS}
        p = {e: (sum(juicios[e]) / len(juicios[e])) if juicios[e] else 0.0 for e in ESTRATOS}
        puntual = _por_referencia(n, p)
        simulados: dict[str, list[float]] = {"falsos_positivos": [], "falsos_negativos": []}
        for _ in range(REMUESTREOS):
            p_sim = {}
            for e in ESTRATOS:
                js = juicios[e]
                if not js or len(js) >= estratos[e]["conductas"]:
                    p_sim[e] = p[e]
                else:
                    p_sim[e] = sum(generador.choice(js) for _ in js) / len(js)
            for k, v in _por_referencia(n, p_sim).items():
                if v is not None:
                    simulados[k].append(v)
        analista[unidad] = {
            k: {"tasa": v, "intervalo_95": _intervalo(simulados[k])} for k, v in puntual.items()
        }

    # coincidencia entre la regla y el analista, sobre lo revisado
    total = len(revisadas)
    acuerdo = sum(coincide_regla.values())
    regla_si = sum(len(juicios[e]) for e in ESTRATOS if _regla_critica(e))
    analista_si = sum(sum(juicios[e]) for e in ESTRATOS)
    esperado = (
        ((regla_si * analista_si) + (total - regla_si) * (total - analista_si)) / (total * total)
        if total
        else 0
    )
    observado = acuerdo / total if total else 0
    kappa = (observado - esperado) / (1 - esperado) if total and esperado < 1 else None

    return {
        "muestra_generada": muestra.get("generada"),
        "revisadas": total,
        "de": len(de_la_muestra),
        "motor_cambio_de_lado": motor_distinto,
        "regla": regla,
        "analista": analista,
        "por_estrato": detalle,
        "regla_contra_analista": {"coinciden": acuerdo, "de": total, "kappa": kappa},
        "tactica": {"coinciden": sum(sum(t) for t in tacticas.values()), "de": total},
    }


def _pct(v: float | None) -> str:
    return "sin datos" if v is None else f"{v * 100:.1f} %".replace(".", ",")


def _rango(r: tuple[float, float] | list[float] | None) -> str:
    return "" if not r else f"(entre {_pct(r[0])} y {_pct(r[1])})"


def informe(r: dict[str, Any]) -> list[str]:
    revisadas = f"{r['revisadas']} de {r['de']} conductas revisadas a ciegas"
    lineas = [f"Muestra generada {r['muestra_generada']}: {revisadas}."]
    if r["motor_cambio_de_lado"]:
        cambios = r["motor_cambio_de_lado"]
        lineas.append(
            f"Hay {cambios} decisiones que cambiaron de lado de crítico desde el muestreo."
        )
    lineas.append("\nCon la regla como referencia, sobre toda la población con piso alto:")
    for unidad, t in r["regla"].items():
        fp, fn = _pct(t["falsos_positivos"]), _pct(t["falsos_negativos"])
        lineas.append(f"  por {unidad}: falsos positivos {fp}, falsos negativos {fn}")
    lineas.append("\nCon el analista como referencia, estimado por estratos:")
    for unidad, t in r["analista"].items():
        pos, neg = t["falsos_positivos"], t["falsos_negativos"]
        sangria = " " * (len(unidad) + 4)
        lineas.append(
            f"  por {unidad}: falsos positivos {_pct(pos['tasa'])} {_rango(pos['intervalo_95'])}"
        )
        lineas.append(
            f"  {sangria}falsos negativos {_pct(neg['tasa'])} {_rango(neg['intervalo_95'])}"
        )
    lineas.append("\nPor estrato:")
    columnas = f"{'conductas':>10}{'revisadas':>10}{'críticas':>10}{'= regla':>9}{'= táctica':>11}"
    lineas.append(f"  {'estrato':<28}{columnas}")
    for e, d in r["por_estrato"].items():
        cifras = (
            f"{d['poblacion_conductas']:>10}{d['revisadas']:>10}"
            f"{d['criticas_segun_el_analista']:>10}{d['coincide_con_la_regla']:>9}"
            f"{d['misma_tactica']:>11}"
        )
        lineas.append(f"  {e:<28}{cifras}")
    rc = r["regla_contra_analista"]
    kappa = "sin datos" if rc["kappa"] is None else f"{rc['kappa']:.2f}".replace(".", ",")
    lineas.append(
        f"\nLa regla y el analista coinciden en {rc['coinciden']} de {rc['de']} (kappa {kappa})."
    )
    tac = r["tactica"]
    lineas.append(
        f"La táctica del motor coincide con la del analista en {tac['coinciden']} de {tac['de']}."
    )
    return lineas


def _revisiones() -> list[dict[str, Any]]:
    pedido = urllib.request.Request(
        f"{queries.ES_URL}/{REVISIONES}/_search",
        data=json.dumps({"size": 1000, "query": {"term": {"a_ciegas": True}}}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(pedido, timeout=60) as resp:
        return [h["_source"] for h in json.load(resp)["hits"]["hits"]]


def main() -> int:
    ap = argparse.ArgumentParser(description="Tasas de falsos positivos y negativos del motor.")
    ap.add_argument("--json", action="store_true", help="el resultado sin formato")
    args = ap.parse_args()
    muestra = json.loads(MUESTRA_FILE.read_text(encoding="utf-8"))
    resultado = calcular(muestra, _revisiones())
    if args.json:
        json.dump(resultado, sys.stdout, ensure_ascii=False, indent=2)
    else:
        print("\n".join(informe(resultado)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
