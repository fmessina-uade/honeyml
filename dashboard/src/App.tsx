import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle } from 'lucide-react';
import {
  api,
  SIN_SESION,
  type ArchetypeData,
  type Artefactos,
  type FingerprintData,
  type Health,
  type Replay,
  type Rol,
  type SesionAbierta,
  type Snapshot,
} from './lib/api';
import { ContextoDeSesion, alcanza, type SesionDelPanel } from './lib/sesion';
import { useI18n } from './lib/i18n';
import Preferencias from './components/Preferencias';
import BarraSuperior from './components/BarraSuperior';
import Titular from './components/Titular';
import { lecciones, type SectionId } from './components/lecciones';
import Inicio from './components/sections/Inicio';
import Pulse from './components/sections/Pulse';
import SessionReplay from './components/sections/SessionReplay';
import Dictionary from './components/sections/Dictionary';
import MitreMatrix from './components/sections/MitreMatrix';
import Protocols from './components/sections/Protocols';
import Fingerprints from './components/sections/Fingerprints';
import Archetypes from './components/sections/Archetypes';
import Geography from './components/sections/Geography';
import Triage from './components/sections/Triage';
import AttackCanvas from './components/AttackCanvas';
import Ingreso from './components/acceso/Ingreso';
import MenuCuenta from './components/acceso/MenuCuenta';
import Reporte from './components/acceso/Reporte';
import Refresco from './components/acceso/Refresco';
import Cuentas from './components/sections/Cuentas';
import Auditoria from './components/sections/Auditoria';
import EnVivo from './components/sections/EnVivo';
import { fechaHora } from './lib/format';
import TransicionColmena, {
  APERTURA_MS,
  CIERRE_MS,
  type Fase,
} from './components/TransicionColmena';

export type { SectionId };

const PRESENTACION_PROPIA = new Set<SectionId>([
  'inicio',
  'pulso',
  'protocolos',
  'origen',
  'diccionario',
  'huellas',
  'arquetipos',
  'anatomia',
  'mitre',
]);

// Cada cuánto se vuelve a pedir el snapshot con la pestaña a la vista. La API lo guarda medio
// minuto, así que pedirlo más seguido no trae nada nuevo.
const REFRESCO_MS = 60_000;

// El rol mínimo de cada vista de administración. Si la sesión no lo tiene, la vista vuelve al resumen.
const ROL_DE: Partial<Record<SectionId, Rol>> = {
  cuentas: 'admin',
  auditoria: 'superadmin',
  envivo: 'superadmin',
};

function SinDatos() {
  const { t } = useI18n();
  return <div className="panel p-8 text-center text-[13px] text-white/50">{t.error.title}</div>;
}

export default function App() {
  const { t } = useI18n();
  // undefined mientras se pregunta a la API, null sin sesión.
  const [sesion, setSesion] = useState<SesionAbierta | null | undefined>(undefined);
  const [aviso, setAviso] = useState<string | null>(null);
  const [reporte, setReporte] = useState(false);
  const [actualizado, setActualizado] = useState<number | null>(null);
  const [refrescando, setRefrescando] = useState(false);
  const [artefactos, setArtefactos] = useState<Artefactos | null>(null);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [replays, setReplays] = useState<Replay[]>([]);
  const [error, setError] = useState<string | null>(null);
  // La sección pedida y la que se muestra van por separado: la barra marca la pedida en el acto, y
  // el contenido cambia recién cuando el velo de la transición la tapa.
  const [active, setActive] = useState<SectionId>('inicio');
  const [mostrada, setMostrada] = useState<SectionId>('inicio');
  const [fase, setFase] = useState<Fase>('inicial');
  const [families, setFamilies] = useState<FingerprintData | null>(null);
  const [archetypes, setArchetypes] = useState<ArchetypeData | null>(null);
  // el modo captura congela todas las animaciones, así las capturas de pantalla se repiten igual
  const [capture, setCapture] = useState(false);
  const principal = useRef<HTMLElement>(null);

  // Al abrir, quién está adentro. Sin sesión va el ingreso; con la API caída, el error de siempre.
  useEffect(() => {
    api
      .sesion()
      .then(setSesion)
      .catch(() => {
        setSesion(null);
        setAviso(t.acceso.sinApi);
      });
    // la primera pregunta va una sola vez, en el idioma con que arrancó el panel
  }, []);

  // Cualquier 401 de cualquier sección quiere decir que la sesión se cerró: vencida, dada de baja
  // o con el rol cambiado. Se vuelve al ingreso con el aviso.
  useEffect(() => {
    const alPerderla = () => {
      setSesion((s) => {
        if (s) setAviso(t.acceso.vencida);
        return null;
      });
    };
    window.addEventListener(SIN_SESION, alPerderla);
    return () => window.removeEventListener(SIN_SESION, alPerderla);
  }, [t]);

  const refrescar = useCallback(() => {
    setRefrescando(true);
    api
      .snapshot()
      .then((s) => {
        setSnapshot(s);
        setActualizado(Date.now());
      })
      .catch(() => undefined)
      .finally(() => setRefrescando(false));
  }, []);

  useEffect(() => {
    if (!sesion) return;
    Promise.all([api.snapshot(), api.replays()])
      .then(([s, r]) => {
        setSnapshot(s);
        setReplays(r);
        setActualizado(Date.now());
      })
      .catch((e) => setError(String(e)));
    api
      .artefactos()
      .then(setArtefactos)
      .catch(() => setArtefactos(null));
    // llamada aparte: el panel tiene que cargar igual si el chequeo de salud no responde
    api
      .health()
      .then(setHealth)
      .catch(() => setHealth(null));
    api
      .fingerprints()
      .then(setFamilies)
      .catch(() => setFamilies(null));
    // Cada uno por separado y con su propio catch: son artefactos generados aparte, y que falte
    // uno no tiene por qué dejar sin panel a los demás.
    api
      .archetypes()
      .then(setArchetypes)
      .catch(() => setArchetypes(null));
  }, [sesion]);

  // Lo que sale del snapshot es en vivo: se vuelve a pedir cada minuto con la pestaña a la vista, y
  // al volver a ella. Las cifras suben desde donde estaban.
  useEffect(() => {
    if (!sesion) return;
    const id = window.setInterval(() => !document.hidden && refrescar(), REFRESCO_MS);
    const alVolver = () => {
      if (!document.hidden && actualizado && Date.now() - actualizado > REFRESCO_MS) refrescar();
    };
    document.addEventListener('visibilitychange', alVolver);
    return () => {
      window.clearInterval(id);
      document.removeEventListener('visibilitychange', alVolver);
    };
  }, [sesion, refrescar, actualizado]);

  useEffect(() => {
    document.documentElement.dataset.capture = capture ? 'on' : 'off';
  }, [capture]);

  // Un único oyente para el filo de todas las tarjetas: cada una sabe dónde está el puntero por
  // dos variables de CSS, sin un manejador por tarjeta.
  useEffect(() => {
    const mover = (e: PointerEvent) => {
      const tarjeta = (e.target as Element | null)?.closest?.('.panel') as HTMLElement | null;
      if (!tarjeta) return;
      const r = tarjeta.getBoundingClientRect();
      tarjeta.style.setProperty('--mx', `${e.clientX - r.left}px`);
      tarjeta.style.setProperty('--my', `${e.clientY - r.top}px`);
    };
    document.addEventListener('pointermove', mover, { passive: true });
    return () => document.removeEventListener('pointermove', mover);
  }, []);

  // El velo cubre mientras no hay nada que mostrar: al abrir, hasta saber si hay sesión, y después
  // del ingreso, hasta que llegan los datos. Así no se llega a ver la pantalla vacía ni el panel
  // anterior mientras carga el nuevo.
  const listo = sesion === null || Boolean(sesion && (snapshot || error));
  useEffect(() => {
    if (listo) setFase((f) => (f === 'quieta' ? f : 'abriendo'));
    else if (sesion) setFase('cerrando');
  }, [listo, sesion]);

  const ingresar = (s: SesionAbierta) => {
    setAviso(null);
    setFase('cerrando');
    setSesion(s);
  };

  const salir = useCallback(() => {
    setFase('cerrando');
    window.setTimeout(() => {
      api.salir().catch(() => undefined);
      setSesion(null);
      setSnapshot(null);
      setReplays([]);
      setFamilies(null);
      setArchetypes(null);
      setActive('inicio');
      setMostrada('inicio');
    }, CIERRE_MS);
  }, []);

  const cerrarReporte = useCallback(() => setReporte(false), []);

  const delPanel = useMemo<SesionDelPanel | null>(
    () =>
      sesion ? { ...sesion, puede: (minimo: Rol) => alcanza(sesion.rol, minimo), salir } : null,
    [sesion, salir],
  );

  // Una vista que el rol no ve no se abre, aunque se llegue a ella por un estado viejo.
  useEffect(() => {
    const minimo = ROL_DE[active];
    if (sesion && minimo && !alcanza(sesion.rol, minimo)) setActive('inicio');
  }, [active, sesion]);

  // Al cambiar de sección el velo cubre la vieja, se cambia y se descubre la nueva ya arriba de
  // todo: si no, en el teléfono la sección nueva abre por la mitad, a la altura de la anterior.
  useEffect(() => {
    if (active === mostrada) return;
    const cambiar = () => {
      setMostrada(active);
      principal.current?.scrollTo({ top: 0 });
    };
    const sinMovimiento =
      window.matchMedia('(prefers-reduced-motion: reduce)').matches ||
      document.documentElement.dataset.capture === 'on';
    if (sinMovimiento) {
      cambiar();
      return;
    }
    setFase('cerrando');
    const id = window.setTimeout(() => {
      cambiar();
      setFase('abriendo');
    }, CIERRE_MS);
    return () => window.clearTimeout(id);
  }, [active, mostrada]);

  useEffect(() => {
    if (fase !== 'abriendo') return;
    const id = window.setTimeout(() => setFase('quieta'), APERTURA_MS);
    return () => window.clearTimeout(id);
  }, [fase]);

  const cifras = useMemo(
    () => (snapshot ? lecciones(snapshot, families, archetypes, replays.length, t) : null),
    [snapshot, families, archetypes, replays.length, t],
  );

  const desde = snapshot?.overview.first_event?.slice(0, 10) ?? '';
  const hasta = snapshot?.overview.last_event?.slice(0, 10) ?? '';
  const estado =
    health?.mode === 'snapshot' ? (
      <span
        className="chip"
        title={`${t.footer.frozenTitle} ${health.generated_at?.slice(0, 16).replace('T', ' ')}`}
      >
        {t.footer.frozenShort}
      </span>
    ) : (
      <span
        className="chip"
        data-vivo="si"
        style={{ '--chip-tono': 'var(--neural-teal)' } as React.CSSProperties}
        title={snapshot ? t.footer.range(desde, hasta) : undefined}
      >
        {t.footer.liveShort}
      </span>
    );

  // Sin sesión, el ingreso. El velo de la transición sigue arriba, así entrar y salir pasan por el
  // mismo cargador que cambiar de sección.
  if (!delPanel) {
    return (
      <>
        {sesion === null && (
          <Ingreso onIngreso={ingresar} aviso={aviso} demora={fase === 'quieta' ? 0 : 450} />
        )}
        <TransicionColmena fase={fase} />
      </>
    );
  }

  const fechaDeLote = (
    {
      huellas: artefactos?.huellas,
      arquetipos: artefactos?.arquetipos,
      anatomia: artefactos?.sesiones,
    } as Partial<Record<SectionId, string | null | undefined>>
  )[mostrada];

  return (
    <ContextoDeSesion.Provider value={delPanel}>
      <div className="h-[100dvh] flex flex-col overflow-hidden">
        <BarraSuperior
          active={active}
          onIr={setActive}
          snapshot={snapshot}
          familias={families}
          arquetipos={archetypes}
          cifras={cifras}
          estado={estado}
          preferencias={<Preferencias capture={capture} onCapture={() => setCapture((c) => !c)} />}
          cuenta={
            <MenuCuenta active={active} onIr={setActive} onReporte={() => setReporte(true)} />
          }
          cuentaEnHoja={
            <MenuCuenta
              active={active}
              onIr={setActive}
              onReporte={() => setReporte(true)}
              enHoja
            />
          }
          refresco={
            <Refresco actualizado={actualizado} refrescando={refrescando} onRefrescar={refrescar} />
          }
        />

        <main
          ref={principal}
          className="flex-1 min-w-0 overflow-y-auto overflow-x-hidden thin-scroll papel"
        >
          <div className="max-w-[1320px] mx-auto px-4 md:px-8 pb-12">
            {/* Las secciones con presentación propia dibujan su encabezado; el resto usa este. */}
            {snapshot && !PRESENTACION_PROPIA.has(mostrada) && (
              <header
                key={`h-${mostrada}`}
                className="relative -mx-4 px-4 md:-mx-8 md:px-8 pt-8 pb-7"
              >
                <AttackCanvas intensity={snapshot.timeline.map((d) => d.count)} />
                <div className="relative max-w-3xl">
                  <Titular texto={t.nav[mostrada]} />
                  <p className="text-[14px] text-white/55 mt-3 leading-relaxed section-in">
                    {t.lead[mostrada]}
                  </p>
                </div>
              </header>
            )}

            {error && (
              <div className="rounded-xl ring-1 ring-[var(--agent-coral)]/30 bg-[var(--agent-coral)]/5 p-4 flex gap-3">
                <AlertTriangle className="w-4 h-4 text-[var(--agent-coral)] shrink-0 mt-0.5" />
                <div className="min-w-0">
                  <div className="text-[13px] text-white/85">{t.error.title}</div>
                  <div className="font-data text-[11px] text-white/45 mt-1 break-all">{error}</div>
                  <div className="text-[11px] text-white/45 mt-2">
                    {t.error.hint} <span className="font-data">make api</span>
                  </div>
                </div>
              </div>
            )}

            {fechaDeLote && (
              <p key={`l-${mostrada}`} className="nota-lote section-in">
                {t.refresco.calculado(fechaHora(fechaDeLote))}
              </p>
            )}

            {snapshot && (
              <div key={mostrada} className="section-in">
                {mostrada === 'inicio' && (
                  <Inicio
                    snapshot={snapshot}
                    familias={families}
                    arquetipos={archetypes}
                    sesiones={replays.length}
                    onIr={setActive}
                  />
                )}
                {mostrada === 'triaje' && <Triage />}
                {mostrada === 'pulso' && (
                  <Pulse
                    overview={snapshot.overview}
                    timeline={snapshot.timeline}
                    hourly={snapshot.hourly}
                    weekly={snapshot.weekly_rhythm}
                  />
                )}
                {mostrada === 'anatomia' && <SessionReplay replays={replays} />}
                {mostrada === 'diccionario' && (
                  <Dictionary
                    users={snapshot.credentials.users}
                    passwords={snapshot.credentials.passwords}
                  />
                )}
                {mostrada === 'protocolos' && <Protocols detail={snapshot.protocol_detail} />}
                {mostrada === 'huellas' &&
                  (families ? <Fingerprints data={families} /> : <SinDatos />)}
                {mostrada === 'arquetipos' &&
                  (archetypes ? <Archetypes data={archetypes} /> : <SinDatos />)}
                {mostrada === 'origen' &&
                  (snapshot.geography ? <Geography data={snapshot.geography} /> : <SinDatos />)}
                {mostrada === 'cuentas' && <Cuentas />}
                {mostrada === 'auditoria' && <Auditoria />}
                {mostrada === 'envivo' && <EnVivo />}
                {mostrada === 'mitre' && (
                  <MitreMatrix
                    replays={replays}
                    stages={snapshot.stages}
                    overview={snapshot.overview}
                  />
                )}
              </div>
            )}

            {snapshot && (
              <footer className="mt-12 pt-5 border-t border-white/5 flex flex-wrap items-center justify-between gap-3 text-[11px] text-white/35">
                <span className="flex items-center gap-2">
                  <img src="/favicon.png" alt="" aria-hidden className="w-4 h-4 rounded" />
                  <span className="font-mono-display">{t.brand.name}</span>
                  <span className="geist text-[12px] text-white/40">{t.brand.subtitle}</span>
                </span>
                <span className="font-data">{t.footer.range(desde, hasta)}</span>
              </footer>
            )}
          </div>
        </main>
        <div className="grano" aria-hidden />
        {reporte && snapshot && <Reporte snapshot={snapshot} onCerrar={cerrarReporte} />}
        <TransicionColmena fase={fase} />
      </div>
    </ContextoDeSesion.Provider>
  );
}
