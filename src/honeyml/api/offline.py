"""Congela la telemetría del panel en un archivo, para que funcione sin Elasticsearch.

El stack es pesado y solo se levanta cuando hace falta. Hay dos momentos en los que necesitamos los
datos sin él: sacar capturas del panel, y mostrarlo en una máquina que no es la de desarrollo. Los
dos son malos momentos para descubrir que el tablero necesita un clúster arriba.

La API lee este archivo sola cuando no alcanza a Elasticsearch, y avisa en qué modo está sirviendo,
así el panel lo dice en pantalla en lugar de pasar números viejos por datos en vivo.

La serie horaria va en su propio archivo. El respaldo guarda un punto por día, que alcanza para
acotar un rango, elegir sensor o agrupar por semana, pero la vista por hora no se puede reconstruir
desde ahí, y la usan dos de los cinco atajos del panel.

Se precalcula desde la tabla consolidada y no desde Elasticsearch. Ojo con una consecuencia: la
tabla incluye el tráfico de healthcheck del propio contenedor y las consultas del panel lo excluyen,
así que sin ese filtro las dos series difieren (32.732 eventos repartidos en once días) y pasar de
"por día" a "por hora" mostraría totales distintos para el mismo período. Con el filtro coinciden.

Usage:
    python -m honeyml.api.offline               # respaldo completo, necesita Elasticsearch
    python -m honeyml.api.offline --horario     # solo la serie horaria, desde la tabla consolidada
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from . import queries

OUT_FILE = Path("data/processed/snapshot.json")
HORARIO_FILE = Path("data/processed/timeline_horario.json")
TABLA_CONSOLIDADA = Path("data/processed/honeypot_events.parquet")


def build(es_url: str = queries.ES_URL) -> dict[str, Any]:
    """Consulta todo lo que necesita el panel y le pone la marca de cuándo se tomó."""
    data = queries.snapshot(es_url)
    data["generated_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    return data


def load() -> dict[str, Any] | None:
    """Lee el respaldo congelado, o None si nunca se generó."""
    if not OUT_FILE.exists():
        return None
    parsed: dict[str, Any] = json.loads(OUT_FILE.read_text(encoding="utf-8"))
    return parsed


def construir_serie_horaria() -> list[dict[str, Any]]:
    """Un cubo por hora con su desglose por sensor, calculado desde la tabla consolidada.

    Se calcula acá y no con una consulta más al índice porque la tabla ya tiene lo necesario y el
    respaldo tiene que poder regenerarse sin levantar el stack.

    El filtro de la dirección local es la única sutileza, y no es opcional: la tabla se carga con
    `match_all` mientras que todas las consultas del panel excluyen el healthcheck del contenedor.
    Sin él las dos series no cuadran y el gráfico se contradice al cambiar de intervalo.
    """
    # Import local: la API necesita pandas para armar el archivo, no para leerlo. Al nivel del
    # módulo, levantar la API cargaría pandas sin usarlo nunca.
    import pandas as pd

    if not TABLA_CONSOLIDADA.exists():
        raise FileNotFoundError(f"Falta {TABLA_CONSOLIDADA}. Generala con: make consolidate")

    df = pd.read_parquet(TABLA_CONSOLIDADA, columns=["@timestamp", "honeypot", "source.ip"])
    df = df[df["source.ip"] != queries.LOCAL_IP]

    # Misma etiqueta que produce Elasticsearch para el intervalo horario: "AAAA-MM-DD HH". El panel
    # parte por el espacio para separar el día de la hora, así que el formato es parte del contrato.
    etiquetas = df["@timestamp"].dt.strftime("%Y-%m-%d %H")

    conteo = df.groupby([etiquetas, "honeypot"]).size().unstack(fill_value=0)
    return [
        {"date": str(marca), "count": int(fila.sum()), **{s: int(v) for s, v in fila.items() if v}}
        for marca, fila in conteo.iterrows()
    ]


def cargar_serie_horaria() -> list[dict[str, Any]] | None:
    """Lee la serie horaria precalculada, o None si nunca se generó."""
    if not HORARIO_FILE.exists():
        return None
    datos: list[dict[str, Any]] = json.loads(HORARIO_FILE.read_text(encoding="utf-8"))
    return datos


def guardar_serie_horaria() -> int:
    """Regenera la serie horaria y la escribe al lado del respaldo. Devuelve cuántos cubos hay."""
    serie = construir_serie_horaria()
    HORARIO_FILE.parent.mkdir(parents=True, exist_ok=True)
    HORARIO_FILE.write_text(json.dumps(serie, ensure_ascii=False), encoding="utf-8")
    return len(serie)


def timeline(
    interval: str = "day",
    sensor: str | None = None,
    desde: str | None = None,
    hasta: str | None = None,
) -> list[dict[str, Any]] | None:
    """Responde la serie filtrada desde el respaldo, o None cuando honestamente no puede.

    Acá se resuelven los cuatro filtros del panel: rango de fechas, sensor y los tres intervalos.
    Día y semana salen de los cubos diarios del respaldo; la vista por hora, del archivo horario,
    que se genera aparte porque el respaldo no la puede reconstruir.

    Que devuelva None cuando falta el archivo horario, en lugar de una aproximación, es a propósito.
    Sin esa distinción el pedido fallaría, el panel se comería el error y el gráfico seguiría
    mostrando la serie sin filtrar debajo de unos controles que dicen "último día", que es una
    respuesta equivocada disfrazada de correcta.
    """
    datos = load()
    if datos is None:
        return None

    if interval == "hour":
        horas = cargar_serie_horaria()
        return None if horas is None else _acotar(horas, sensor, desde, hasta, corte=13)

    dias = _acotar(datos.get("timeline") or [], sensor, desde, hasta, corte=10)
    if interval != "week":
        return dias
    return _por_semana(dias)


def _acotar(
    filas: list[dict[str, Any]],
    sensor: str | None,
    desde: str | None,
    hasta: str | None,
    corte: int,
) -> list[dict[str, Any]]:
    """Acota una serie por rango de fechas y sensor. `corte` es cuánto de la etiqueta se conserva.

    Diez para la vista diaria y trece para la horaria ("AAAA-MM-DD HH"), que es el mismo largo con
    que Elasticsearch etiqueta cada intervalo. El panel parte esa etiqueta por el espacio para
    separar el día de la hora, así que el largo es parte del contrato y no una preferencia.

    El recorte del rango siempre compara solo la fecha: el panel manda el fin de día como
    "AAAA-MM-DDT23:59:59", y contra una etiqueta horaria una comparación de cadenas completa
    dejaría fuera las horas de ese último día.
    """
    d0 = (desde or "")[:10]
    d1 = (hasta or "")[:10]

    salida: list[dict[str, Any]] = []
    for f in filas:
        etiqueta = str(f.get("date", ""))
        dia = etiqueta[:10]
        if (d0 and dia < d0) or (d1 and dia > d1):
            continue

        if sensor:
            # Con un sensor elegido, el total pasa a ser el de ese sensor. Dejar el `count` original
            # mostraría la barra completa bajo una etiqueta que dice lo contrario.
            n = int(f.get(sensor, 0))
            salida.append({"date": etiqueta[:corte], "count": n, sensor: n})
        else:
            salida.append({**f, "date": etiqueta[:corte]})
    return salida


def _por_semana(dias: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Agrupa los cubos diarios en semanas ISO, como las etiqueta Elasticsearch.

    Misma clave que `calendar_interval: week`, así pasar de vivo a congelado no corre las barras
    unos días para el costado.
    """
    semanas: dict[str, dict[str, Any]] = {}
    for d in dias:
        try:
            dia = date.fromisoformat(str(d["date"])[:10])
        except ValueError:
            continue
        lunes = (dia - timedelta(days=dia.weekday())).isoformat()

        acumulado = semanas.setdefault(lunes, {"date": lunes, "count": 0})
        for clave, valor in d.items():
            if clave == "date" or not isinstance(valor, int):
                continue
            acumulado[clave] = int(acumulado.get(clave, 0)) + valor
    return [semanas[k] for k in sorted(semanas)]


def _informar_horaria() -> None:
    n = guardar_serie_horaria()
    kb = HORARIO_FILE.stat().st_size / 1024
    print(f"Serie horaria -> {HORARIO_FILE} ({kb:.0f} KB, {n} intervalos)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--horario",
        action="store_true",
        help="regenera solo la serie horaria desde la tabla consolidada, sin tocar Elasticsearch",
    )
    args = ap.parse_args()

    if args.horario:
        _informar_horaria()
        print("\nLa vista por hora del panel ya funciona sin Elasticsearch levantado.")
        return

    data = build()
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    ov = data["overview"]
    size_kb = OUT_FILE.stat().st_size / 1024
    print(f"Snapshot congelado -> {OUT_FILE} ({size_kb:.0f} KB)")
    print(f"  {ov['events']:,} eventos, {ov['unique_ips']:,} direcciones".replace(",", "."))
    print(f"  ventana {ov['first_event'][:10]} a {ov['last_event'][:10]}")
    print(f"  tomado {data['generated_at']}")

    # La serie horaria sale de la tabla consolidada, no del índice, así que se regenera junto con el
    # respaldo: si quedara desfasada, el gráfico mostraría un período distinto al cambiar de
    # intervalo. Si la tabla no está, el respaldo igual sirve, solo que pierde la vista por hora.
    try:
        _informar_horaria()
    except FileNotFoundError as exc:
        print(f"  sin serie horaria: {exc}")

    print("\nEl panel ahora funciona sin Elasticsearch levantado.")


if __name__ == "__main__":
    main()
