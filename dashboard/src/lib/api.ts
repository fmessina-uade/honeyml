// Client for the HoneyML API. Vite proxies /api to the FastAPI service in dev.

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
  /** English copy, served by the API so the language toggle also covers the replay. */
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
  /** Events whose source resolved to a country / to an autonomous system. The free MaxMind
   *  databases do not know every address, so these bound every percentage in the section. */
  with_geo: number;
  with_asn: number;
  countries: CountryOrigin[];
  autonomous_systems: AsOrigin[];
}

export interface ArchetypeTrait {
  caracteristica: string;
  columna: string;
  /** Distance from the population mean, in standard deviations. */
  desvios: number;
  direccion: 'alto' | 'bajo';
}

export interface Archetype {
  grupo: number;
  /** Derived from the profile, never from the cluster number, which KMeans does not keep stable. */
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
  /** Optional: a snapshot frozen before geographic enrichment existed will not carry it. */
  geography?: Geography;
  weekly_rhythm?: WeeklyRhythm;
  generated_at?: string;
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`/api${path}`);
  if (!res.ok) {
    // La API explica en `detail` por qué no puede responder —típicamente qué falta levantar—, y
    // ese texto es lo único accionable que tiene el lector. Quedarse con el número de estado
    // convierte una instrucción en un código.
    const detalle = await res
      .json()
      .then((b: { detail?: string }) => b?.detail)
      .catch(() => undefined);
    throw new Error(detalle ?? `${path}: ${res.status}`);
  }
  return res.json() as Promise<T>;
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
};
