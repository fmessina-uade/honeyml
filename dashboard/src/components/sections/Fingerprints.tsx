import { useState } from 'react';
import { ChevronDown, Users, Repeat } from 'lucide-react';
import type { FingerprintData } from '../../lib/api';
import { tacticColor } from './SessionReplay';
import Reveal from '../Reveal';
import { n, pct } from '../../lib/format';
import { useI18n } from '../../lib/i18n';

/**
 * Sessions grouped by byte-identical command sequence.
 *
 * This is the section that turns "we captured a lot of attacks" into "we captured a few programs,
 * many times". A family is a set of sessions whose commands match exactly — a strict definition
 * that cannot group things by accident, so every family shown is real.
 */
export default function Fingerprints({ data }: { data: FingerprintData }) {
  const { t, lang } = useI18n();
  const [open, setOpen] = useState<number | null>(0);

  const share = pct(data.grouped_sessions, data.total_sessions, 0);
  const max = Math.max(...data.families.map((f) => f.sessions), 1);

  const tacticName = (key: string) => t.tactics[key as keyof typeof t.tactics]?.name ?? key;
  const fmtDate = (iso?: string) =>
    iso
      ? new Date(iso).toLocaleDateString(lang === 'en' ? 'en-GB' : 'es-AR', {
          day: 'numeric',
          month: 'short',
        })
      : '—';

  return (
    <section className="flex flex-col gap-4">
      {/* The headline: most of the traffic is a handful of scripts */}
      <Reveal>
        <div className="grid sm:grid-cols-3 gap-3">
          <div className="tile rounded-xl ring-1 ring-white/5 bg-white/[0.03] p-4">
            <span className="tile-glow" style={{ background: 'var(--honey-amber)' }} />
            <div className="relative">
              <div className="flex items-center gap-2 text-white/35">
                <Repeat className="w-3.5 h-3.5" />
                <span className="text-[9px] uppercase tracking-wider">
                  {t.fingerprints.sessionsLabel}
                </span>
              </div>
              <div className="font-data text-2xl text-white mt-2">{n(data.total_sessions)}</div>
              <div className="text-[10px] text-white/40 mt-1">{t.fingerprints.withCommands}</div>
            </div>
          </div>

          <div className="tile rounded-xl ring-1 ring-white/5 bg-white/[0.03] p-4">
            <span className="tile-glow" style={{ background: 'var(--agent-coral)' }} />
            <div className="relative">
              <div className="flex items-center gap-2 text-white/35">
                <Users className="w-3.5 h-3.5" />
                <span className="text-[9px] uppercase tracking-wider">
                  {t.fingerprints.familiesLabel}
                </span>
              </div>
              <div className="font-data text-2xl text-white mt-2">{n(data.families_found)}</div>
              <div className="text-[10px] text-white/40 mt-1">{t.fingerprints.identical}</div>
            </div>
          </div>

          <div className="tile rounded-xl ring-1 ring-white/5 bg-white/[0.03] p-4">
            <span className="tile-glow" style={{ background: 'var(--neural-teal)' }} />
            <div className="relative">
              <div className="text-[9px] uppercase tracking-wider text-white/35">
                {t.fingerprints.coverageLabel}
              </div>
              <div className="font-data text-2xl text-white mt-2">{share}%</div>
              <div className="text-[10px] text-white/40 mt-1">
                {t.fingerprints.grouped(n(data.grouped_sessions))}
              </div>
            </div>
          </div>
        </div>
      </Reveal>

      <Reveal delay={100}>
        <div className="rounded-xl ring-1 ring-white/5 bg-white/[0.03] p-4">
          <div className="text-[11px] text-white/60 leading-relaxed max-w-3xl">
            {t.fingerprints.lesson}
          </div>
        </div>
      </Reveal>

      {/* Each family, expandable to its exact script */}
      <div className="flex flex-col gap-2">
        {data.families.map((f, i) => {
          const isOpen = open === i;
          return (
            <Reveal key={f.label} delay={Math.min(i * 50, 300)}>
              <div className="rounded-xl ring-1 ring-white/5 bg-white/[0.03] overflow-hidden">
                <button
                  onClick={() => setOpen(isOpen ? null : i)}
                  className="w-full text-left p-4 hover:bg-white/[0.02] transition"
                >
                  <div className="flex items-center justify-between gap-3 flex-wrap">
                    <div className="flex items-center gap-2.5">
                      <ChevronDown
                        className={`w-3.5 h-3.5 text-white/30 transition-transform ${
                          isOpen ? 'rotate-180' : ''
                        }`}
                      />
                      <span className="font-data text-[12px] text-white/85">{f.label}</span>
                      <div className="flex items-center gap-1">
                        {f.tactics.map((tac) => (
                          <span
                            key={tac}
                            title={tacticName(tac)}
                            className="w-1.5 h-1.5 rounded-full"
                            style={{ background: tacticColor(tac) }}
                          />
                        ))}
                      </div>
                    </div>
                    <div className="flex items-center gap-4 font-data text-[10px] text-white/45">
                      <span>
                        <span className="text-white/80">{n(f.sessions)}</span>{' '}
                        {t.fingerprints.sessions}
                      </span>
                      <span>
                        <span className="text-white/80">{n(f.sources)}</span>{' '}
                        {t.fingerprints.sources}
                      </span>
                      <span className="text-white/25 hidden sm:inline">
                        {fmtDate(f.first_seen)} → {fmtDate(f.last_seen)}
                      </span>
                    </div>
                  </div>

                  <div className="h-1 rounded bg-white/5 mt-2.5 overflow-hidden">
                    <div
                      className="h-1 rounded transition-all duration-700"
                      style={{
                        width: `${(f.sessions / max) * 100}%`,
                        background: 'var(--honey-amber)',
                      }}
                    />
                  </div>

                  {/* sessions per source is the tell: many repeats from few machines */}
                  <div className="text-[10px] text-white/35 mt-1.5">
                    {t.fingerprints.perSource(
                      (f.sessions / (f.sources || 1)).toLocaleString(
                        lang === 'en' ? 'en-GB' : 'es-AR',
                        { maximumFractionDigits: 1 },
                      ),
                    )}
                  </div>
                </button>

                {isOpen && (
                  <div className="section-in border-t border-white/5 bg-[#0f141b] p-4">
                    <div className="text-[8px] uppercase tracking-wider text-white/30 mb-2">
                      {t.fingerprints.script}
                    </div>
                    <div className="font-data text-[11px] flex flex-col gap-1.5">
                      {f.commands.map((c, k) => (
                        <div key={k} className="flex gap-2">
                          <span className="text-white/25 select-none">{k + 1}</span>
                          <span className="text-white/70 break-all">{c}</span>
                        </div>
                      ))}
                      {f.truncated && (
                        <div className="text-white/25 mt-1">
                          {t.fingerprints.truncated(f.total_commands)}
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </Reveal>
          );
        })}
      </div>
    </section>
  );
}
