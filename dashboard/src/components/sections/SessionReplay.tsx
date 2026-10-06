import { useCallback, useEffect, useRef, useState } from 'react';
import { Play, Pause, RotateCcw, Terminal, Gauge, Search } from 'lucide-react';
import type { Replay } from '../../lib/api';
import { useI18n } from '../../lib/i18n';
import ManoAlzada from '../ManoAlzada';
import { Palabras } from '../Titular';

// Una táctica, un color, reutilizado en todo el panel.
const TACTIC_COLOR: Record<string, string> = {
  Descubrimiento: 'var(--honey-amber)',
  Ejecución: 'var(--agent-coral)',
  Persistencia: 'var(--neural-teal)',
  'Evasión de defensas': 'var(--violeta)',
  'Acceso a credenciales': 'var(--celeste)',
  'Acceso inicial': 'var(--rosa)',
};

export function tacticColor(tactic: string): string {
  return TACTIC_COLOR[tactic] ?? 'var(--ghost-slate)';
}

const SPEEDS = [
  { label: '0,5x', ms: 4400 },
  { label: '1x', ms: 2200 },
  { label: '2x', ms: 1100 },
];

// El paso que se anota a mano es el primero de la táctica más grave que aparece en la sesión: el
// momento en que el atacante deja de mirar y empieza a quedarse.
const GRAVEDAD = ['Persistencia', 'Evasión de defensas', 'Ejecución', 'Descubrimiento'];

/**
 * Lo que un gráfico no puede hacer: una intrusión real capturada, repasada comando por comando,
 * explicando qué buscaba el atacante en cada paso.
 *
 * La reproducción se puede arrastrar y manejar con el teclado. Quien lee esto quiere frenar en un
 * comando y releerlo, y con reproducción automática sola eso es una carrera contra el reloj.
 */
export default function SessionReplay({ replays }: { replays: Replay[] }) {
  const { t, lang } = useI18n();
  const [selected, setSelected] = useState(0);
  const [step, setStep] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [speed, setSpeed] = useState(1);
  const [filter, setFilter] = useState('');
  const scrollRef = useRef<HTMLDivElement>(null);

  const replay = replays[selected];
  const total = replay?.steps.length ?? 0;

  useEffect(() => {
    if (!playing || step >= total) return;
    const id = setTimeout(() => setStep((s) => s + 1), SPEEDS[speed].ms);
    return () => clearTimeout(id);
  }, [playing, step, total, speed]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [step]);

  const seek = useCallback(
    (to: number) => {
      setStep(Math.max(0, Math.min(to, total - 1)));
      setPlaying(false);
    },
    [total],
  );

  // Espacio alterna, las flechas avanzan. Acotado a la sección para no secuestrar la página entera.
  const onKeyDown = (e: React.KeyboardEvent) => {
    if ((e.target as HTMLElement).tagName === 'INPUT') return;
    if (e.key === ' ') {
      e.preventDefault();
      setPlaying((p) => !p);
    } else if (e.key === 'ArrowRight') {
      e.preventDefault();
      seek(step + 1);
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault();
      seek(step - 1);
    }
  };

  function pick(i: number) {
    setSelected(i);
    setStep(0);
    setPlaying(true);
  }

  if (!replay) {
    return (
      <div className="panel p-8 text-center">
        <div className="text-[13px] text-white/60">{t.replay.empty}</div>
        <div className="text-[11px] text-white/35 mt-1">{t.replay.emptyHint}</div>
      </div>
    );
  }

  // el índice viaja al lado, así elegir sigue seleccionando la sesión correcta después de filtrar
  const q = filter.trim().toLowerCase();
  const visible = replays
    .map((r, i) => ({ r, i }))
    .filter(
      ({ r }) =>
        !q ||
        r.attacker.toLowerCase().includes(q) ||
        r.credentials.user.toLowerCase().includes(q) ||
        r.credentials.password.toLowerCase().includes(q) ||
        r.tactics.some((x) => x.toLowerCase().includes(q)),
    );

  const current = replay.steps[Math.min(step, total - 1)];
  const done = step >= total - 1;
  const tacticName = (key: string) => t.tactics[key as keyof typeof t.tactics]?.name ?? key;

  // Las tácticas de la sesión en el orden en que aparecen: es la leyenda de la cinta.
  const enOrden = replay.steps
    .map((s) => s.tactic)
    .filter((tac, i, todas) => todas.indexOf(tac) === i);

  const tacticaDelGiro = GRAVEDAD.find((tac) => enOrden.includes(tac));
  const pasoDelGiro = tacticaDelGiro
    ? replay.steps.findIndex((s) => s.tactic === tacticaDelGiro)
    : -1;
  const xGiro = total ? ((pasoDelGiro + 0.5) / total) * 100 : 50;
  const giroALaIzquierda = xGiro > 55;

  return (
    <section className="flex flex-col gap-14 outline-none" tabIndex={0} onKeyDown={onKeyDown}>
      {/* La presentación es la escena misma: el título arriba y la terminal como imagen */}
      <div className="presentacion presentacion-escena">
        <div className="relative max-w-[1320px] mx-auto px-4 md:px-8 pt-12 sm:pt-16 pb-10">
          <div className="grid lg:grid-cols-[minmax(0,1fr)_minmax(0,0.85fr)] gap-6 lg:gap-12 items-end mb-8">
            <div className="min-w-0">
              <span className="ceja section-in">{t.replay.heroBadge(replays.length)}</span>
              <h1 className="titular-landing mt-5">
                <Palabras texto={t.nav.anatomia} />
              </h1>
            </div>
            <p className="portada-bajada section-in lg:pb-2">{t.lead.anatomia}</p>
          </div>

          {/* La terminal */}
          <div className="impreso escena-terminal rounded-2xl overflow-hidden min-w-0">
            <div className="flex items-center justify-between bg-[var(--impreso-cabecera)] border-b border-white/5 px-3 sm:px-4 py-2.5 gap-2 flex-wrap">
              <div className="flex items-center gap-2 text-[11px] text-white/60 min-w-0">
                <span className="flex gap-1 shrink-0" aria-hidden>
                  <span className="w-2 h-2 rounded-full bg-white/10" />
                  <span className="w-2 h-2 rounded-full bg-white/10" />
                  <span className="w-2 h-2 rounded-full bg-white/10" />
                </span>
                <Terminal className="w-3.5 h-3.5 shrink-0 ml-1" />
                <span className="font-data truncate">
                  {replay.attacker}@honeypot ({replay.protocol})
                </span>
              </div>
              <div className="flex items-center gap-2">
                <div className="flex items-center rounded-md bg-white/5 p-0.5">
                  <Gauge className="w-3 h-3 text-white/30 mx-1" />
                  {SPEEDS.map((s, i) => (
                    <button
                      key={s.label}
                      onClick={() => setSpeed(i)}
                      className={`rounded px-1.5 py-0.5 text-[9px] font-data transition ${
                        i === speed
                          ? 'bg-white/10 text-white/85'
                          : 'text-white/40 hover:text-white/70'
                      }`}
                    >
                      {s.label}
                    </button>
                  ))}
                </div>
                <button
                  onClick={() => setPlaying((p) => !p)}
                  className="flex items-center gap-1.5 rounded-md bg-white/5 hover:bg-white/10 px-2.5 py-1 text-[10px] text-white/70 transition"
                >
                  {playing ? <Pause className="w-3 h-3" /> : <Play className="w-3 h-3" />}
                  {playing ? t.replay.pause : t.replay.play}
                </button>
                <button
                  onClick={() => {
                    setStep(0);
                    setPlaying(true);
                  }}
                  className="flex items-center gap-1.5 rounded-md bg-white/5 hover:bg-white/10 px-2.5 py-1 text-[10px] text-white/70 transition"
                >
                  <RotateCcw className="w-3 h-3" />
                  {t.replay.restart}
                </button>
              </div>
            </div>

            <div
              ref={scrollRef}
              className="thin-scroll h-[340px] sm:h-[420px] overflow-y-auto p-4 sm:p-5 font-data text-[12.5px]"
            >
              <div className="text-[var(--neural-teal)] mb-3">
                <span className="text-white/40">$</span> ssh {replay.credentials.user}@honeypot
                <div className="text-white/40 mt-1">
                  {t.replay.accessGranted(replay.credentials.user, replay.credentials.password)}
                </div>
              </div>

              {replay.steps.slice(0, step + 1).map((s, i) => (
                <div key={i} className={`mb-3 ${i === step ? 'row-enter' : ''}`}>
                  <button
                    onClick={() => seek(i)}
                    className="flex gap-2 text-left w-full group"
                    title={t.replay.goToStep}
                  >
                    <span style={{ color: tacticColor(s.tactic) }}>$</span>
                    <span
                      className={`break-all transition-colors ${
                        i === step ? 'text-white/90' : 'text-white/45 group-hover:text-white/70'
                      }`}
                    >
                      {s.command}
                    </span>
                  </button>
                  {i === step && (
                    <div
                      className="mt-1.5 ml-4 pl-3 border-l-2 text-[11px] text-white/55 leading-relaxed"
                      style={{ borderColor: tacticColor(s.tactic) }}
                    >
                      {lang === 'en' && s.what_en ? s.what_en : s.what}
                    </div>
                  )}
                </div>
              ))}

              {/* El cursor es lo que hace que se lea como una terminal viva y no como un bloque de
              código. */}
              <div className="flex gap-2">
                <span className="text-white/40">$</span>
                {done && !playing ? (
                  <span className="text-white/30">{t.replay.sessionEnded}</span>
                ) : (
                  <span className="terminal-cursor" />
                )}
              </div>
            </div>

            {/* La cinta de la sesión: un tramo por comando, del color de su táctica. Se toca un tramo
            para ir a ese paso, y la anotación marca dónde el ataque cambia de naturaleza. */}
            <div className="border-t border-white/5 px-3 sm:px-4 pt-1 pb-3">
              <div className="relative pt-10">
                <div className="flex gap-[2px] h-3.5 items-end">
                  {replay.steps.map((s, i) => (
                    <button
                      key={i}
                      onClick={() => seek(i)}
                      aria-label={t.replay.step(i + 1, total)}
                      aria-current={i === step ? 'step' : undefined}
                      className="flex-1 min-w-[3px] rounded-[2px] transition-all duration-300 hover:opacity-100"
                      style={{
                        background: tacticColor(s.tactic),
                        opacity: i === step ? 1 : i < step ? 0.7 : 0.18,
                        height: i === step ? '100%' : '55%',
                        boxShadow: i === step ? `0 0 10px ${tacticColor(s.tactic)}` : undefined,
                      }}
                    />
                  ))}
                </div>
                {pasoDelGiro >= 0 && tacticaDelGiro && (
                  <ManoAlzada
                    key={selected}
                    trazos={[
                      {
                        tipo: 'elipse',
                        x: xGiro,
                        y: 86,
                        ancho: Math.max((100 / total) * 2.4, 4),
                        alto: 62,
                      },
                      {
                        tipo: 'flecha',
                        desde: [giroALaIzquierda ? xGiro - 7 : xGiro + 7, 30],
                        hasta: [giroALaIzquierda ? xGiro - 1.5 : xGiro + 1.5, 66],
                        curva: giroALaIzquierda ? -0.3 : 0.3,
                      },
                    ]}
                    notas={[
                      {
                        x: giroALaIzquierda ? xGiro - 8 : xGiro + 8,
                        y: -6,
                        texto: t.replay.turn(pasoDelGiro + 1, t.replay.turnWhat[tacticaDelGiro]),
                        alinear: giroALaIzquierda ? 'derecha' : 'izquierda',
                        ancho: 280,
                      },
                    ]}
                  />
                )}
              </div>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-2.5">
                {enOrden.map((tac) => (
                  <span key={tac} className="flex items-center gap-1.5 text-[10px] text-white/45">
                    <span className="w-2 h-2 rounded-sm" style={{ background: tacticColor(tac) }} />
                    {tacticName(tac)}
                  </span>
                ))}
              </div>
              <div className="flex justify-between gap-3 mt-2 text-[9px] text-white/35">
                <span>
                  <span className="font-data">
                    {t.replay.step(Math.min(step + 1, total), total)}
                  </span>
                  <span className="text-white/20 ml-2 hidden sm:inline">{t.replay.keys}</span>
                </span>
                <span className="font-data">{replay.timestamp?.slice(0, 10)}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* La mitad educativa: qué hizo en este paso y por qué, como nota al margen */}
      <div className="pliego grid lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)] gap-6 lg:gap-14">
        <div className="min-w-0">
          <span className="ceja">{t.replay.phase}</span>
          <div
            key={current.tactic}
            className="titular-tactica section-in mt-4"
            style={{ color: tacticColor(current.tactic) }}
          >
            {tacticName(current.tactic)}
          </div>
          <div className="flex items-center gap-4 mt-4 text-[11px] text-white/45">
            <span className="font-data">{t.replay.step(Math.min(step + 1, total), total)}</span>
            {current.technique && (
              <a
                href={`https://attack.mitre.org/techniques/${current.technique.replace('.', '/')}/`}
                target="_blank"
                rel="noopener noreferrer"
                className="font-data text-white/55 hover:text-[var(--honey-amber)] transition underline decoration-dotted underline-offset-2"
                title={t.replay.seeInMitre}
              >
                {current.technique}
              </a>
            )}
          </div>
        </div>
        <div key={step} className="section-in min-w-0">
          <p className="geist text-[17px] text-white/90 leading-relaxed tracking-tight">
            {lang === 'en' && current.what_en ? current.what_en : current.what}
          </p>
          <div className="rotulo mt-5 mb-1.5">{t.replay.why}</div>
          <p className="text-[13px] text-white/60 leading-relaxed">
            {lang === 'en' && current.why_en ? current.why_en : current.why}
          </p>
        </div>
      </div>

      {/* Las otras sesiones, en una grilla abierta con su buscador */}
      <div className="pliego">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div className="flex flex-col gap-3">
            <span className="ceja">{t.replay.attackers(replays.length)}</span>
            <h2 className="titulo-bloque">{t.replay.others}</h2>
          </div>
          <div className="relative w-full sm:w-72">
            <Search className="w-3.5 h-3.5 text-white/30 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder={t.replay.search}
              className="w-full rounded-full bg-white/[0.04] ring-1 ring-white/10 focus:ring-white/25
                         pl-8 pr-3 py-2 text-[12px] text-white/80 placeholder:text-white/30
                         outline-none transition font-data"
            />
          </div>
        </div>
        <div className="thin-scroll grid sm:grid-cols-2 lg:grid-cols-3 gap-x-8 mt-6 max-h-[420px] overflow-y-auto pr-1">
          {visible.length === 0 && (
            <div className="text-[11px] text-white/35 py-3">{t.replay.noMatch}</div>
          )}
          {visible.map(({ r, i }) => (
            <button
              key={r.attacker + i}
              onClick={() => {
                pick(i);
                window.requestAnimationFrame(() =>
                  scrollRef.current?.closest('section')?.scrollIntoView({ behavior: 'smooth' }),
                );
              }}
              data-actual={i === selected ? 'si' : undefined}
              className="sesion-fila"
            >
              <div className="flex items-center justify-between gap-2 min-w-0">
                <span className="font-data text-[11px] text-white/75">{r.attacker}</span>
                <span className="font-data text-[10px] text-white/35 truncate">
                  {r.credentials.user}:{r.credentials.password}
                </span>
              </div>
              {/* La tira de tácticas es lo que distingue a un bot de otro de un vistazo. */}
              <div className="flex items-center gap-1 mt-2">
                {r.tactics.map((tac) => (
                  <span
                    key={tac}
                    title={tacticName(tac)}
                    className="h-1 flex-1 rounded-full"
                    style={{
                      background: tacticColor(tac),
                      opacity: i === selected ? 0.95 : 0.45,
                    }}
                  />
                ))}
                <span className="font-data text-[9.5px] text-white/30 ml-1 shrink-0">
                  {r.steps.length} {t.replay.cmd}
                </span>
              </div>
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}
