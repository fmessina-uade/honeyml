import type { ArchetypeData, FingerprintData, Snapshot } from '../lib/api';
import { compacto, dec } from '../lib/format';
import { useI18n } from '../lib/i18n';
import type { LeccionId } from './lecciones';
import { NOT_OBSERVED, OBSERVED } from './sections/MitreMatrix';
import { nombreDelServicio } from './sections/Protocols';
import { tacticColor } from './sections/SessionReplay';

const ANCHO = 400;
const ALTO = 230;

/**
 * La vista previa de una sección en el desplegable de la barra: su gráfico en miniatura, dibujado
 * con los mismos datos que la sección y sin pedir nada nuevo. Cumple el papel que en un sitio
 * comercial cumple una foto, pero dice algo: quien pasa el puntero ya ve la forma del resultado.
 */
export default function Miniatura({
  id,
  color,
  snapshot,
  familias,
  arquetipos,
}: {
  id: LeccionId;
  color: string;
  snapshot: Snapshot;
  familias: FingerprintData | null;
  arquetipos: ArchetypeData | null;
}) {
  switch (id) {
    case 'pulso':
      return <Curva snapshot={snapshot} color={color} />;
    case 'protocolos':
      return <Barras snapshot={snapshot} color={color} />;
    case 'origen':
      return <Globo snapshot={snapshot} color={color} />;
    case 'diccionario':
      return <Nube snapshot={snapshot} color={color} />;
    case 'huellas':
      return <Panal familias={familias} color={color} />;
    case 'arquetipos':
      return <Circulos arquetipos={arquetipos} color={color} />;
    case 'anatomia':
      return <Consola color={color} />;
    case 'mitre':
      return <Cadena />;
  }
}

function Lienzo({ children }: { children: React.ReactNode }) {
  return (
    <svg viewBox={`0 0 ${ANCHO} ${ALTO}`} className="w-full h-full" aria-hidden>
      {children}
    </svg>
  );
}

/** El pulso: la captura diaria entera, con el pico marcado. */
function Curva({ snapshot, color }: { snapshot: Snapshot; color: string }) {
  const serie = snapshot.timeline.map((d) => d.count);
  const max = Math.max(...serie, 1);
  const paso = ANCHO / Math.max(serie.length - 1, 1);
  const y = (v: number) => ALTO - 18 - (v / max) * (ALTO - 50);
  const linea = serie.map((v, i) => `${i ? 'L' : 'M'}${(i * paso).toFixed(1)} ${y(v).toFixed(1)}`);
  const pico = serie.indexOf(max);
  return (
    <Lienzo>
      <defs>
        <linearGradient id="mini-curva" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={color} stopOpacity="0.45" />
          <stop offset="1" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={`${linea.join(' ')} L${ANCHO} ${ALTO} L0 ${ALTO} Z`} fill="url(#mini-curva)" />
      <path d={linea.join(' ')} fill="none" stroke={color} strokeWidth="1.6" />
      <circle cx={pico * paso} cy={y(max)} r="4" fill={color} />
      <circle cx={pico * paso} cy={y(max)} r="9" fill="none" stroke={color} strokeOpacity="0.4" />
    </Lienzo>
  );
}

/** Más allá de SSH: los servicios del sensor de red, con escala de raíz para que SMB no tape al resto. */
function Barras({ snapshot, color }: { snapshot: Snapshot; color: string }) {
  const filas = snapshot.protocol_detail
    .filter((p) => p.sources > 0)
    .sort((a, b) => b.count - a.count)
    .slice(0, 6);
  const max = Math.sqrt(filas[0]?.count ?? 1);
  return (
    <div className="w-full h-full flex flex-col justify-center gap-2.5 px-1">
      {filas.map((f, i) => (
        <div key={f.protocol} className="flex items-center gap-3">
          <span className="font-data text-[10.5px] text-white/55 w-16 shrink-0 truncate">
            {nombreDelServicio(f.protocol)}
          </span>
          <span className="flex-1 h-3.5 rounded-sm bg-white/[0.04] overflow-hidden">
            <span
              className="block h-full rounded-sm"
              style={{
                width: `${Math.max(4, (Math.sqrt(f.count) / max) * 100)}%`,
                background: color,
                opacity: 1 - i * 0.12,
              }}
            />
          </span>
          <span className="font-data text-[10px] text-white/45 w-11 text-right">
            {compacto(f.count)}
          </span>
        </div>
      ))}
    </div>
  );
}

/** De dónde vienen: un globo de alambre con los países como puntos, del tamaño de su tráfico. */
function Globo({ snapshot, color }: { snapshot: Snapshot; color: string }) {
  const cx = ANCHO / 2;
  const cy = ALTO / 2 + 4;
  const r = 100;
  const lon0 = (-40 * Math.PI) / 180;
  const lat0 = (24 * Math.PI) / 180;
  const paises = (snapshot.geography?.countries ?? []).filter(
    (c) => c.lat != null && c.lon != null,
  );
  const max = Math.max(...paises.map((c) => c.count), 1);
  const puntos = paises.flatMap((c) => {
    const lat = ((c.lat as number) * Math.PI) / 180;
    const lon = ((c.lon as number) * Math.PI) / 180 - lon0;
    const visible = Math.sin(lat0) * Math.sin(lat) + Math.cos(lat0) * Math.cos(lat) * Math.cos(lon);
    if (visible <= 0) return [];
    return [
      {
        iso: c.iso,
        x: cx + r * Math.cos(lat) * Math.sin(lon),
        y:
          cy -
          r * (Math.cos(lat0) * Math.sin(lat) - Math.sin(lat0) * Math.cos(lat) * Math.cos(lon)),
        radio: 2.5 + 9 * Math.sqrt(c.count / max),
      },
    ];
  });
  return (
    <Lienzo>
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="currentColor" strokeOpacity="0.18" />
      {[-60, -30, 0, 30, 60].map((g) => (
        <ellipse
          key={`m${g}`}
          cx={cx}
          cy={cy}
          rx={r * Math.abs(Math.sin(((g + 90) * Math.PI) / 180))}
          ry={r}
          fill="none"
          stroke="currentColor"
          strokeOpacity="0.09"
        />
      ))}
      {[-50, -20, 10, 40, 70].map((g) => {
        const y = cy - r * Math.sin(((g - 10) * Math.PI) / 180);
        const ancho = r * Math.cos(((g - 10) * Math.PI) / 180);
        return (
          <line
            key={`p${g}`}
            x1={cx - ancho}
            x2={cx + ancho}
            y1={y}
            y2={y}
            stroke="currentColor"
            strokeOpacity="0.09"
          />
        );
      })}
      {puntos.map((p) => (
        <g key={p.iso}>
          <circle cx={p.x} cy={p.y} r={p.radio * 1.9} fill={color} fillOpacity="0.12" />
          <circle cx={p.x} cy={p.y} r={p.radio} fill={color} fillOpacity="0.75" />
        </g>
      ))}
    </Lienzo>
  );
}

/** El diccionario: las contraseñas más probadas, del tamaño de sus intentos. */
function Nube({ snapshot, color }: { snapshot: Snapshot; color: string }) {
  const claves = snapshot.credentials.passwords.slice(0, 10);
  const max = Math.sqrt(claves[0]?.count ?? 1);
  return (
    <div className="w-full h-full flex flex-wrap content-center justify-center items-baseline gap-x-4 gap-y-1 px-4">
      {claves.map((c, i) => (
        <span
          key={c.key}
          className="font-data leading-tight"
          style={{
            fontSize: `${12 + 22 * (Math.sqrt(c.count) / max)}px`,
            color: i < 3 ? color : 'rgb(var(--tinta) / 0.55)',
          }}
        >
          {c.key}
        </span>
      ))}
    </div>
  );
}

/** Las huellas: un panal donde cada celda es una parte de las sesiones, pintada por familia. */
function Panal({ familias, color }: { familias: FingerprintData | null; color: string }) {
  const columnas = 9;
  const filas = 5;
  const total = columnas * filas;
  const ordenadas = familias ? [...familias.families].sort((a, b) => b.sessions - a.sessions) : [];
  const sesiones = familias?.total_sessions || 1;
  const primera = Math.round(((ordenadas[0]?.sessions ?? 0) / sesiones) * total);
  const segunda = Math.round(((ordenadas[1]?.sessions ?? 0) / sesiones) * total);
  const w = 38;
  const h = 44;
  const hexagono = (x: number, y: number) =>
    `M${x} ${y - h / 2} L${x + w / 2} ${y - h / 4} L${x + w / 2} ${y + h / 4} L${x} ${y + h / 2} L${x - w / 2} ${y + h / 4} L${x - w / 2} ${y - h / 4} Z`;
  const celdas = Array.from({ length: total }, (_, i) => {
    const fila = Math.floor(i / columnas);
    const col = i % columnas;
    const x = 40 + col * w + (fila % 2 ? w / 2 : 0);
    const y = 50 + fila * h * 0.75;
    const tono = i < primera ? 1 : i < primera + segunda ? 0.45 : 0;
    return { x, y, tono };
  });
  return (
    <Lienzo>
      {celdas.map((c, i) => (
        <path
          key={i}
          d={hexagono(c.x, c.y)}
          fill={c.tono ? color : 'none'}
          fillOpacity={c.tono * 0.8}
          stroke={c.tono ? color : 'currentColor'}
          strokeOpacity={c.tono ? 0.9 : 0.14}
        />
      ))}
    </Lienzo>
  );
}

/** Los tipos de atacante: un círculo por grupo, del área de su porcentaje, uno dentro del otro. */
function Circulos({ arquetipos, color }: { arquetipos: ArchetypeData | null; color: string }) {
  const { t } = useI18n();
  const perfiles = [...(arquetipos?.perfiles ?? [])].sort((a, b) => b.porcentaje - a.porcentaje);
  const base = ALTO - 14;
  const rMax = 96;
  const cx = 128;
  const rotulo = 236;
  return (
    <Lienzo>
      {perfiles.map((p, i) => {
        const radio = Math.max(7, rMax * Math.sqrt(p.porcentaje / 100));
        const ultimo = i === perfiles.length - 1;
        const nombre =
          (t.archetypes.groups as Record<string, { name: string }>)[p.nombre]?.name ?? p.nombre;
        return (
          <g key={p.nombre}>
            <circle
              cx={cx}
              cy={base - radio}
              r={radio}
              fill={ultimo ? 'var(--agent-coral)' : color}
              fillOpacity={ultimo ? 0.9 : 0.08 + i * 0.1}
              stroke={ultimo ? 'var(--agent-coral)' : color}
              strokeOpacity="0.6"
            />
            <line
              x1={cx + (ultimo ? radio : radio * 0.7)}
              x2={rotulo - 6}
              y1={base - radio * (ultimo ? 1 : 1.7)}
              y2={base - radio * (ultimo ? 1 : 1.7)}
              stroke="currentColor"
              strokeOpacity="0.2"
            />
            <text
              x={rotulo}
              y={base - radio * (ultimo ? 1 : 1.7) + 4}
              fontSize="11.5"
              fill="currentColor"
              fillOpacity="0.7"
              fontFamily="Geist, Inter, sans-serif"
            >
              {nombre} {dec(p.porcentaje, 1)}%
            </text>
          </g>
        );
      })}
    </Lienzo>
  );
}

/** La anatomía: una consola abstracta, sin comandos reales, con la línea que se está reproduciendo. */
function Consola({ color }: { color: string }) {
  const lineas = [0.62, 0.38, 0.8, 0.5, 0.7, 0.3];
  return (
    <Lienzo>
      <rect
        x="30"
        y="18"
        width="340"
        height="194"
        rx="10"
        fill="currentColor"
        fillOpacity="0.04"
        stroke="currentColor"
        strokeOpacity="0.14"
      />
      {[0, 1, 2].map((i) => (
        <circle key={i} cx={48 + i * 13} cy="34" r="3.5" fill="currentColor" fillOpacity="0.2" />
      ))}
      {lineas.map((l, i) => (
        <g key={i}>
          <text x="48" y={70 + i * 24} fontSize="12" fill={color} fontFamily="Fira Code, monospace">
            $
          </text>
          <rect
            x="64"
            y={61 + i * 24}
            width={270 * l}
            height="9"
            rx="2"
            fill={i === 4 ? color : 'currentColor'}
            fillOpacity={i === 4 ? 0.85 : 0.14}
          />
        </g>
      ))}
      <rect
        x={64 + 270 * 0.7 + 6}
        y={157}
        width="7"
        height="11"
        fill={color}
        className="terminal-cursor"
      />
    </Lienzo>
  );
}

/** MITRE: la cadena de ocho tácticas, encendidas las que el señuelo observa. */
function Cadena() {
  const { t } = useI18n();
  const cadena = [...OBSERVED, ...NOT_OBSERVED];
  return (
    <div className="w-full h-full grid grid-cols-4 gap-2 content-center px-2">
      {cadena.map((tactica) => {
        const vista = (OBSERVED as readonly string[]).includes(tactica);
        const c = tacticColor(tactica);
        return (
          <div
            key={tactica}
            className="rounded-lg px-2 py-3 text-[10.5px] leading-tight text-center"
            style={{
              background: vista ? `color-mix(in srgb, ${c} 16%, transparent)` : 'transparent',
              boxShadow: `inset 0 0 0 1px ${vista ? `color-mix(in srgb, ${c} 50%, transparent)` : 'rgb(var(--tinta) / 0.12)'}`,
              color: vista ? c : 'rgb(var(--tinta) / 0.35)',
              borderStyle: vista ? undefined : 'dashed',
            }}
          >
            {t.tactics[tactica as keyof typeof t.tactics]?.name ?? tactica}
          </div>
        );
      })}
    </div>
  );
}
