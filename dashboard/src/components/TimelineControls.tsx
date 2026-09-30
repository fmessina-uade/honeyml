import { useI18n } from '../lib/i18n';

/**
 * Los selectores de intervalo y de sensor de la línea de tiempo.
 *
 * Van al lado del gráfico y no en una barra global a propósito: la línea de tiempo es lo único que
 * reacciona a ellos, y un control que parece global pero cambia un solo gráfico es peor que no
 * tener control.
 *
 * Los dos son botones segmentados y no desplegables. Son tres y cuatro opciones; un desplegable las
 * escondería detrás de un clic y haría más difícil leer de un vistazo qué está elegido, que para un
 * panel pensado para mirarse y no para operarse es el intercambio equivocado.
 */

export type Interval = 'hour' | 'day' | 'week';
export type Sensor = 'todos' | 'cowrie' | 'dionaea';
export type Atajo = 'hoy' | 'ayer' | 'semana' | 'mes' | 'todo';

/**
 * Los rangos son relativos al último día con datos, no al reloj de hoy.
 *
 * "Hoy" tiene que significar el último día capturado: el panel muchas veces se lee desde un
 * respaldo congelado, o unas horas después de la última descarga, y anclarlo al reloj real
 * devolvería un gráfico vacío sin ninguna explicación.
 *
 * Cada atajo lleva además el intervalo que lo hace legible: un solo día en barras diarias es una
 * barra, y tres meses por hora son dos mil.
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
  'bg-transparent text-[10px] text-white/70 font-data outline-none ' + 'disabled:opacity-40';

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
          <span className="text-white/25 text-[10px]">{t.controls.to.toLowerCase()}</span>
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

        {/* Mientras llega el rango nuevo el gráfico sigue mostrando el anterior. Sin este aviso,
            con una consulta lenta los controles parecerían no responder. */}
        {loading && (
          <span className="text-[10px] text-white/35 font-data">{t.controls.loading}</span>
        )}
      </div>
    </div>
  );
}
