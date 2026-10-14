import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { ChevronDown, Menu, SlidersHorizontal, X } from 'lucide-react';
import type { ArchetypeData, FingerprintData, Snapshot } from '../lib/api';
import { useI18n } from '../lib/i18n';
import Miniatura from './Miniatura';
import Marca from './Marca';
import {
  MENUS,
  SECCIONES,
  type Leccion,
  type LeccionId,
  type MenuId,
  type SectionId,
} from './lecciones';

const ORDEN: MenuId[] = MENUS.map((m) => m.id);
// Corrimiento del desplegable respecto de su disparador: el relleno del panel más el de sus filas,
// así el texto de adentro arranca alineado con el del botón que lo abrió.
const ALINEACION = 20;
const GRACIA_MS = 140;

/**
 * La barra de arriba: la marca, las secciones y el acceso al motor.
 *
 * Los tres desplegables comparten un único contenedor. Al pasar de uno a otro el contenedor no se
 * cierra y se vuelve a abrir: cambia de lugar, de ancho y de alto hasta calzar con el contenido
 * nuevo, y el contenido entra desde el lado hacia el que se movió el puntero. Las clases y los
 * estados de esa transición se manejan sobre el DOM y no con estado de React, porque el orden
 * importa: primero se ubica el panel nuevo sin animar, después se fuerza el reflujo y recién ahí se
 * deja animar. Con un render de por medio, ese orden no se garantiza.
 *
 * Cada desplegable tiene la lista a la izquierda y, a la derecha, la miniatura de la fila elegida.
 * En pantallas angostas las secciones pasan a una hoja que se despliega debajo de la barra.
 */
export default function BarraSuperior({
  active,
  onIr,
  snapshot,
  familias,
  arquetipos,
  cifras,
  estado,
  preferencias,
  cuenta,
  cuentaEnHoja,
  refresco,
}: {
  active: SectionId;
  onIr: (id: SectionId) => void;
  snapshot: Snapshot | null;
  familias: FingerprintData | null;
  arquetipos: ArchetypeData | null;
  cifras: Record<LeccionId, Leccion> | null;
  estado: ReactNode;
  preferencias: ReactNode;
  cuenta: ReactNode;
  cuentaEnHoja: ReactNode;
  refresco: ReactNode;
}) {
  const { t } = useI18n();
  const [abierto, setAbierto] = useState<MenuId | null>(null);
  const [previa, setPrevia] = useState<Record<MenuId, LeccionId>>(
    () => Object.fromEntries(MENUS.map((m) => [m.id, m.secciones[0]])) as Record<MenuId, LeccionId>,
  );
  const [hoja, setHoja] = useState(false);
  const [ajustes, setAjustes] = useState(false);

  const barra = useRef<HTMLElement>(null);
  const nav = useRef<HTMLElement>(null);
  const caja = useRef<HTMLDivElement>(null);
  const ajustesRef = useRef<HTMLDivElement>(null);
  const paneles = useRef<Partial<Record<MenuId, HTMLDivElement | null>>>({});
  const disparadores = useRef<Partial<Record<MenuId, HTMLButtonElement | null>>>({});
  const actual = useRef<MenuId | null>(null);
  const espera = useRef<number>();

  const ubicar = useCallback((id: MenuId) => {
    const panel = paneles.current[id];
    const disparador = disparadores.current[id];
    const dd = caja.current;
    if (!panel || !disparador || !dd || !barra.current) return;
    const borde = barra.current.getBoundingClientRect();
    const ancho = panel.offsetWidth;
    const x = Math.min(
      Math.max(disparador.getBoundingClientRect().left - ALINEACION, borde.left + 12),
      borde.right - ancho - 12,
    );
    const base = ((dd.offsetParent as HTMLElement | null) ?? barra.current).getBoundingClientRect();
    dd.style.setProperty('--x', `${x - base.left}px`);
    dd.style.setProperty('--w', `${ancho}px`);
    dd.style.setProperty('--h', `${panel.offsetHeight}px`);
  }, []);

  const cerrar = useCallback(() => {
    window.clearTimeout(espera.current);
    caja.current?.classList.remove('abierto');
    const previo = actual.current && paneles.current[actual.current];
    if (previo) delete previo.dataset.estado;
    actual.current = null;
    setAbierto(null);
  }, []);

  const cerrarEnSeguida = useCallback(
    (ms = GRACIA_MS) => {
      window.clearTimeout(espera.current);
      espera.current = window.setTimeout(cerrar, ms);
    },
    [cerrar],
  );

  const abrir = useCallback(
    (id: MenuId) => {
      window.clearTimeout(espera.current);
      const dd = caja.current;
      const nuevo = paneles.current[id];
      if (!dd || !nuevo || actual.current === id) return;
      const todos = Object.values(paneles.current).filter(Boolean) as HTMLDivElement[];

      if (actual.current === null) {
        // Primera apertura: aparece en su lugar, sin animar posición ni tamaño.
        dd.classList.add('instantaneo', 'sin-transicion');
        todos.forEach((p) => {
          p.classList.add('sin-transicion');
          delete p.dataset.estado;
        });
        ubicar(id);
        void dd.offsetWidth;
        dd.classList.remove('sin-transicion');
        todos.forEach((p) => p.classList.remove('sin-transicion'));
        dd.classList.add('abierto');
        requestAnimationFrame(() => dd.classList.remove('instantaneo'));
      } else {
        // Cambio de desplegable: el viejo sale hacia un lado y el nuevo entra desde el otro.
        const haciaLaDerecha = ORDEN.indexOf(id) > ORDEN.indexOf(actual.current);
        const viejo = paneles.current[actual.current];
        if (viejo) viejo.dataset.estado = haciaLaDerecha ? 'exit-left' : 'exit-right';
        nuevo.classList.add('sin-transicion');
        nuevo.dataset.estado = haciaLaDerecha ? 'exit-right' : 'exit-left';
        void nuevo.offsetWidth;
        nuevo.classList.remove('sin-transicion');
        ubicar(id);
      }
      nuevo.dataset.estado = 'active';
      actual.current = id;
      setAbierto(id);
    },
    [ubicar],
  );

  const ir = (id: SectionId) => {
    cerrar();
    setHoja(false);
    setAjustes(false);
    onIr(id);
  };

  useEffect(() => {
    const alTeclear = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      const habia = actual.current;
      cerrar();
      setHoja(false);
      setAjustes(false);
      if (habia) disparadores.current[habia]?.focus();
    };
    const alTocar = (e: PointerEvent) => {
      if (!nav.current?.contains(e.target as Node)) cerrar();
      if (!ajustesRef.current?.contains(e.target as Node)) setAjustes(false);
    };
    const alCambiarTamano = () => actual.current && ubicar(actual.current);
    document.addEventListener('keydown', alTeclear);
    document.addEventListener('pointerdown', alTocar);
    window.addEventListener('resize', alCambiarTamano);
    return () => {
      document.removeEventListener('keydown', alTeclear);
      document.removeEventListener('pointerdown', alTocar);
      window.removeEventListener('resize', alCambiarTamano);
      window.clearTimeout(espera.current);
    };
  }, [cerrar, ubicar]);

  // Elegir una vista desde la cuenta, que va adentro de la hoja, también la cierra.
  useEffect(() => setHoja(false), [active]);

  const menuActivo = MENUS.find((m) => (m.secciones as readonly SectionId[]).includes(active))?.id;

  const enlaceDirecto = (id: SectionId) => (
    <button
      onClick={() => ir(id)}
      onPointerEnter={(e) => e.pointerType === 'mouse' && cerrarEnSeguida(60)}
      aria-current={active === id ? 'page' : undefined}
      className="enlace-barra"
    >
      {t.nav[id]}
    </button>
  );

  return (
    <header ref={barra} className="barra-sup relative z-40 shrink-0">
      <div className="barra-fila">
        <button
          onClick={() => ir('inicio')}
          className="flex items-center gap-2.5 justify-self-start min-w-0"
          aria-label={t.brand.name}
        >
          <img src="/favicon.png" alt="" aria-hidden className="w-7 h-7 rounded-lg shrink-0" />
          <Marca className="geist text-[16px] font-semibold text-white tracking-tight leading-none" />
        </button>

        <nav
          ref={nav}
          aria-label={t.brand.name}
          className="hidden min-[981px]:block justify-self-center"
          onPointerEnter={() => window.clearTimeout(espera.current)}
          onPointerLeave={(e) => e.pointerType === 'mouse' && cerrarEnSeguida()}
          onBlur={(e) => {
            if (!nav.current?.contains(e.relatedTarget as Node | null)) cerrarEnSeguida(0);
          }}
        >
          <ul className="flex items-center gap-7">
            <li>{enlaceDirecto('inicio')}</li>
            {MENUS.map((m) => (
              <li key={m.id}>
                <button
                  ref={(el) => (disparadores.current[m.id] = el)}
                  className="enlace-barra"
                  aria-expanded={abierto === m.id}
                  aria-haspopup="true"
                  data-actual={menuActivo === m.id ? 'si' : undefined}
                  onPointerEnter={(e) => e.pointerType === 'mouse' && abrir(m.id)}
                  onClick={() => (abierto === m.id ? cerrar() : abrir(m.id))}
                >
                  {t.navGroups[m.id]}
                  <ChevronDown className="chevron w-3 h-3" aria-hidden />
                </button>
              </li>
            ))}
          </ul>

          <div ref={caja} className="desplegable">
            {MENUS.map((m) => (
              <div
                key={m.id}
                ref={(el) => (paneles.current[m.id] = el)}
                className="panel-dd grid grid-cols-[248px_1fr] w-[680px]"
                style={{ height: m.secciones.length === 3 ? 348 : 260 }}
              >
                <div className="flex flex-col gap-0.5 p-2">
                  {m.secciones.map((id) => (
                    <button
                      key={id}
                      onClick={() => ir(id)}
                      onPointerEnter={() => setPrevia((p) => ({ ...p, [m.id]: id }))}
                      onFocus={() => setPrevia((p) => ({ ...p, [m.id]: id }))}
                      aria-current={active === id ? 'page' : undefined}
                      data-elegida={previa[m.id] === id ? 'si' : undefined}
                      className="fila-dd flex-1 flex flex-col justify-center px-3 rounded-[10px] text-left"
                    >
                      <span className="geist flex items-center gap-2 text-[15px] font-medium text-white">
                        {t.nav[id]}
                        {active === id && <span className="punto-actual" aria-hidden />}
                      </span>
                      <span className="text-[12.5px] leading-snug text-white/55 mt-1">
                        {t.navDesc[id]}
                      </span>
                    </button>
                  ))}
                </div>
                <div className="relative overflow-hidden rounded-r-[15px]" aria-hidden>
                  {m.secciones.map((id) => (
                    <div
                      key={id}
                      className="previa"
                      data-elegida={previa[m.id] === id ? 'si' : undefined}
                      style={{ '--tono': SECCIONES[id].color } as React.CSSProperties}
                    >
                      <span className="lamina-panal" />
                      <div className="relative flex-1 min-h-0 text-white">
                        {snapshot && (
                          <Miniatura
                            id={id}
                            color={SECCIONES[id].color}
                            snapshot={snapshot}
                            familias={familias}
                            arquetipos={arquetipos}
                          />
                        )}
                      </div>
                      {cifras && (
                        <div className="relative flex items-baseline gap-2 flex-wrap pt-2">
                          <span
                            className="cifra text-[20px]"
                            style={{ color: SECCIONES[id].color }}
                          >
                            {cifras[id].cifra}
                          </span>
                          <span className="text-[11.5px] text-white/55">{cifras[id].texto}</span>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </nav>

        <div className="flex items-center gap-2.5 justify-self-end">
          <span className="hidden min-[1341px]:inline-flex">{refresco}</span>
          <span className="hidden min-[1181px]:inline-flex">{estado}</span>
          <div ref={ajustesRef} className="relative hidden min-[981px]:block">
            <button
              onClick={() => setAjustes((a) => !a)}
              aria-label={t.theme.title}
              aria-expanded={ajustes}
              data-capture-toggle
              className="flex items-center justify-center w-9 h-9 rounded-full text-white/60 ring-1 ring-white/10 hover:text-white hover:ring-white/25 transition"
            >
              <SlidersHorizontal className="w-4 h-4" />
            </button>
            <div className="ajustes" data-abierta={ajustes ? 'si' : undefined}>
              {preferencias}
            </div>
          </div>
          <button
            onClick={() => ir('triaje')}
            aria-current={active === 'triaje' ? 'page' : undefined}
            className="boton-cta hidden min-[981px]:inline-flex"
          >
            <span className="relative flex w-1.5 h-1.5">
              <span className="absolute inline-flex h-full w-full rounded-full bg-[var(--agent-coral)] opacity-70 animate-ping" />
              <span className="relative inline-flex w-1.5 h-1.5 rounded-full bg-[var(--agent-coral)]" />
            </span>
            {t.nav.triaje}
          </button>
          <div className="hidden min-[981px]:block">{cuenta}</div>

          <span className="min-[981px]:hidden geist text-[13px] text-white/65 truncate max-w-[42vw]">
            {t.nav[active]}
          </span>
          <button
            onClick={() => setHoja((h) => !h)}
            aria-label={hoja ? t.menu.close : t.menu.open}
            aria-expanded={hoja}
            data-capture-toggle
            className="min-[981px]:hidden flex items-center justify-center w-9 h-9 rounded-full text-white/80 ring-1 ring-white/15 bg-white/[0.06]"
          >
            {hoja ? <X className="w-4 h-4" /> : <Menu className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {/* La hoja de pantallas angostas: las mismas secciones, agrupadas igual que en la barra */}
      <div className="hoja min-[981px]:hidden" data-abierta={hoja ? 'si' : undefined}>
        <div className="flex flex-col">
          {(['inicio', 'triaje'] as const).map((id) => (
            <button
              key={id}
              onClick={() => ir(id)}
              aria-current={active === id ? 'page' : undefined}
              className="fila-dd flex items-center gap-2.5 px-3 py-2.5 rounded-[10px] text-left"
            >
              <span className="geist text-[15px] text-white/90">{t.nav[id]}</span>
              {active === id && <span className="punto-actual ml-auto" aria-hidden />}
            </button>
          ))}
        </div>
        {MENUS.map((m) => (
          <div key={m.id} className="flex flex-col">
            <h3 className="rotulo px-3 pt-3 pb-1.5">{t.navGroups[m.id]}</h3>
            {m.secciones.map((id) => (
              <button
                key={id}
                onClick={() => ir(id)}
                aria-current={active === id ? 'page' : undefined}
                className="fila-dd flex flex-col px-3 py-2 rounded-[10px] text-left"
              >
                <span className="geist flex items-center gap-2 text-[15px] text-white/90">
                  {t.nav[id]}
                  {active === id && <span className="punto-actual" aria-hidden />}
                </span>
                <span className="text-[12px] text-white/50 mt-0.5">{t.navDesc[id]}</span>
              </button>
            ))}
          </div>
        ))}
        <div className="mt-2 border-t border-white/5 pt-2">{cuentaEnHoja}</div>
        <div className="flex flex-col gap-3 px-3 pt-4 pb-2 mt-2 border-t border-white/5">
          {preferencias}
          <div className="flex items-center gap-2 flex-wrap">
            {estado}
            {refresco}
          </div>
        </div>
      </div>
    </header>
  );
}
