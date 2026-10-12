import { Brain, Database, Search, type LucideIcon } from 'lucide-react';
import type { FilaDecision } from '../../lib/api';
import { useI18n } from '../../lib/i18n';

// La escala del motor, de menor a mayor. Es la de `severidad.py`, y el panel la necesita para
// ordenar y para que el analista corrija con los mismos niveles.
export const SEVERIDADES = ['informativo', 'bajo', 'medio', 'alto', 'critico'] as const;

// Con variables de la paleta, así cada nivel se ajusta solo al tema.
export const COLOR_DE_SEVERIDAD: Record<string, string> = {
  informativo: 'var(--ghost-slate)',
  bajo: 'var(--neural-teal)',
  medio: 'var(--honey-amber)',
  alto: 'var(--agent-coral)',
  critico: 'var(--critico)',
};

export const colorDeSeveridad = (s: string | null | undefined) =>
  COLOR_DE_SEVERIDAD[s ?? ''] ?? 'var(--ghost-slate)';

// Cómo pide la API las decisiones sin táctica, en los filtros.
export const SIN_TACTICA = 'ninguna';

// Cowrie escribe el comando en `message` con un prefijo según el tipo de evento, y el pipeline lo
// deja limpio en `process.command_line`. Cuando uno es el otro más el prefijo, mostrar los dos solo
// repite el renglón más largo de la lista. El dato sigue llegando completo desde la API.
const PREFIJO_DE_COWRIE = /^(CMD: |Command (not )?found: )/;

export function sinMensajeRepetido<T>(atributos: Record<string, T>): {
  atributos: Record<string, T>;
  oculto: boolean;
} {
  const comando = atributos['process.command_line'];
  const mensaje = atributos['message'];
  const repite =
    typeof comando === 'string' &&
    typeof mensaje === 'string' &&
    mensaje.replace(PREFIJO_DE_COWRIE, '') === comando;
  if (!repite) return { atributos, oculto: false };
  return {
    atributos: Object.fromEntries(Object.entries(atributos).filter(([k]) => k !== 'message')),
    oculto: true,
  };
}

// Sin táctica, el motor dice por qué: no es lo mismo un `cd` que un comando ilegible o una
// descarga que ninguna táctica del vocabulario describe. Las decisiones anteriores al motivo no lo
// traen y quedan con el rótulo solo.
export function sinTacticaConMotivo(
  t: ReturnType<typeof useI18n>['t'],
  motivo: string | null | undefined,
): string {
  const razon = motivo ? t.triage.noTacticReason[motivo] : undefined;
  return razon ? `${t.triage.noTactic} (${razon})` : t.triage.noTactic;
}

export function NotaMensajeOculto() {
  const { t } = useI18n();
  return <p className="font-data text-[10px] text-white/40 mt-2">{t.triage.messageHidden}</p>;
}

export function ChipSeveridad({
  severidad,
  grande = false,
}: {
  severidad: string | null | undefined;
  grande?: boolean;
}) {
  const { t } = useI18n();
  const tam = grande ? 'text-[12px] px-2.5 py-1' : 'text-[10px] px-1.5 py-0.5';
  if (!severidad) {
    return (
      <span className={`rounded ${tam} text-white/45 ring-1 ring-white/15`}>
        {t.triage.notConcluded}
      </span>
    );
  }
  const color = colorDeSeveridad(severidad);
  return (
    <span
      className={`rounded ${tam} font-medium first-letter:uppercase whitespace-nowrap`}
      style={{
        color,
        boxShadow: `inset 0 0 0 1px ${color}`,
        background: `color-mix(in srgb, ${color} 10%, transparent)`,
      }}
    >
      {t.severities[severidad as keyof typeof t.severities] ?? severidad}
    </span>
  );
}

/** Por qué camino del grafo salió una decisión: el atajo de memoria, el modelo o el corte. */
export function caminoDe(d: Pick<FilaDecision, 'copiada' | 'motivo_de_corte'>): {
  icono: LucideIcon;
  color: string;
  clave: 'memory' | 'full' | 'noContext';
} {
  if (d.copiada) return { icono: Database, color: 'var(--neural-teal)', clave: 'memory' };
  if (d.motivo_de_corte === 'sin_contexto') {
    return { icono: Search, color: 'var(--ghost-slate)', clave: 'noContext' };
  }
  return { icono: Brain, color: 'var(--agent-coral)', clave: 'full' };
}
