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

export interface Snapshot {
  overview: Overview;
  timeline: TimelinePoint[];
  credentials: { users: Bucket[]; passwords: Bucket[] };
  commands: Bucket[];
  protocols: Bucket[];
  stages: Bucket[];
  protocol_detail: ProtocolDetail[];
  hourly: HourPoint[];
  generated_at?: string;
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`/api${path}`);
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json() as Promise<T>;
}

export const api = {
  snapshot: () => get<Snapshot>('/snapshot'),
  overview: () => get<Overview>('/overview'),
  replays: () => get<Replay[]>('/replays'),
  health: () => get<Health>('/health'),
  fingerprints: () => get<FingerprintData>('/fingerprints'),
  passwordCheck: (prefix: string) =>
    get<PasswordCheckResult>(`/password-check?prefix=${encodeURIComponent(prefix)}`),
};
