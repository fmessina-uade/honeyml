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

interface Props {
  interval: Interval;
  sensor: Sensor;
  onInterval: (i: Interval) => void;
  onSensor: (s: Sensor) => void;
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

export default function TimelineControls({
  interval,
  sensor,
  onInterval,
  onSensor,
  loading,
}: Props) {
  const { t } = useI18n();

  return (
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
      {/* The chart keeps showing the previous data while a new range loads, so without this the
          controls would look unresponsive on a slow query. */}
      {loading && <span className="text-[10px] text-white/35 font-data">{t.controls.loading}</span>}
    </div>
  );
}
