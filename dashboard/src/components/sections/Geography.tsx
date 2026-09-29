import { useState } from 'react';
import { Globe as GlobeIcon, Server } from 'lucide-react';
import Globo from '../Globe';
import type { Geography as GeoData } from '../../lib/api';
import Reveal from '../Reveal';
import ManoAlzada from '../ManoAlzada';
import { Hexagono } from '../Instrumento';
import { n, pct } from '../../lib/format';
import { useI18n } from '../../lib/i18n';

/**
 * De dónde vienen los ataques: por país, y por la red que efectivamente opera la dirección.
 *
 * El país solo es la mitad más débil. Lo que separa un servidor alquilado de una conexión hogareña
 * es el sistema autónomo, así que se muestran los dos lado a lado y la sección está escrita
 * alrededor de esa comparación y no de un ranking de banderas.
 */

/**
 * El país como su código de dos letras, en un recuadro. Las banderas con emoji dependen del sistema:
 * en Windows se ven como dos letras sueltas, así que el panel muestra directamente el código, igual
 * en todas partes.
 */
function Codigo({ iso }: { iso: string }) {
  return (
    <span className="inline-flex items-center justify-center font-data text-[9px] leading-none w-6 h-4 rounded-[3px] ring-1 ring-white/15 text-white/60 shrink-0">
      {iso.length === 2 ? iso.toUpperCase() : '?'}
    </span>
  );
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

  // El país que más eventos junta por dirección es la lección de la sección hecha dato: lidera en
  // insistencia con pocas máquinas. Es el que se subraya a mano en la tabla.
  const insistente = data.countries.reduce<(typeof data.countries)[number] | null>(
    (mejor, c) =>
      c.sources > 0 && (!mejor || c.count / c.sources > mejor.count / (mejor.sources || 1))
        ? c
        : mejor,
    null,
  );

  return (
    <section className="flex flex-col gap-4">
      <Reveal>
        <div className="panel p-4">
          <div className="text-[11px] text-white/60 leading-relaxed">{t.geography.lesson}</div>
        </div>
      </Reveal>

      {/* El globo y la tabla son un solo control: elegir en cualquiera de los dos mueve al otro. */}
      <Reveal delay={60}>
        <div className="panel p-4">
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
                  <div className="mb-1.5">
                    <Codigo iso={elegido.iso} />
                  </div>
                  <div className="text-2xl leading-none text-white font-mono-display text-balance">
                    {elegido.country}
                  </div>
                  <div className="font-data text-[11px] text-[var(--agent-coral)] mt-1.5">
                    {n(elegido.count)}{' '}
                    <span className="text-white/40">{t.geography.eventsShort}</span>
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
                        <div className="cifra-chica">{m.value}</div>
                        <div className="rotulo mt-0.5">{m.label}</div>
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
        <Reveal delay={80}>
          <div className="panel p-4 h-full">
            <div className="flex items-center gap-2.5 mb-3">
              <Hexagono color="var(--neural-teal)">
                <GlobeIcon className="w-3.5 h-3.5" />
              </Hexagono>
              <span className="rotulo">{t.geography.byCountry}</span>
            </div>
            <div className="flex flex-col gap-2.5">
              {data.countries.map((c) => {
                const activo = pais === c.country;
                const subrayado = insistente === c && data.countries.length > 2;
                return (
                  <button
                    key={c.country}
                    onClick={() => setPais(activo ? null : c.country)}
                    className={`relative text-left rounded-lg -mx-1.5 px-1.5 py-1 transition-colors ${
                      activo ? 'bg-white/[0.06]' : 'hover:bg-white/[0.03]'
                    }`}
                  >
                    <div className="flex items-baseline justify-between gap-2">
                      <span
                        className={`flex items-center gap-2 text-[11px] min-w-0 ${activo ? 'text-white' : 'text-white/80'}`}
                      >
                        <Codigo iso={c.iso} />
                        <span className="truncate">{c.country}</span>
                      </span>
                      <span className="font-data text-[10px] text-white/45 shrink-0">
                        {n(c.count)}
                        <span className="text-white/25">
                          {' '}
                          {t.geography.fromAddresses(n(c.sources))}
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
                    {subrayado && (
                      <ManoAlzada
                        trazos={[{ tipo: 'subrayado', x1: 0.5, x2: 33, y: 99 }]}
                        notas={[{ x: 36, y: 60, texto: t.geography.noteLoud, ancho: 260 }]}
                      />
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        </Reveal>

        <Reveal delay={160}>
          <div className="panel p-4 h-full">
            <div className="flex items-center gap-2.5 mb-3">
              <Hexagono color="var(--honey-amber)">
                <Server className="w-3.5 h-3.5" />
              </Hexagono>
              <span className="rotulo">{t.geography.byAs}</span>
            </div>
            <div className="flex flex-col gap-2.5">
              {data.autonomous_systems.map((a) => (
                <div key={a.organization}>
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="text-[11px] text-white/80 truncate">{a.organization}</span>
                    <span className="font-data text-[10px] text-white/45 shrink-0">
                      {n(a.count)}
                      <span className="text-white/25">
                        {' '}
                        {t.geography.fromAddresses(n(a.sources))}
                      </span>
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

      {/* La cobertura se dice y no se supone: los porcentajes de arriba se calculan sobre lo que se
          pudo resolver. */}
      <Reveal delay={240}>
        <div className="panel panel-tenue p-3.5">
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
