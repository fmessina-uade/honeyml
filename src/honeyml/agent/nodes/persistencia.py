"""Quinto nodo: deja la decisión guardada de forma durable, y cierra el ciclo.

Todo camino del grafo termina acá, incluidos los que no produjeron decisión. Un evento que llegó al
motor y no aparece en ningún lado es peor que uno mal clasificado: el segundo se puede discutir, el
primero no se puede ni contar. Así el panel lo muestra como no concluyente, que es lo que describe
el CU-03, en vez de simplemente no listarlo.

Qué se guarda, además del nivel. La justificación y la evidencia, porque una decisión de triaje que
no se puede releer es una opinión. El piso y el techo que la escala calculó para ese evento, así
quien audite verifica que el nivel era defendible sin tener que recalcularlos. Los reproches, que
cuentan si el modelo acertó de una o hubo que corregirlo. Y qué modelo contestó y cuánto costó, que
es la única forma de responder después si convino la política de escalar recién al reintentar.

Una cosa que este nodo decide y no acepta: `concluyente`. El modo estricto del proveedor obliga al
modelo a emitir ese campo, así que viene con un valor, pero describe cómo terminó el ciclo y no algo
que el modelo pueda saber. Lo escribe el motor a partir de `resultado_del_ciclo`. Dejar pasar el del
modelo permitiría una decisión válida marcada como no concluyente, o peor, un corte por esquema
inválido que se presenta como concluyente.

Si el almacén no responde, el nodo levanta. Misma regla que en contexto y en inferencia: la
excepción sale del grafo, el consumidor no confirma, y otro lo reclama cuando Elasticsearch vuelva.
Confirmar un evento cuya decisión no se pudo guardar lo perdería para siempre, y en silencio.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ..adapters.almacen import Almacen, AlmacenElastic
from ..adapters.repertorio import Repertorio
from ..severidad import piso, techo
from ..state import EstadoTriaje, resultado_del_ciclo

# Tope de reproches que se guardan. Con MAX_INTENTOS en 3 y varios problemas por ronda, el techo
# real ronda la docena; el corte está para que un cambio de esos números no infle un documento sin
# que nadie lo haya decidido.
MAX_REPROCHES_GUARDADOS = 20


def _del_evento(estado: EstadoTriaje) -> dict[str, Any]:
    """Los datos del evento que viajan con la decisión.

    Se copian en lugar de dejar solo el `doc_id` porque el panel tiene que poder listar decisiones
    sin una segunda consulta por cada una, y porque una decisión que se lee sola es auditable
    aunque el índice de telemetría se haya rotado.
    """
    evento = estado["evento"]
    contexto = estado.get("contexto")
    return {
        "doc_id": evento.doc_id,
        "momento": evento.timestamp or None,
        "sensor": evento.honeypot or None,
        "categoria": evento.category or None,
        "accion": evento.action or None,
        "resultado": evento.outcome or None,
        "protocolo": evento.protocol or None,
        "origen": evento.source_ip or None,
        "sesion": evento.session or None,
        "resumen": contexto.resumen if contexto else evento.resumen(),
    }


def _de_la_decision(estado: EstadoTriaje, concluyente: bool) -> dict[str, Any]:
    """El bloque de la decisión, o el mínimo que se puede afirmar cuando no hubo ninguna."""
    evento = estado["evento"]
    limites = {"piso": piso(evento).value, "techo": techo(evento).value}

    decision = estado.get("decision")
    if decision is None:
        # Sin decisión igual se guardan los límites: dicen qué se esperaba de este evento, y son la
        # mitad del diagnóstico cuando se revisa por qué el ciclo no llegó a nada.
        return {**limites, "concluyente": False}

    return {
        **limites,
        "severidad": decision.severidad.value,
        "confianza": decision.confianza,
        "tactica_mitre": decision.tactica_mitre,
        "justificacion": decision.justificacion,
        "evidencia": decision.evidencia,
        "concluyente": concluyente,
    }


def documento(estado: EstadoTriaje) -> dict[str, Any]:
    """Arma el documento que se indexa. Separado de `guardar` para poder probarlo sin almacén."""
    motivo = resultado_del_ciclo(estado)
    return {
        # Cuándo se decidió, que no es cuándo ocurrió el evento. Los dos hacen falta: uno mide el
        # atraso del motor, el otro ubica el ataque.
        "@timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
        "evento": _del_evento(estado),
        "decision": _de_la_decision(estado, concluyente=motivo is None),
        "ciclo": {
            "motivo_de_corte": motivo,
            "intentos": int(estado.get("intentos", 0)),
            "rechazos": int(estado.get("rechazos", 0)),
            "reproches": list(estado.get("reproches") or [])[:MAX_REPROCHES_GUARDADOS],
            # La firma agrupa los eventos de la misma conducta, y `reutilizada_de` dice de cuál se
            # copió esta decisión. Vacío quiere decir que se razonó. Con los dos campos, el panel
            # cuenta a cuántos eventos cubre cada decisión con una sola agregación, y cualquiera
            # puede verificar que una copia coincide con su original.
            "firma": estado.get("firma") or None,
            "reutilizada_de": estado.get("reutilizada_de") or None,
        },
        "modelo": estado.get("consumo") or {},
    }


def guardar(
    estado: EstadoTriaje,
    almacen: Almacen | None = None,
    repertorio: Repertorio | None = None,
) -> EstadoTriaje:
    """Persiste la decisión. Levanta si el almacén no responde, para que el evento no se pierda.

    `almacen` se inyecta igual que el servicio de inferencia: así el nodo se prueba sin levantar el
    stack, que son treinta segundos de arranque por corrida.
    """
    evento = estado.get("evento")
    if evento is None:
        # No debería pasar: el estado inicial siempre trae el evento. Si pasara, no hay identidad
        # bajo la cual guardar, y un documento sin `doc_id` sería peor que no escribir nada.
        return {}

    destino = almacen or AlmacenElastic()
    destino.guardar(evento.doc_id, documento(estado))
    _registrar_la_firma(estado, repertorio)
    return {}


def _registrar_la_firma(estado: EstadoTriaje, repertorio: Repertorio | None) -> None:
    """Anota la conducta como resuelta, recién después de que la decisión quedó guardada.

    El orden importa y es el mismo que usa el consumidor para la deduplicación: la marca se escribe
    después del éxito y nunca antes. Al revés, un almacén que falla dejaría la firma apuntando a una
    decisión que no se persistió, y las miles de repeticiones que vienen detrás copiarían de un
    documento inexistente.

    Solo se registran las concluyentes. Una decisión que no pasó la validación describe un ciclo que
    salió mal, no una conducta resuelta: propagarla le pondría el mismo fracaso a las 6.588
    repeticiones de la firma en lugar de darles otra oportunidad.

    Y no se re-registra lo que ya vino del repertorio: el `doc_id` de origen tiene que seguir siendo
    el del evento que efectivamente se razonó, o la cadena de auditoría apunta a una copia.
    """
    if repertorio is None or estado.get("reutilizada_de"):
        return
    firma = estado.get("firma")
    decision = estado.get("decision")
    if not firma or decision is None or resultado_del_ciclo(estado) is not None:
        return
    evento = estado["evento"]
    repertorio.registrar(firma, decision.model_dump(mode="json"), evento.doc_id)
