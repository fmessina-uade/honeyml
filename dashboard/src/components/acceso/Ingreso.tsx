import { useEffect, useLayoutEffect, useRef, useState, type FormEvent } from 'react';
import { ArrowRight, Eye, EyeOff, KeyRound, LoaderCircle, UserRound } from 'lucide-react';
import { api, type SesionAbierta } from '../../lib/api';
import { useI18n } from '../../lib/i18n';
import Preferencias from '../Preferencias';
import EscenaPanal from './EscenaPanal';
import Marca from '../Marca';

const EXPO = 'cubic-bezier(.16,1,.3,1)';
const SUAVE = 'cubic-bezier(.22,1,.36,1)';

interface Paso {
  sel: string;
  demora: number;
  duracion: number;
  curva: string;
  desde: Keyframe;
  hasta?: Keyframe;
}

// La entrada, en orden: la tarjeta da la profundidad, la promesa de la marca se apoya sobre ella y
// el formulario se resuelve al final, grupo por grupo. La escena no se mueve: es el escenario.
const PASOS: Paso[] = [
  {
    sel: '.ingreso-tarjeta',
    demora: 40,
    duracion: 820,
    curva: EXPO,
    desde: { opacity: 0, transform: 'translateY(12px) scale(.988)' },
  },
  {
    sel: '.ingreso-preferencias',
    demora: 160,
    duracion: 480,
    curva: SUAVE,
    desde: { opacity: 0, transform: 'translateY(-6px)' },
  },
  {
    sel: '.ingreso-insignia',
    demora: 120,
    duracion: 480,
    curva: SUAVE,
    desde: { opacity: 0, transform: 'translateY(8px)' },
  },
  {
    sel: '.ingreso-titular .ln:nth-child(1) > span',
    demora: 240,
    duracion: 900,
    curva: EXPO,
    desde: { transform: 'translateY(112%)' },
    hasta: { transform: 'none' },
  },
  {
    sel: '.ingreso-titular .ln:nth-child(2) > span',
    demora: 360,
    duracion: 900,
    curva: EXPO,
    desde: { transform: 'translateY(112%)' },
    hasta: { transform: 'none' },
  },
  {
    sel: '.ingreso-marca',
    demora: 380,
    duracion: 700,
    curva: EXPO,
    desde: { opacity: 0, transform: 'translateY(10px) scale(.94)' },
  },
  {
    sel: '.ingreso-insignia-tarjeta',
    demora: 440,
    duracion: 520,
    curva: SUAVE,
    desde: { opacity: 0, transform: 'translateY(8px)' },
  },
  {
    sel: '.ingreso-h1',
    demora: 500,
    duracion: 620,
    curva: EXPO,
    desde: { opacity: 0, transform: 'translateY(10px)' },
  },
  {
    sel: '[data-campo="usuario"]',
    demora: 720,
    duracion: 520,
    curva: SUAVE,
    desde: { opacity: 0, transform: 'translateY(8px)' },
  },
  {
    sel: '[data-campo="contrasena"]',
    demora: 790,
    duracion: 520,
    curva: SUAVE,
    desde: { opacity: 0, transform: 'translateY(8px)' },
  },
  {
    sel: '.ingreso-boton',
    demora: 930,
    duracion: 600,
    curva: EXPO,
    desde: { clipPath: 'inset(0 100% 0 0)' },
    hasta: { clipPath: 'inset(0 0 0 0)' },
  },
  {
    sel: '.ingreso-pie',
    demora: 1060,
    duracion: 500,
    curva: SUAVE,
    desde: { opacity: 0, transform: 'translateY(6px)' },
  },
];

/**
 * La pantalla de ingreso. Las cuentas las crea un administrador, así que no hay alta ni recuperación
 * de contraseña: el pie lo dice. La respuesta de un ingreso fallido no distingue si falló el usuario
 * o la contraseña, igual que la API.
 *
 * La entrada corre una sola vez. Hasta que arranca, lo que va a animarse queda oculto por CSS; si
 * algo falla, un temporizador lo libera igual, así nunca queda una pantalla en blanco.
 */
export default function Ingreso({
  onIngreso,
  aviso,
  demora,
}: {
  onIngreso: (s: SesionAbierta) => void;
  aviso: string | null;
  demora: number;
}) {
  const { t } = useI18n();
  const a = t.acceso;
  const raiz = useRef<HTMLDivElement>(null);
  const controles = useRef<HTMLDivElement>(null);
  const heroe = useRef<HTMLElement>(null);
  const campoUsuario = useRef<HTMLInputElement>(null);
  const [pendiente, setPendiente] = useState(true);
  const [usuario, setUsuario] = useState('');
  const [contrasena, setContrasena] = useState('');
  const [ver, setVer] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(aviso);

  useLayoutEffect(() => {
    const nodo = raiz.current;
    const sinMovimiento =
      window.matchMedia('(prefers-reduced-motion: reduce)').matches ||
      document.documentElement.dataset.capture === 'on' ||
      typeof Element.prototype.animate !== 'function';
    if (!nodo || sinMovimiento) {
      setPendiente(false);
      return;
    }
    const animaciones: Animation[] = [];
    for (const p of PASOS) {
      nodo.querySelectorAll<HTMLElement>(p.sel).forEach((el) => {
        animaciones.push(
          el.animate([p.desde, p.hasta ?? { opacity: 1, transform: 'none' }], {
            delay: demora + p.demora,
            duration: p.duracion,
            easing: p.curva,
            fill: 'both',
          }),
        );
      });
    }
    // Las animaciones ya tienen tomado el primer cuadro, así que el CSS que ocultaba puede soltarse
    // sin que nada parpadee. Al terminar se cancelan y queda el estilo escrito, sin residuos.
    setPendiente(false);
    const seguro = window.setTimeout(() => animaciones.forEach((x) => x.finish()), 3500 + demora);
    Promise.allSettled(animaciones.map((x) => x.finished)).then(() => {
      window.clearTimeout(seguro);
      animaciones.forEach((x) => x.cancel());
    });
    return () => {
      window.clearTimeout(seguro);
      animaciones.forEach((x) => x.cancel());
    };
    // la entrada corre una sola vez, con la demora que traía al montarse
  }, []);

  useEffect(() => {
    // En el teléfono el teclado tapa media pantalla: el foco automático solo en escritorio.
    if (window.matchMedia('(min-width: 700px) and (pointer: fine)').matches) {
      window.setTimeout(() => campoUsuario.current?.focus({ preventScroll: true }), demora + 900);
    }
  }, [demora]);

  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    if (enviando) return;
    if (!usuario.trim() || !contrasena) {
      setError(a.faltan);
      return;
    }
    setEnviando(true);
    setError(null);
    try {
      onIngreso(await api.ingresar(usuario.trim().toLowerCase(), contrasena));
    } catch (err) {
      const texto = err instanceof Error ? err.message : '';
      setError(texto && !texto.startsWith('/sesion') && !/fetch/i.test(texto) ? texto : a.sinApi);
      setContrasena('');
      setEnviando(false);
    }
  };

  return (
    <div ref={raiz} className="ingreso" data-entrada={pendiente ? 'pendiente' : undefined}>
      <EscenaPanal etiqueta={a.escena} controles={controles} texto={heroe} />
      <div className="ingreso-velo" aria-hidden />
      <div ref={controles} className="ingreso-preferencias">
        <Preferencias enLinea />
      </div>

      <section ref={heroe} className="ingreso-heroe">
        <span className="insignia ingreso-insignia">{a.insignia}</span>
        <h2 className="ingreso-titular">
          <span className="ln">
            <span>{a.linea1}</span>
          </span>
          <span className="ln">
            <span className="degradado">{a.linea2}</span>
          </span>
        </h2>
      </section>

      <main className="ingreso-tarjeta">
        <form className="ingreso-form" onSubmit={enviar} noValidate>
          <div className="ingreso-marca">
            <img src="/logo.png" alt="" aria-hidden width={88} height={88} />
            <Marca />
          </div>
          <span className="insignia ingreso-insignia-tarjeta">{a.insignia}</span>
          <h1 className="ingreso-h1">{a.titulo}</h1>

          <label className="ingreso-campo" data-campo="usuario">
            <UserRound className="w-[18px] h-[18px]" aria-hidden />
            <input
              ref={campoUsuario}
              value={usuario}
              onChange={(e) => setUsuario(e.target.value)}
              name="username"
              autoComplete="username"
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              placeholder={a.usuario}
              aria-label={a.usuario}
              maxLength={64}
            />
          </label>
          <label className="ingreso-campo" data-campo="contrasena">
            <KeyRound className="w-[18px] h-[18px]" aria-hidden />
            <input
              value={contrasena}
              onChange={(e) => setContrasena(e.target.value)}
              type={ver ? 'text' : 'password'}
              name="password"
              autoComplete="current-password"
              placeholder={a.contrasena}
              aria-label={a.contrasena}
              maxLength={256}
            />
            <button
              type="button"
              onClick={() => setVer((v) => !v)}
              aria-label={ver ? a.ocultar : a.mostrar}
              aria-pressed={ver}
              className="ingreso-ver"
            >
              {ver ? (
                <EyeOff className="w-[17px] h-[17px]" />
              ) : (
                <Eye className="w-[17px] h-[17px]" />
              )}
            </button>
          </label>

          <p className="ingreso-error" role="alert" aria-live="polite">
            {error}
          </p>

          <button type="submit" className="ingreso-boton" disabled={enviando}>
            {enviando ? (
              <>
                <LoaderCircle className="w-4 h-4 animate-spin" aria-hidden />
                {a.entrando}
              </>
            ) : (
              <>
                {a.entrar}
                <ArrowRight className="w-[15px] h-[15px]" aria-hidden />
              </>
            )}
          </button>

          <p className="ingreso-pie">{a.pie}</p>
        </form>
      </main>
    </div>
  );
}
