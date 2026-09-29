// Cliente de la API de HoneyML. En desarrollo, Vite hace proxy de /api al servicio FastAPI.

export interface Overview {
  events: number;
  unique_ips: number;
  logins: number;
  logins_success: number;
  commands: number;
  by_sensor: Record<string, number>;
  first_event: string;
  last_event: string;
}

export interface Bucket {
  key: string;
  count: number;
}

export interface TimelinePoint {
  date: string;
  count: number;
  cowrie?: number;
  dionaea?: number;
}

export interface ReplayStep {
  command: string;
  what: string;
  why: string;
  /** El texto en inglés, servido por la API para que el selector de idioma cubra también el replay. */
  what_en: string;
  why_en: string;
  tactic: string;
  technique: string;
}

export interface Replay {
  attacker: string;
  protocol: string;
  timestamp: string;
  credentials: { user: string; password: string };
  tactics: string[];
  steps: ReplayStep[];
}

export interface ProtocolDetail {
  protocol: string;
  count: number;
  sources: number;
  port: number | null;
}

export interface HourPoint {
  hour: number;
  count: number;
  logins: number;
}

export interface Family {
  label: string;
  sessions: number;
  sources: number;
  commands: string[];
  truncated: boolean;
  total_commands: number;
  tactics: string[];
  first_seen?: string;
  last_seen?: string;
}

export interface FingerprintData {
  families: Family[];
  total_sessions: number;
  families_found: number;
  grouped_sessions: number;
}

export interface PasswordCheckResult {
  prefix: string;
  matches: { suffix: string; count: number }[];
  distinct: number;
  attempts: number;
}

export interface Health {
  status: string;
  mode: 'live' | 'snapshot' | 'none';
  generated_at?: string;
}

export interface WeeklyRhythm {
  /** [día][hora], lunes en 0. Totales crudos. */
  total: number[][];
  /** Promedio por hora observada: la ventana de captura no cubre la misma cantidad de cada día. */
  average: number[][];
  /** Cuántas veces se observó cada celda, para poder leer el promedio con criterio. */
  observed: number[][];
}

export interface CountryOrigin {
  country: string;
  iso: string;
  count: number;
  sources: number;
  /** Centroide de las direcciones observadas en ese país. Puede faltar si ninguna resolvió. */
  lat?: number | null;
  lon?: number | null;
}

export interface AsOrigin {
  organization: string;
  count: number;
  sources: number;
}

export interface Geography {
  events: number;
  /** Eventos cuyo origen se pudo resolver a un país o a un sistema autónomo. Las bases gratuitas
   *  de MaxMind no conocen todas las direcciones, así que estos acotan cada porcentaje de la
   *  sección. */
  with_geo: number;
  with_asn: number;
  countries: CountryOrigin[];
  autonomous_systems: AsOrigin[];
}

export interface ArchetypeTrait {
  caracteristica: string;
  columna: string;
  /** Distancia respecto de la media de la población, en desvíos estándar. */
  desvios: number;
  direccion: 'alto' | 'bajo';
}

export interface Archetype {
  grupo: number;
  /** Sale del perfil y nunca del número de grupo, que KMeans no mantiene estable entre corridas. */
  nombre: string;
  descripcion: string;
  direcciones: number;
  porcentaje: number;
  rasgos: ArchetypeTrait[];
  mediana_eventos: number;
  mediana_intentos_acceso: number;
  pct_ejecuto_comandos: number;
  pct_descargo_archivo: number;
  pct_logro_acceso: number;
}

export interface ArchetypeData {
  direcciones_analizadas: number;
  caracteristicas: number;
  grupos: number;
  perfiles: Archetype[];
}

export interface Snapshot {
  overview: Overview;
  timeline: TimelinePoint[];
  credentials: { users: Bucket[]; passwords: Bucket[] };
  commands: Bucket[];
  protocols: Bucket[];
  stages: Bucket[];
  protocol_detail: ProtocolDetail[];
  hourly: HourPoint[];
  /** Opcional: un respaldo congelado antes de que existiera el enriquecimiento geográfico no lo trae. */
  geography?: Geography;
  weekly_rhythm?: WeeklyRhythm;
  generated_at?: string;
}

/** Lo que el motor de triaje decidió, en números. Sale de `/api/decisiones/resumen`. */
export interface ResumenTriaje {
  total: number;
  razonadas: number;
  copiadas: number;
  corregidas_por_el_motor: number;
  no_concluyentes: number;
  costo_usd: number;
  por_severidad: Bucket[];
  por_tactica: Bucket[];
  por_sensor: Bucket[];
  por_modelo: Bucket[];
  revision: {
    requieren: number;
    pendientes: number;
    revisadas: number;
    confirmadas: number;
    corregidas: number;
  };
  /** Si el motor está trabajando: su última decisión y cuántas tomó en la última hora. */
  actividad: {
    ultima: string | null;
    ultima_hora: number;
    copiadas_ultima_hora: number;
  };
  /** Desde que ocurrió el evento hasta que su decisión quedó guardada, en segundos. */
  conclusion: {
    ventana_dias: number;
    decisiones: number;
    mediana_s: number | null;
    p90_s: number | null;
  };
}

export type Veredicto = 'confirma' | 'corrige';

export interface Revision {
  '@timestamp': string;
  doc_id: string;
  veredicto: Veredicto;
  severidad: string | null;
  tactica_mitre: string | null;
  nota: string;
  /** La clasificación del motor tal como estaba cuando se revisó. */
  motor: {
    severidad: string | null;
    tactica_mitre: string | null;
    concluyente: boolean | null;
    requiere_revision: boolean;
    consultas_fallidas: string[];
  };
}

export interface FilaDecision {
  doc_id: string;
  momento: string | null;
  decidida: string | null;
  sensor: string | null;
  categoria: string | null;
  resultado: string | null;
  protocolo: string | null;
  origen: string | null;
  resumen: string | null;
  severidad: string | null;
  tactica_mitre: string | null;
  confianza: number | null;
  concluyente: boolean | null;
  copiada: boolean;
  requiere_revision: boolean;
  consultas_fallidas: string[];
  intentos: number;
  rechazos: number;
  motivo_de_corte: string | null;
  retriaje: boolean;
  modelo: string | null;
  segundos: number | null;
  costo_usd: number | null;
  /** Los nodos del grafo por los que pasó, en orden y con las vueltas por reproche incluidas. */
  camino: NodoDelGrafo[];
  revision: Revision | null;
}

export type NodoDelGrafo =
  'memoria' | 'contexto' | 'historial' | 'inferencia' | 'validacion' | 'persistencia';

export interface ListadoDecisiones {
  total: number;
  items: FilaDecision[];
}

/** El documento de `honeyml-decisiones`, tal como lo escribe el nodo de persistencia. */
export interface DocumentoDecision {
  '@timestamp': string;
  evento: {
    doc_id: string;
    momento: string | null;
    sensor: string | null;
    categoria: string | null;
    accion: string | null;
    resultado: string | null;
    protocolo: string | null;
    origen: string | null;
    sesion: string | null;
    resumen: string | null;
  };
  decision: {
    piso: string;
    techo: string;
    concluyente: boolean;
    severidad?: string;
    confianza?: number;
    tactica_mitre?: string | null;
    justificacion?: string;
    evidencia?: string[];
  };
  ciclo: {
    motivo_de_corte: string | null;
    intentos: number;
    rechazos: number;
    reproches: string[];
    firma: string | null;
    reutilizada_de: string | null;
    consultas_fallidas?: string[];
    requiere_revision?: boolean;
    retriaje?: boolean;
  };
  modelo: {
    nombre?: string;
    proveedor?: string;
    tokens_entrada?: number;
    tokens_salida?: number;
    segundos?: number;
    costo_usd?: number;
  };
}

export interface DetalleDecision {
  doc_id: string;
  decision: DocumentoDecision;
  camino: NodoDelGrafo[];
  /** Los atributos normalizados del evento, o null si su índice de telemetría ya se rotó. */
  evento: Record<string, string | number | string[]> | null;
  revision: Revision | null;
}

export interface FiltrosDecisiones {
  estado: 'todas' | 'pendientes' | 'revisadas';
  severidad?: string;
  tactica?: string;
  sensor?: string;
  desde: number;
  tamano: number;
  /** Por defecto, por momento del evento; `decision` sigue al motor en vivo. */
  orden?: 'evento' | 'decision';
  /** Solo las que pasaron por el modelo, sin las copias del repertorio. */
  razonadas?: boolean;
}

export interface VeredictoNuevo {
  veredicto: Veredicto;
  severidad?: string | null;
  tactica_mitre?: string | null;
  nota?: string;
}

async function leer<T>(path: string, res: Response): Promise<T> {
  if (!res.ok) {
    // La API explica en `detail` por qué no puede responder (típicamente qué falta levantar), y
    // ese texto es lo único accionable que tiene el lector. Quedarse con el número de estado
    // convierte una instrucción en un código. Un 422 de validación trae una lista y no un texto.
    const detalle = await res
      .json()
      .then((b: { detail?: string | { msg: string }[] }) =>
        Array.isArray(b?.detail) ? b.detail.map((d) => d.msg).join('; ') : b?.detail,
      )
      .catch(() => undefined);
    throw new Error(detalle ?? `${path}: ${res.status}`);
  }
  return res.json() as Promise<T>;
}

async function get<T>(path: string): Promise<T> {
  return leer<T>(path, await fetch(`/api${path}`));
}

async function put<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return leer<T>(path, res);
}

export const api = {
  snapshot: () => get<Snapshot>('/snapshot'),
  overview: () => get<Overview>('/overview'),
  replays: () => get<Replay[]>('/replays'),
  health: () => get<Health>('/health'),
  fingerprints: () => get<FingerprintData>('/fingerprints'),
  geography: () => get<Geography>('/geography'),
  timeline: (interval: string, sensor?: string, desde?: string, hasta?: string) => {
    const q = new URLSearchParams({ interval });
    if (sensor && sensor !== 'todos') q.set('sensor', sensor);
    if (desde) q.set('desde', desde);
    // El fin de día, no su comienzo: con la fecha pelada, Elasticsearch corta a las 00:00 y el
    // último día elegido quedaría fuera del rango que el usuario cree haber pedido.
    if (hasta) q.set('hasta', `${hasta}T23:59:59`);
    return get<TimelinePoint[]>(`/timeline?${q}`);
  },
  archetypes: () => get<ArchetypeData>('/archetypes'),
  passwordCheck: (prefix: string) =>
    get<PasswordCheckResult>(`/password-check?prefix=${encodeURIComponent(prefix)}`),
  triaje: () => get<ResumenTriaje>('/decisiones/resumen'),
  decisiones: (f: FiltrosDecisiones) => {
    const q = new URLSearchParams({
      estado: f.estado,
      desde: String(f.desde),
      tamano: String(f.tamano),
    });
    if (f.severidad) q.set('severidad', f.severidad);
    if (f.tactica) q.set('tactica', f.tactica);
    if (f.sensor) q.set('sensor', f.sensor);
    if (f.orden) q.set('orden', f.orden);
    if (f.razonadas) q.set('razonadas', 'true');
    return get<ListadoDecisiones>(`/decisiones?${q}`);
  },
  decision: (docId: string) => get<DetalleDecision>(`/decisiones/${encodeURIComponent(docId)}`),
  revisar: (docId: string, v: VeredictoNuevo) =>
    put<Revision>(`/decisiones/${encodeURIComponent(docId)}/revision`, v),
};
