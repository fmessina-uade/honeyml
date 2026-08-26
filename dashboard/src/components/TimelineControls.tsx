import { useI18n } from '../lib/i18n';

/**
 * Interval and sensor selectors for the timeline.
 *
 * They sit next to the chart rather than in a global bar on purpose: only the timeline reacts to
 * them, and a control that looks global but changes one chart is worse than no control at all.
 *
 * Both are plain segmented buttons instead of dropdowns. There are three and four options; a
 * dropdown would hide them behind a click and make the current selection harder to read at a
 * glance, which for a panel meant to be looked at rather than operated is the wrong trade.
 */

export type Interval = 'hour' | 'day' | 'week';
export type Sensor = 'todos' | 'cowrie' | 'dionaea';
export type Atajo = 'hoy' | 'ayer' | 'semana' | 'mes' | 'todo';

/**
 * Ranges relative to the last day with data, not to today's clock.
 *
 * "Today" has to mean the last captured day: the panel is often read from a frozen snapshot, or
 * hours after the last pull, and anchoring to the real clock would hand back an empty chart and no
 * explanation for it.
 *
 * Each shortcut also carries the interval that makes it readable — a single day as daily bars is
 * one bar, and three months by the hour is two thousand.
 */
export const ATAJOS: Record<Atajo, { dias: number | null; interval: Interval }> = {
  hoy: { dias: 0, interval: 'hour' },
  ayer: { dias: 1, interval: 'hour' },
  semana: { dias: 6, interval: 'day' },
  mes: { dias: 29, interval: 'day' },
  todo: { dias: null, interval: 'day' },
};

interface Props {
  interval: Interval;
  sensor: Sensor;
  desde: string;
  hasta: string;
  /** Extremos de lo capturado: acotan los selectores para que no se pueda pedir un rango vacío. */
  minimo: string;
  maximo: string;
  onInterval: (i: Interval) => void;
  onSensor: (s: Sensor) => void;
  onRango: (desde: string, hasta: string) => void;
  onAtajo: (a: Atajo) => void;
  /** Cuál de los atajos coincide con el rango actual, para poder marcarlo. */
  atajoActivo: Atajo | null;
  loading: boolean;
}

const INTERVALS: Interval[] = ['hour', 'day', 'week'];
const SENSORS: Sensor[] = ['todos', 'cowrie', 'dionaea'];

function Grupo<T extends string>({
  value,
  options,
  onChange,
  label,
  disabled,
}: {
  value: T;
  options: T[];
  onChange: (v: T) => void;
  label: (v: T) => string;
  disabled: boolean;
}) {
  return (
    <div className="flex rounded-lg ring-1 ring-white/10 bg-white/[0.03] p-0.5">
      {options.map((o) => (
        <button
          key={o}
          onClick={() => onChange(o)}
          disabled={disabled}
          aria-pressed={value === o}
          className={`px-2 py-1 rounded-md text-[10px] transition-colors disabled:opacity-40 ${
            value === o ? 'bg-white/10 text-white/90' : 'text-white/40 hover:text-white/70'
          }`}
        >
          {label(o)}
        </button>
      ))}
    </div>
  );
}

const fecha =
  'bg-transparent text-[10px] text-white/70 font-data outline-none ' +
  '[color-scheme:dark] disabled:opacity-40';

export default function TimelineControls({
  interval,
  sensor,
  desde,
  hasta,
  minimo,
  maximo,
  onInterval,
  onSensor,
  onRango,
  onAtajo,
  atajoActivo,
  loading,
}: Props) {
  const { t } = useI18n();

  return (
    <div className="flex flex-col gap-2">
      {/* Los atajos van primero porque son lo que se usa: elegir dos fechas a mano es la salida
          para el caso raro, no el camino principal. */}
      <div className="flex gap-1.5 flex-wrap">
        {(Object.keys(ATAJOS) as Atajo[]).map((a) => (
          <button
            key={a}
            onClick={() => onAtajo(a)}
            disabled={loading}
            aria-pressed={atajoActivo === a}
            className={`px-2.5 py-1 rounded-full text-[10px] ring-1 transition-colors disabled:opacity-40 ${
              atajoActivo === a
                ? 'ring-[var(--honey-amber)]/45 bg-[var(--honey-amber)]/15 text-[var(--honey-amber)]'
                : 'ring-white/10 bg-white/[0.03] text-white/45 hover:text-white/80'
            }`}
          >
            {t.controls.shortcut[a]}
          </button>
        ))}
      </div>

      <div className="flex items-center gap-2 flex-wrap">
        <Grupo
          value={interval}
          options={INTERVALS}
          onChange={onInterval}
          label={(i) => t.controls.interval[i]}
          disabled={loading}
        />
        <Grupo
          value={sensor}
          options={SENSORS}
          onChange={onSensor}
          label={(s) => (s === 'todos' ? t.controls.allSensors : s)}
          disabled={loading}
        />

        {/* Los extremos se acotan a lo capturado: un rango fuera de eso devuelve un gráfico vacío
          sin explicar por qué, y el lector no tiene forma de saber que no hay datos ahí. */}
        <div className="flex items-center gap-1.5 rounded-lg ring-1 ring-white/10 bg-white/[0.03] px-2 py-1">
          <input
            type="date"
            value={desde}
            min={minimo}
            max={hasta}
            disabled={loading}
            onChange={(e) => onRango(e.target.value, hasta)}
            className={fecha}
            aria-label={t.controls.from}
          />
          <span className="text-white/25 text-[10px]">→</span>
          <input
            type="date"
            value={hasta}
            min={desde}
            max={maximo}
            disabled={loading}
            onChange={(e) => onRango(desde, e.target.value)}
            className={fecha}
            aria-label={t.controls.to}
          />
        </div>

        {/* The chart keeps showing the previous data while a new range loads, so without this the
            controls would look unresponsive on a slow query. */}
        {loading && (
          <span className="text-[10px] text-white/35 font-data">{t.controls.loading}</span>
        )}
      </div>
    </div>
  );
}
