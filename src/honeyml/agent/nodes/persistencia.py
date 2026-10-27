"""Quinto nodo: deja la decisión guardada de forma durable, y cierra el ciclo.

Todo camino del grafo termina acá, incluidos los que no produjeron decisión. Un evento que llegó al
motor y no aparece en ningún lado es peor que uno mal clasificado: el segundo se puede discutir, el
primero no se puede ni contar. Así el panel lo muestra como no concluyente y pendiente.

Además del nivel se guardan la justificación y la evidencia, porque una decisión que no se puede
releer es una opinión; el piso y el techo de la escala, para verificar que el nivel era defendible
sin recalcularlos; los reproches, que cuentan si hubo que corregir al modelo; qué modelo contestó y
cuánto costó, para evaluar la política de escalar al reintentar; y qué consultas fallaron, porque
una decisión tomada sin el historial de la dirección no vale lo mismo. Un ciclo no concluyente o con
consultas fallidas deja la decisión marcada para revisión, y lo que decida quien opera el panel va
a un índice aparte, así la del motor queda intacta y se puede medir en qué se equivocó.

`concluyente` lo escribe el motor a partir de `resultado_del_ciclo`, porque describe cómo terminó
el ciclo y el modelo no puede saberlo. Si el almacén no responde, el nodo levanta, igual que
contexto e inferencia: el consumidor no confirma y otro lo reclama cuando Elasticsearch vuelva.
Confirmar un evento cuya decisión no se pudo guardar lo perdería para siempre, y en silencio.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ..adapters.almacen import Almacen, AlmacenElastic
from ..adapters.repertorio import Repertorio
from ..severidad import piso, techo
from ..state import SUFIJO_DE_FALLA, EstadoTriaje, resultado_del_ciclo

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
        "motivo_sin_tactica": decision.motivo_sin_tactica,
        "justificacion": decision.justificacion,
        "evidencia": decision.evidencia,
        "concluyente": concluyente,
    }


def consultas_fallidas(estado: EstadoTriaje) -> list[str]:
    """Qué consultas del contexto fallaron, por nombre.

    Los nodos de contexto e historial anotan cada falla como `<consulta>_falló` en los hallazgos,
    con el mensaje del error. En el documento va solo el nombre, que es lo que necesita quien revisa
    ("se decidió sin la sesión"). El mensaje sirve para depurar y lo imprime el motor.
    """
    contexto = estado.get("contexto")
    if contexto is None:
        return []
    return sorted(
        clave.removesuffix(SUFIJO_DE_FALLA)
        for clave in contexto.hallazgos
        if clave.endswith(SUFIJO_DE_FALLA)
    )


def documento(estado: EstadoTriaje) -> dict[str, Any]:
    """Arma el documento que se indexa. Separado de `guardar` para poder probarlo sin almacén."""
    motivo = resultado_del_ciclo(estado)
    fallidas = consultas_fallidas(estado)
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
            "consultas_fallidas": fallidas,
            "requiere_revision": motivo is not None or bool(fallidas),
            "retriaje": bool(estado.get("retriaje")),
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

    # Un documento que dice haberse copiado de sí mismo no se escribe nunca. El repertorio registra
    # una firma recién después de que su decisión quedó guardada, así que si el origen es este mismo
    # evento, la decisión ya está en el índice y lo que llegó es una repetición.
    origen = estado.get("reutilizada_de")
    if origen and origen == evento.doc_id:
        return {"ya_existia": True}

    if not destino.guardar(evento.doc_id, documento(estado)):
        # Ya había una decisión para este evento y no se tocó. La firma tampoco se registra: lo
        # guardado puede no coincidir con lo que trae este estado, y el repertorio quedaría
        # apuntando a un documento que dice otra cosa.
        return {"ya_existia": True}

    _registrar_la_firma(estado, repertorio)
    return {}


def _registrar_la_firma(estado: EstadoTriaje, repertorio: Repertorio | None) -> None:
    """Anota la conducta como resuelta, recién después de que la decisión quedó guardada.

    El orden importa y es el mismo que usa el consumidor para la deduplicación: la marca se escribe
    después del éxito y nunca antes. Al revés, un almacén que falla dejaría la firma apuntando a una
    decisión que no se persistió, y las miles de repeticiones que vienen detrás copiarían de un
    documento inexistente.

    Solo se registran las concluyentes y tomadas con todas sus consultas. Una decisión que no pasó
    la validación describe un ciclo que salió mal, no una conducta resuelta, y una tomada sin parte
    del contexto está esperando la revisión de alguien: propagar cualquiera de las dos le pondría el
    mismo defecto a todas las repeticiones de la firma en lugar de darles otra oportunidad.

    Y no se re-registra lo que ya vino del repertorio: el `doc_id` de origen tiene que seguir siendo
    el del evento que efectivamente se razonó, o la cadena de auditoría apunta a una copia.
    """
    if repertorio is None or estado.get("reutilizada_de"):
        return
    firma = estado.get("firma")
    decision = estado.get("decision")
    if not firma or decision is None or resultado_del_ciclo(estado) is not None:
        return
    if consultas_fallidas(estado):
        return
    evento = estado["evento"]
    repertorio.registrar(firma, decision.model_dump(mode="json"), evento.doc_id)
