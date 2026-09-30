import { useCallback, useEffect, useRef, useState } from 'react';
import { api, type FilaDecision, type ResumenTriaje } from './api';

// Cada cuánto se pregunta si el motor decidió algo nuevo, y cada cuánto se refresca el resumen aunque
// no haya llegado nada: la ventana de la última hora tiene que seguir corriendo.
const SONDEO_MS = 4000;
const RESUMEN_MS = 30000;
const VENTANA = 30;

export interface Llegada {
  /** Crece con cada tanda nueva. Quien la escucha reacciona cuando cambia. */
  serie: number;
  filas: FilaDecision[];
}

/**
 * El motor en vivo para toda la sección de triaje, desde un solo sondeo.
 *
 * Una sola consulta detecta lo nuevo y, cuando llega algo, refresca el resumen en el acto: el grafo,
 * los números, el gráfico por minuto y el listado cambian juntos. Con un sondeo por parte, cada una
 * a su ritmo, se vería una decisión recorriendo el grafo con los contadores todavía viejos.
 */
export function useMotorEnVivo() {
  const [resumen, setResumen] = useState<ResumenTriaje | null>(null);
  const [recientes, setRecientes] = useState<FilaDecision[]>([]);
  const [llegada, setLlegada] = useState<Llegada>({ serie: 0, filas: [] });
  const [error, setError] = useState<string | null>(null);
  // Null hasta la primera respuesta: lo que ya estaba decidido al abrir no cuenta como llegada.
  const conocidas = useRef<Set<string> | null>(null);

  const cargarResumen = useCallback(
    () =>
      api
        .triaje()
        .then((r) => {
          setResumen(r);
          setError(null);
        })
        .catch((e) => setError(String(e.message ?? e))),
    [],
  );

  useEffect(() => {
    let vivo = true;
    const traer = () =>
      api
        .decisiones({ estado: 'todas', desde: 0, tamano: VENTANA, orden: 'decision' })
        .then((l) => {
          if (!vivo) return;
          setRecientes(l.items);
          if (conocidas.current === null) {
            conocidas.current = new Set(l.items.map((d) => d.doc_id));
            return;
          }
          const vistas = conocidas.current;
          const nuevas = l.items.filter((d) => !vistas.has(d.doc_id));
          if (!nuevas.length) return;
          nuevas.forEach((d) => vistas.add(d.doc_id));
          setLlegada((anterior) => ({ serie: anterior.serie + 1, filas: nuevas }));
          cargarResumen();
        })
        .catch((e) => vivo && setError(String(e.message ?? e)));

    cargarResumen();
    traer();
    const sondeo = window.setInterval(traer, SONDEO_MS);
    const lento = window.setInterval(cargarResumen, RESUMEN_MS);
    return () => {
      vivo = false;
      window.clearInterval(sondeo);
      window.clearInterval(lento);
    };
  }, [cargarResumen]);

  return { resumen, recientes, llegada, error, recargarResumen: cargarResumen };
}
