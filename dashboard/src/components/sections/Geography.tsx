import { useState } from 'react';
import { Globe as GlobeIcon, Server } from 'lucide-react';
import Globo from '../Globe';
import type { Geography as GeoData } from '../../lib/api';
import Reveal from '../Reveal';
import { n, pct } from '../../lib/format';
import { useI18n } from '../../lib/i18n';

/**
 * Where the attacks come from — by country, and by the network that actually operates the address.
 *
 * The country alone is the weaker half. What separates a rented server from a home connection is
 * the autonomous system, so both are shown side by side and the section is written around the
 * comparison rather than around a ranking of flags.
 */

/** Regional indicator symbols from the ISO code: no flag assets, no external requests. */
function flag(iso: string): string {
  if (iso.length !== 2) return '🏳️';
  return String.fromCodePoint(...[...iso.toUpperCase()].map((c) => 0x1f1a5 + c.charCodeAt(0)));
}

export default function Geography({ data }: { data: GeoData }) {
  const { t } = useI18n();
  // Un solo país seleccionado a la vez: el globo gira hasta él y la fila queda resaltada. Volver a
  // tocarlo deselecciona y el giro continuo se retoma.
  const [pais, setPais] = useState<string | null>(null);

  const maxPais = Math.max(...data.countries.map((c) => c.count), 1);
  const maxAs = Math.max(...data.autonomous_systems.map((a) => a.count), 1);

  // Events per address is the tell: a country can lead on volume and still be a handful of hosts.
  //
  // Formatted with the project's helper and not with toLocaleString directly: that one falls back
  // to the browser's locale, which produced "1,537" right next to "252.137" in the same line. The
  // helper follows the language toggle, so both numbers agree.
  const porDireccion = (count: number, sources: number) => n(Math.round(count / (sources || 1)));

  return (
    <section className="flex flex-col gap-4">
      <Reveal>
        <div className="rounded-xl ring-1 ring-white/5 bg-white/[0.03] p-4">
          <div className="text-[11px] text-white/60 leading-relaxed">{t.geography.lesson}</div>
        </div>
      </Reveal>

      {/* The globe and the table are one control: selecting in either drives the other. */}
      <Reveal delay={60}>
        <div className="rounded-xl ring-1 ring-white/5 bg-white/[0.03] p-4">
          <div className="grid md:grid-cols-[minmax(0,320px)_1fr] gap-4 items-center">
            <div className="aspect-square w-full max-w-[320px] mx-auto">
              <Globo countries={data.countries} selected={pais} onSelect={setPais} />
            </div>
            <div className="text-[11px] text-white/55 leading-relaxed">
              {pais ? t.geography.selected(pais) : t.geography.pickHint}
            </div>
          </div>
        </div>
      </Reveal>

      <div className="grid lg:grid-cols-2 gap-3">
        {/* by country */}
        <Reveal delay={80}>
          <div className="rounded-xl ring-1 ring-white/5 bg-white/[0.03] p-4 h-full">
            <div className="flex items-center gap-2 text-white/35 mb-3">
              <GlobeIcon className="w-3.5 h-3.5" />
              <span className="text-[9px] uppercase tracking-wider">{t.geography.byCountry}</span>
            </div>
            <div className="flex flex-col gap-2.5">
              {data.countries.map((c) => {
                const activo = pais === c.country;
                return (
                  <button
                    key={c.country}
                    onClick={() => setPais(activo ? null : c.country)}
                    className={`text-left rounded-lg -mx-1.5 px-1.5 py-1 transition-colors ${
                      activo ? 'bg-white/[0.06]' : 'hover:bg-white/[0.03]'
                    }`}
                  >
                    <div className="flex items-baseline justify-between gap-2">
                      <span
                        className={`text-[11px] truncate ${activo ? 'text-white' : 'text-white/80'}`}
                      >
                        <span className="mr-1.5">{flag(c.iso)}</span>
                        {c.country}
                      </span>
                      <span className="font-data text-[10px] text-white/45 shrink-0">
                        {n(c.count)}
                        <span className="text-white/25">
                          {' '}
                          · {n(c.sources)} {t.geography.addresses}
                        </span>
                      </span>
                    </div>
                    <div className="h-1 rounded bg-white/5 mt-1 overflow-hidden">
                      <div
                        className="h-1 rounded transition-all duration-700"
                        style={{
                          width: `${(c.count / maxPais) * 100}%`,
                          background: activo ? 'var(--agent-coral)' : 'var(--neural-teal)',
                        }}
                      />
                    </div>
                    <div className="text-[9px] text-white/30 mt-0.5">
                      {t.geography.perAddress(porDireccion(c.count, c.sources))}
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        </Reveal>

        {/* by autonomous system */}
        <Reveal delay={160}>
          <div className="rounded-xl ring-1 ring-white/5 bg-white/[0.03] p-4 h-full">
            <div className="flex items-center gap-2 text-white/35 mb-3">
              <Server className="w-3.5 h-3.5" />
              <span className="text-[9px] uppercase tracking-wider">{t.geography.byAs}</span>
            </div>
            <div className="flex flex-col gap-2.5">
              {data.autonomous_systems.map((a) => (
                <div key={a.organization}>
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="text-[11px] text-white/80 truncate">{a.organization}</span>
                    <span className="font-data text-[10px] text-white/45 shrink-0">
                      {n(a.count)}
                      <span className="text-white/25"> · {n(a.sources)}</span>
                    </span>
                  </div>
                  <div className="h-1 rounded bg-white/5 mt-1 overflow-hidden">
                    <div
                      className="h-1 rounded transition-all duration-700"
                      style={{
                        width: `${(a.count / maxAs) * 100}%`,
                        background: 'var(--honey-amber)',
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </Reveal>
      </div>

      {/* Coverage is stated, not assumed: the percentages above are computed over what resolved. */}
      <Reveal delay={240}>
        <div className="rounded-xl ring-1 ring-white/5 bg-white/[0.02] p-3.5">
          <div className="text-[10px] text-white/40 leading-relaxed">
            {t.geography.coverage(
              pct(data.with_geo, data.events, 1),
              pct(data.with_asn, data.events, 1),
            )}
          </div>
        </div>
      </Reveal>
    </section>
  );
}
