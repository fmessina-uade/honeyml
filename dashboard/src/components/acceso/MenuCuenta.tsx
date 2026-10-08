import { useEffect, useRef, useState, type FormEvent } from 'react';
import { FileDown, KeyRound, LogOut } from 'lucide-react';
import { api } from '../../lib/api';
import { useI18n } from '../../lib/i18n';
import { useSesion } from '../../lib/sesion';
import { Modal } from '../Superpuesto';
import { SECCIONES, type AdminId, type SectionId } from '../lecciones';

const MINIMO = 10;

// Qué rol hace falta para cada vista de administración. La API lo exige igual; acá solo decide qué
// se ofrece en el menú.
const VISTAS: { id: AdminId; rol: 'admin' | 'superadmin' }[] = [
  { id: 'cuentas', rol: 'admin' },
  { id: 'auditoria', rol: 'superadmin' },
  { id: 'envivo', rol: 'superadmin' },
];

/**
 * La cuenta, en la barra: quién está adentro y con qué rol, las vistas que ese rol habilita, el
 * reporte, el cambio de contraseña y la salida. En el teléfono va dentro de la hoja, abierto.
 */
export default function MenuCuenta({
  active,
  onIr,
  onReporte,
  enHoja = false,
}: {
  active: SectionId;
  onIr: (id: SectionId) => void;
  onReporte: () => void;
  enHoja?: boolean;
}) {
  const { t } = useI18n();
  const sesion = useSesion();
  const [abierto, setAbierto] = useState(false);
  const [cambiando, setCambiando] = useState(false);
  const caja = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!abierto) return;
    const alTocar = (e: PointerEvent) => {
      if (!caja.current?.contains(e.target as Node)) setAbierto(false);
    };
    const alTeclear = (e: KeyboardEvent) => e.key === 'Escape' && setAbierto(false);
    document.addEventListener('pointerdown', alTocar);
    document.addEventListener('keydown', alTeclear);
    return () => {
      document.removeEventListener('pointerdown', alTocar);
      document.removeEventListener('keydown', alTeclear);
    };
  }, [abierto]);

  const elegir = (accion: () => void) => {
    setAbierto(false);
    accion();
  };

  const contenido = (
    <div className="flex flex-col">
      <div className="px-3 pt-2 pb-3">
        <div className="flex items-center gap-2.5">
          <span className="avatar-cuenta" aria-hidden>
            {sesion.usuario.slice(0, 1).toUpperCase()}
          </span>
          <span className="min-w-0">
            <span className="block geist text-[14.5px] font-medium text-white truncate">
              {sesion.usuario}
            </span>
            <span className="rol-cuenta" data-rol={sesion.rol}>
              {t.roles[sesion.rol]}
            </span>
          </span>
        </div>
        <p className="text-[12px] leading-snug text-white/55 mt-2.5">{t.rolesDesc[sesion.rol]}</p>
      </div>
      {VISTAS.some((v) => sesion.puede(v.rol)) && (
        <div className="flex flex-col border-t border-white/[0.06] py-1.5">
          {VISTAS.filter((v) => sesion.puede(v.rol)).map(({ id }) => {
            const Icono = SECCIONES[id].icon;
            return (
              <button
                key={id}
                onClick={() => elegir(() => onIr(id))}
                aria-current={active === id ? 'page' : undefined}
                className="fila-dd fila-cuenta"
              >
                <Icono className="w-4 h-4" style={{ color: SECCIONES[id].color }} aria-hidden />
                {t.nav[id]}
                {active === id && <span className="punto-actual ml-auto" aria-hidden />}
              </button>
            );
          })}
        </div>
      )}
      <div className="flex flex-col border-t border-white/[0.06] pt-1.5">
        <button onClick={() => elegir(onReporte)} className="fila-dd fila-cuenta">
          <FileDown className="w-4 h-4 text-white/60" aria-hidden />
          {t.cuenta.reporte}
        </button>
        <button onClick={() => elegir(() => setCambiando(true))} className="fila-dd fila-cuenta">
          <KeyRound className="w-4 h-4 text-white/60" aria-hidden />
          {t.cuenta.contrasena}
        </button>
        <button onClick={() => elegir(sesion.salir)} className="fila-dd fila-cuenta">
          <LogOut className="w-4 h-4 text-[var(--agent-coral)]" aria-hidden />
          {t.cuenta.salir}
        </button>
      </div>
    </div>
  );

  return (
    <>
      {enHoja ? (
        contenido
      ) : (
        <div ref={caja} className="relative">
          <button
            onClick={() => setAbierto((a) => !a)}
            aria-label={t.cuenta.abrir}
            aria-expanded={abierto}
            aria-haspopup="true"
            className="boton-cuenta"
            data-capture-toggle
          >
            <span className="avatar-cuenta" aria-hidden>
              {sesion.usuario.slice(0, 1).toUpperCase()}
            </span>
            {/* el rol va envuelto: `.rol-cuenta` fija su propio display y le ganaría a `hidden` */}
            <span className="hidden min-[1281px]:inline-flex">
              <span className="rol-cuenta" data-rol={sesion.rol}>
                {t.roles[sesion.rol]}
              </span>
            </span>
          </button>
          <div className="ajustes menu-cuenta" data-abierta={abierto ? 'si' : undefined}>
            {contenido}
          </div>
        </div>
      )}
      <CambioDeContrasena abierto={cambiando} onCerrar={() => setCambiando(false)} />
    </>
  );
}

function CambioDeContrasena({ abierto, onCerrar }: { abierto: boolean; onCerrar: () => void }) {
  const { t } = useI18n();
  const c = t.cuenta;
  const [actual, setActual] = useState('');
  const [nueva, setNueva] = useState('');
  const [repetida, setRepetida] = useState('');
  const [estado, setEstado] = useState<{ error?: string; hecho?: boolean; enviando?: boolean }>({});

  useEffect(() => {
    if (!abierto) {
      setActual('');
      setNueva('');
      setRepetida('');
      setEstado({});
    }
  }, [abierto]);

  const guardar = async (e: FormEvent) => {
    e.preventDefault();
    if (nueva.length < MINIMO) return setEstado({ error: c.minimo(MINIMO) });
    if (nueva !== repetida) return setEstado({ error: c.noCoinciden });
    setEstado({ enviando: true });
    try {
      await api.cambiarContrasena(actual, nueva);
      setEstado({ hecho: true });
    } catch (err) {
      setEstado({ error: err instanceof Error ? err.message : String(err) });
    }
  };

  return (
    <Modal abierto={abierto} onCerrar={onCerrar} titulo={c.contrasena} opaco>
      {estado.hecho ? (
        <div className="flex flex-col gap-4">
          <p className="text-[14px] text-white/80">{c.hecho}</p>
          <button onClick={onCerrar} className="boton-formulario self-end">
            {t.reporte.cerrar}
          </button>
        </div>
      ) : (
        <form onSubmit={guardar} className="flex flex-col gap-3">
          {(
            [
              [c.actual, actual, setActual, 'current-password'],
              [c.nueva, nueva, setNueva, 'new-password'],
              [c.repetir, repetida, setRepetida, 'new-password'],
            ] as const
          ).map(([rotulo, valor, poner, auto]) => (
            <label key={rotulo} className="flex flex-col gap-1.5">
              <span className="text-[12px] text-white/60">{rotulo}</span>
              <input
                type="password"
                value={valor}
                onChange={(e) => poner(e.target.value)}
                autoComplete={auto}
                className="campo-formulario"
                maxLength={256}
              />
            </label>
          ))}
          <p className="min-h-[18px] text-[12.5px] text-[var(--agent-coral)]" role="alert">
            {estado.error}
          </p>
          <div className="flex justify-end gap-2">
            <button type="button" onClick={onCerrar} className="boton-formulario" data-tipo="suave">
              {c.cancelar}
            </button>
            <button type="submit" className="boton-formulario" disabled={estado.enviando}>
              {estado.enviando ? c.guardando : c.guardar}
            </button>
          </div>
        </form>
      )}
    </Modal>
  );
}
