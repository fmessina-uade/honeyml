import { useEffect, useState } from 'react';
import {
  Activity,
  ArrowRight,
  Fingerprint,
  ShieldCheck,
  Terminal,
  Workflow,
  type LucideIcon,
} from 'lucide-react';
import {
  api,
  type ArchetypeData,
  type FingerprintData,
  type ResumenTriaje,
  type Snapshot,
} from '../../lib/api';
import { dec, duracion, n, pct } from '../../lib/format';
import { useI18n } from '../../lib/i18n';
import { LECCIONES, SECCIONES, lecciones, type SectionId } from '../lecciones';
import CountUp from '../CountUp';
import Latido from '../Latido';
import Reveal from '../Reveal';
import { Hexagono, Indicador } from '../Instrumento';

const MINUTOS_ACTIVO = 10;
const REFRESCO_MS = 15000;

interface Tarjeta {
  id: SectionId;
  icono: LucideIcon;
  color: string;
  cifra: string;
  texto: string;
}

/**
 * La portada del panel: lo que llega, lo que decide el motor y por dónde seguir.
 *
 * No agrega datos propios. Cada cifra sale de lo mismo que usa la sección a la que lleva, así la
 * portada no puede decir algo distinto de lo que se encuentra al entrar.
 */
export default function Inicio({
  snapshot,
  familias,
  arquetipos,
  sesiones,
  onIr,
}: {
  snapshot: Snapshot;
  familias: FingerprintData | null;
  arquetipos: ArchetypeData | null;
  sesiones: number;
  onIr: (id: SectionId) => void;
}) {
  const { t } = useI18n();
  const h = t.home;
  const [motor, setMotor] = useState<ResumenTriaje | null>(null);
  const [sinMotor, setSinMotor] = useState(false);
  const [ahora, setAhora] = useState(() => Date.now());

  useEffect(() => {
    let vivo = true;
    const traer = () =>
      api
        .triaje()
        .then((r) => {
          if (!vivo) return;
          setMotor(r);
          setSinMotor(false);
        })
        .catch(() => vivo && setSinMotor(true));
    traer();
    const id = window.setInterval(() => {
      traer();
      setAhora(Date.now());
    }, REFRESCO_MS);
    return () => {
      vivo = false;
      window.clearInterval(id);
    };
  }, []);

  const o = snapshot.overview;
  const ultima = motor?.actividad.ultima;
  const hace = ultima ? Math.max(0, (ahora - new Date(ultima).getTime()) / 1000) : null;
  const activo = hace !== null && hace < MINUTOS_ACTIVO * 60;

  const dias = snapshot.timeline.filter((d) => d.count > 0).length;
  const cifras = lecciones(snapshot, familias, arquetipos, sesiones, t);
  const tarjetas: Tarjeta[] = LECCIONES.map((id) => ({
    id,
    icono: SECCIONES[id].icon,
    color: SECCIONES[id].color,
    ...cifras[id],
  }));

  return (
    <section className="flex flex-col gap-4">
      {/* El motor, arriba de todo: es lo que el proyecto agrega */}
      <Reveal>
        <div className="motor relative overflow-hidden rounded-2xl ring-1 ring-white/10 p-4 sm:p-5">
          <div
            aria-hidden
            className="absolute -top-24 -left-16 w-[420px] h-[300px] rounded-full pointer-events-none"
            style={{
              background: 'radial-gradient(circle, rgba(255,107,53,0.18), transparent 65%)',
              filter: 'blur(40px)',
            }}
          />
          <div className="relative grid lg:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)] gap-5 items-center">
            <div className="flex flex-col gap-3">
              <div className="flex items-center gap-2.5">
                <Hexagono color="var(--agent-coral)">
                  <Workflow className="w-3.5 h-3.5" />
                </Hexagono>
                <span className="rotulo">{h.engineTitle}</span>
              </div>
              {motor ? (
                <>
                  <div className="flex items-center gap-2.5">
                    <span className="relative flex w-2.5 h-2.5">
                      {activo && (
                        <span className="absolute inline-flex h-full w-full rounded-full bg-[#ff6b35] opacity-60 animate-ping" />
                      )}
                      <span
                        className="relative inline-flex w-2.5 h-2.5 rounded-full"
                        style={{
                          background: activo ? 'var(--agent-coral)' : 'var(--motor-apagado)',
                        }}
                      />
                    </span>
                    <span className="font-mono-display text-[15px] text-white">
                      {activo ? t.triage.engine.active : t.triage.engine.idle}
                    </span>
                    {hace !== null && (
                      <span className="font-data text-[10.5px] text-white/45">
                        {t.triage.engine.lastAgo(duracion(hace))}
                      </span>
                    )}
                  </div>
                  <div className="grid grid-cols-3 gap-2">
                    {[
                      [n(motor.actividad.ultima_hora), h.lastHour],
                      [
                        motor.conclusion.mediana_s !== null
                          ? duracion(motor.conclusion.mediana_s)
                          : '—',
                        h.toDecision,
                      ],
                      [n(motor.revision.pendientes), h.pending],
                    ].map(([valor, texto]) => (
                      <div
                        key={texto}
                        className="rounded-lg bg-white/[0.04] ring-1 ring-white/[0.07] p-2.5"
                      >
                        <div className="cifra-chica">{valor}</div>
                        <div className="text-[10px] text-white/45 mt-0.5 leading-snug">{texto}</div>
                      </div>
                    ))}
                  </div>
                  <p className="text-[11.5px] text-white/60 leading-relaxed">
                    {h.engineLine(
                      n(motor.total),
                      pct(motor.copiadas, motor.total, 1),
                      dec(motor.costo_usd, 2),
                    )}
                  </p>
                  <button
                    onClick={() => onIr('triaje')}
                    className="group self-start flex items-center gap-2 rounded-lg px-3.5 py-2 text-[12px] font-medium bg-[#ff6b35]/15 text-[var(--motor-acento)] ring-1 ring-[#ff6b35]/40 hover:bg-[#ff6b35]/25 transition"
                  >
                    <ShieldCheck className="w-4 h-4" />
                    {h.openEngine}
                    <ArrowRight className="w-3.5 h-3.5 transition-transform group-hover:translate-x-0.5" />
                  </button>
                </>
              ) : (
                <p className="text-[12px] text-white/50">
                  {sinMotor ? t.triage.liveOnly : t.loading}
                </p>
              )}
            </div>
            {motor?.actividad.por_minuto?.length ? (
              <div className="min-w-0">
                <Latido serie={motor.actividad.por_minuto} alto={96} />
              </div>
            ) : (
              !motor && <div className="h-[96px] rounded-lg bg-white/[0.02]" />
            )}
          </div>
        </div>
      </Reveal>

      {/* La captura, en cuatro números */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Reveal>
          <Indicador
            icono={Activity}
            rotulo={t.pulse.events}
            valor={<CountUp end={o.events} />}
            sub={t.pulse.inDays(dias)}
            color="var(--honey-amber)"
          />
        </Reveal>
        <Reveal delay={60}>
          <Indicador
            icono={Fingerprint}
            rotulo={t.pulse.addresses}
            valor={<CountUp end={o.unique_ips} />}
            sub={h.distinctOrigins}
            color="var(--neural-teal)"
          />
        </Reveal>
        <Reveal delay={120}>
          <Indicador
            icono={ShieldCheck}
            rotulo={t.pulse.logins}
            valor={<CountUp end={o.logins} />}
            sub={t.pulse.gotIn(n(o.logins_success))}
            color="var(--agent-coral)"
          />
        </Reveal>
        <Reveal delay={180}>
          <Indicador
            icono={Terminal}
            rotulo={t.pulse.commands}
            valor={<CountUp end={o.commands} />}
            sub={t.pulse.insideDecoy}
            color="var(--honey-amber)"
          />
        </Reveal>
      </div>

      {/* Por dónde seguir: una tarjeta por sección, con la cifra que resume su lección */}
      <Reveal delay={120}>
        <div className="flex items-baseline justify-between gap-3 mt-2 mb-1">
          <span className="rotulo">{h.learnTitle}</span>
          <span className="text-[11px] text-white/40">{h.learnHint}</span>
        </div>
        <div className="grid sm:grid-cols-2 xl:grid-cols-4 gap-3">
          {tarjetas.map((c) => (
            <button
              key={c.id}
              onClick={() => onIr(c.id)}
              className="panel group relative overflow-hidden p-4 text-left transition hover:bg-white/[0.05]"
            >
              <span
                className="absolute inset-x-0 top-0 h-px"
                style={{
                  background: `linear-gradient(90deg, transparent, ${c.color}, transparent)`,
                }}
              />
              <div className="flex items-center justify-between gap-2">
                <span className="flex items-center gap-2.5 min-w-0">
                  <Hexagono color={c.color}>
                    <c.icono className="w-3.5 h-3.5" />
                  </Hexagono>
                  <span className="titulo text-[12px] leading-snug">{t.nav[c.id]}</span>
                </span>
                <ArrowRight className="w-3.5 h-3.5 text-white/25 transition group-hover:text-white/70 group-hover:translate-x-0.5 shrink-0" />
              </div>
              <div className="cifra mt-3" style={{ color: c.color }}>
                {c.cifra}
              </div>
              <div className="text-[11px] text-white/50 mt-1 leading-snug">{c.texto}</div>
            </button>
          ))}
        </div>
      </Reveal>
    </section>
  );
}
