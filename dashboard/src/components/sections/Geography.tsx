import { useState } from 'react';
import { Globe as GlobeIcon, Server } from 'lucide-react';
import Globo from '../Globe';
import type { Geography as GeoData } from '../../lib/api';
import Reveal from '../Reveal';
import { n, pct } from '../../lib/format';
import { useI18n } from '../../lib/i18n';

/**
 * De dónde vienen los ataques: por país, y por la red que efectivamente opera la dirección.
 *
 * El país solo es la mitad más débil. Lo que separa un servidor alquilado de una conexión hogareña
 * es el sistema autónomo, así que se muestran los dos lado a lado y la sección está escrita
 * alrededor de esa comparación y no de un ranking de banderas.
 */

/** Símbolos indicadores regionales desde el código ISO: sin imágenes de banderas ni pedidos externos. */
function flag(iso: string): string {
  if (iso.length !== 2) return '🏳️';
  return String.fromCodePoint(...[...iso.toUpperCase()].map((c) => 0x1f1a5 + c.charCodeAt(0)));
}

export default function Geography({ data }: { data: GeoData }) {
  const { t } = useI18n();
  // Un solo país seleccionado a la vez: el globo gira hasta él y la fila queda resaltada. Volver a
  // tocarlo deselecciona y el giro continuo se retoma.
  const [pais, setPais] = useState<string | null>(null);

  const elegido = pais ? (data.countries.find((c) => c.country === pais) ?? null) : null;

  const maxPais = Math.max(...data.countries.map((c) => c.count), 1);
  const maxAs = Math.max(...data.autonomous_systems.map((a) => a.count), 1);

  // Los eventos por dirección son la pista: un país puede liderar en volumen y ser cuatro equipos.
  //
  // Formateado con el helper del proyecto y no con toLocaleString directo: ese cae en el locale del
  // navegador, y así apareció "1,537" al lado de "252.137" en la misma línea. El helper sigue el
  // selector de idioma, así que los dos números quedan consistentes.
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
            <div className="relative aspect-square w-full max-w-[320px] mx-auto">
              <Globo countries={data.countries} selected={pais} onSelect={setPais} />

              {/* El nombre va sobre el globo y no al costado: al elegir un país la mirada ya está
                  acá, siguiendo el giro, y leerlo en otro lado obliga a buscarlo. Sin capturar el
                  puntero, para no romper el arrastre que pasa por debajo. */}
              {elegido && (
                <div
                  key={elegido.country}
                  className="pais-rotulo pointer-events-none absolute inset-x-0 bottom-0 px-3 pb-3 pt-10
                             bg-gradient-to-t from-[#0f141b] via-[#0f141b]/85 to-transparent
                             rounded-b-xl text-center"
                >
                  <div className="text-[10px] text-white/40 mb-0.5">{flag(elegido.iso)}</div>
                  <div className="text-2xl leading-none text-white font-mono-display text-balance">
                    {elegido.country}
                  </div>
                  <div className="font-data text-[11px] text-[var(--agent-coral)] mt-1.5">
                    {n(elegido.count)}{' '}
                    <span className="text-white/40">{t.geography.eventsShort}</span>
                    <span className="text-white/25">
                      {' '}
                      · {pct(elegido.count, data.with_geo, 1)}%
                    </span>
                  </div>
                </div>
              )}
            </div>

            <div className="text-[11px] text-white/55 leading-relaxed">
              {elegido ? (
                <>
                  <div className="grid grid-cols-3 gap-2 mb-3">
                    {[
                      { label: t.geography.addresses, value: n(elegido.sources) },
                      {
                        label: t.geography.perAddressShort,
                        value: porDireccion(elegido.count, elegido.sources),
                      },
                      {
                        label: t.geography.ofLocated,
                        value: `${pct(elegido.count, data.with_geo, 1)}%`,
                      },
                    ].map((m) => (
                      <div key={m.label} className="rounded-lg bg-white/[0.03] p-2.5">
                        <div className="font-data text-[15px] text-white/90">{m.value}</div>
                        <div className="text-[9px] uppercase tracking-wider text-white/35 mt-0.5">
                          {m.label}
                        </div>
                      </div>
                    ))}
                  </div>
                  {t.geography.selected(elegido.country)}
                </>
              ) : (
                t.geography.pickHint
              )}
              <div className="text-[10px] text-white/30 mt-2">{t.geography.dragHint}</div>
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
