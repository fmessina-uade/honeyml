import {
  Activity,
  BookOpen,
  Fingerprint,
  Globe,
  Grid3x3,
  LayoutDashboard,
  Network,
  Radar,
  ScrollText,
  ShieldCheck,
  Terminal,
  UserCog,
  Users,
  type LucideIcon,
} from 'lucide-react';
import type { ArchetypeData, FingerprintData, Snapshot } from '../lib/api';
import { compacto, dec, n, nombreDePais, pct } from '../lib/format';
import type { Dict } from '../lib/translations';
import { NOT_OBSERVED, OBSERVED } from './sections/MitreMatrix';
import { nombreDelServicio } from './sections/Protocols';

// Cada sección con su ícono y su color. Están en el orden narrativo de la portada: primero la
// escala, después una intrusión concreta, después toda la superficie, la evidencia detrás del
// consejo y al final el marco formal.
export const SECCIONES = {
  inicio: { icon: LayoutDashboard, color: 'var(--honey-amber)' },
  triaje: { icon: ShieldCheck, color: 'var(--agent-coral)' },
  pulso: { icon: Radar, color: 'var(--honey-amber)' },
  anatomia: { icon: Terminal, color: 'var(--agent-coral)' },
  protocolos: { icon: Network, color: 'var(--neural-teal)' },
  diccionario: { icon: BookOpen, color: 'var(--honey-amber)' },
  huellas: { icon: Fingerprint, color: 'var(--agent-coral)' },
  arquetipos: { icon: Users, color: 'var(--ghost-slate)' },
  origen: { icon: Globe, color: 'var(--neural-teal)' },
  mitre: { icon: Grid3x3, color: 'var(--violeta)' },
  // Las de administración no son lecciones: no están en la portada ni en los desplegables, se llega
  // desde el menú de la cuenta y solo con el rol que las ve.
  cuentas: { icon: UserCog, color: 'var(--neural-teal)' },
  auditoria: { icon: ScrollText, color: 'var(--honey-amber)' },
  envivo: { icon: Activity, color: 'var(--agent-coral)' },
} as const satisfies Record<string, { icon: LucideIcon; color: string }>;

export type SectionId = keyof typeof SECCIONES;
export type AdminId = 'cuentas' | 'auditoria' | 'envivo';
export type LeccionId = Exclude<SectionId, 'inicio' | 'triaje' | AdminId>;

export const LECCIONES: readonly LeccionId[] = [
  'pulso',
  'anatomia',
  'protocolos',
  'diccionario',
  'huellas',
  'arquetipos',
  'origen',
  'mitre',
];

// Los desplegables de la barra agrupan las lecciones por la pregunta que contestan: qué llega,
// quién lo manda y qué hace adentro.
export const MENUS = [
  { id: 'captura', secciones: ['pulso', 'protocolos', 'origen'] },
  { id: 'atacantes', secciones: ['diccionario', 'huellas', 'arquetipos'] },
  { id: 'intrusion', secciones: ['anatomia', 'mitre'] },
] as const satisfies readonly { id: string; secciones: readonly LeccionId[] }[];

export type MenuId = (typeof MENUS)[number]['id'];

export interface Leccion {
  cifra: string;
  texto: string;
}

/**
 * Una cifra por sección de aprendizaje, la que resume su lección. La usan la portada y la vista
 * previa del menú, así las dos dicen lo mismo que se encuentra al entrar a la sección.
 */
export function lecciones(
  snapshot: Snapshot,
  familias: FingerprintData | null,
  arquetipos: ArchetypeData | null,
  sesiones: number,
  t: Dict,
): Record<LeccionId, Leccion> {
  const h = t.home;
  const o = snapshot.overview;
  const vectores = snapshot.protocol_detail.filter((d) => d.sources > 5);
  const insistente = [...vectores].sort(
    (a, b) => b.count / (b.sources || 1) - a.count / (a.sources || 1),
  )[0];
  const usuario = snapshot.credentials.users[0];
  const pais = snapshot.geography?.countries
    .filter((c) => c.sources > 0)
    .sort((a, b) => b.count / b.sources - a.count / a.sources)[0];
  const familia = familias
    ? [...familias.families].sort((a, b) => b.sessions - a.sessions)[0]
    : null;
  const intrusion = arquetipos?.perfiles.find((p) => p.nombre === 'Intrusión efectiva');
  const dias = snapshot.timeline.filter((d) => d.count > 0).length;

  return {
    pulso: { cifra: compacto(o.events), texto: h.cards.pulso(dias) },
    anatomia: { cifra: n(sesiones), texto: h.cards.anatomia },
    protocolos: {
      cifra: insistente ? n(Math.round(insistente.count / (insistente.sources || 1))) : '—',
      texto: insistente ? h.cards.protocolos(nombreDelServicio(insistente.protocol)) : '',
    },
    diccionario: {
      cifra: usuario ? compacto(usuario.count) : '—',
      texto: usuario ? h.cards.diccionario(usuario.key) : '',
    },
    huellas: {
      cifra: familia && familias ? `${pct(familia.sessions, familias.total_sessions, 0)}%` : '—',
      texto: h.cards.huellas,
    },
    arquetipos: {
      cifra: intrusion ? `${dec(intrusion.porcentaje, 1)}%` : '—',
      texto: h.cards.arquetipos,
    },
    origen: {
      cifra: pais ? n(Math.round(pais.count / pais.sources)) : '—',
      texto: pais ? h.cards.origen(nombreDePais(pais.iso, pais.country)) : '',
    },
    mitre: {
      cifra: `${OBSERVED.length} / ${OBSERVED.length + NOT_OBSERVED.length}`,
      texto: h.cards.mitre,
    },
  };
}
