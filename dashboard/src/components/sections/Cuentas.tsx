import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { KeyRound, Power, UserPlus } from 'lucide-react';
import { api, ROLES, type CambioDeCuenta, type Cuenta, type Rol } from '../../lib/api';
import { fechaHora } from '../../lib/format';
import { useI18n } from '../../lib/i18n';
import { alcanza, useSesion } from '../../lib/sesion';

const MINIMO = 10;
const NOMBRE = /^[a-z0-9][a-z0-9._-]{2,31}$/;

/**
 * La administración de cuentas. Arriba, la escalera de roles, encendida hasta donde llega quien
 * está mirando. Abajo, el alta y la lista. Solo se ofrecen los roles que quedan por debajo del
 * propio, que es lo mismo que exige la API.
 */
export default function Cuentas() {
  const { t } = useI18n();
  const c = t.cuentas;
  const sesion = useSesion();
  const [cuentas, setCuentas] = useState<Cuenta[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  const asignables = ROLES.filter((r) => ROLES.indexOf(r) < ROLES.indexOf(sesion.rol));

  const cargar = useCallback(() => {
    api
      .cuentas()
      .then(setCuentas)
      .catch((e) => setError(String(e.message ?? e)));
  }, []);
  useEffect(cargar, [cargar]);

  const cambiar = async (usuario: string, cambio: CambioDeCuenta, texto?: string) => {
    setError(null);
    try {
      await api.cambiarCuenta(usuario, cambio);
      setAviso(texto ?? null);
      cargar();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div className="flex flex-col gap-10">
      <ol className="escalera-roles" aria-label={c.rol}>
        {ROLES.map((rol, i) => (
          <li
            key={rol}
            data-rol={rol}
            data-propio={rol === sesion.rol ? 'si' : undefined}
            data-alcanza={alcanza(sesion.rol, rol) ? 'si' : undefined}
            style={{ '--escalon': i } as React.CSSProperties}
          >
            <span className="escalon-marca" aria-hidden />
            <span className="geist text-[15px] font-medium text-white">{t.roles[rol]}</span>
          </li>
        ))}
      </ol>

      <div className="grid gap-8 lg:grid-cols-[360px_1fr] items-start">
        <Alta
          roles={asignables}
          onCreada={(u) => {
            setAviso(c.creada(u));
            cargar();
          }}
        />

        <section className="pliego" aria-labelledby="lista-cuentas">
          <div className="flex items-baseline justify-between gap-3 flex-wrap">
            <h2 id="lista-cuentas" className="titulo-bloque">
              {c.lista}
            </h2>
            <p className="text-[12.5px] text-white/55 min-h-[18px]" role="status">
              {error ? <span className="text-[var(--agent-coral)]">{error}</span> : aviso}
            </p>
          </div>
          {cuentas && cuentas.length === 0 && (
            <p className="text-[13px] text-white/55 mt-5">{c.vacio}</p>
          )}
          <ul className="mt-4 flex flex-col">
            {cuentas?.map((cuenta) => (
              <FilaDeCuenta
                key={cuenta.usuario}
                cuenta={cuenta}
                roles={asignables}
                onCambio={cambiar}
              />
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}

function Alta({ roles, onCreada }: { roles: Rol[]; onCreada: (usuario: string) => void }) {
  const { t } = useI18n();
  const c = t.cuentas;
  const [usuario, setUsuario] = useState('');
  const [rol, setRol] = useState<Rol>(roles[roles.length - 1] === 'admin' ? 'analista' : roles[0]);
  const [contrasena, setContrasena] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  const crear = async (e: FormEvent) => {
    e.preventDefault();
    const nombre = usuario.trim().toLowerCase();
    if (!NOMBRE.test(nombre)) return setError(c.reglaUsuario);
    if (contrasena.length < MINIMO) return setError(t.cuenta.minimo(MINIMO));
    setEnviando(true);
    setError(null);
    try {
      await api.crearCuenta(nombre, rol, contrasena);
      setUsuario('');
      setContrasena('');
      onCreada(nombre);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setEnviando(false);
    }
  };

  return (
    <form onSubmit={crear} className="vidrio p-5 sm:p-6 flex flex-col gap-3.5">
      <div className="flex items-center gap-2.5">
        <UserPlus className="w-[18px] h-[18px] text-[var(--neural-teal)]" aria-hidden />
        <h2 className="geist text-[17px] font-medium text-white">{c.nueva}</h2>
      </div>
      <p className="text-[12.5px] leading-snug text-white/55 -mt-1">{c.nuevaBajada}</p>
      <label className="flex flex-col gap-1.5">
        <span className="text-[12px] text-white/60">{c.usuario}</span>
        <input
          value={usuario}
          onChange={(e) => setUsuario(e.target.value)}
          className="campo-formulario"
          autoComplete="off"
          autoCapitalize="none"
          spellCheck={false}
          maxLength={32}
        />
        <span className="text-[11px] text-white/45">{c.reglaUsuario}</span>
      </label>
      <fieldset className="flex flex-col gap-1.5">
        <legend className="text-[12px] text-white/60 mb-1.5">{c.rol}</legend>
        <div className="flex flex-wrap gap-1.5">
          {roles.map((r) => (
            <button
              key={r}
              type="button"
              onClick={() => setRol(r)}
              aria-pressed={rol === r}
              className="opcion-rol"
              data-rol={r}
            >
              {t.roles[r]}
            </button>
          ))}
        </div>
      </fieldset>
      <label className="flex flex-col gap-1.5">
        <span className="text-[12px] text-white/60">{c.contrasena}</span>
        <input
          type="password"
          value={contrasena}
          onChange={(e) => setContrasena(e.target.value)}
          className="campo-formulario"
          autoComplete="new-password"
          maxLength={256}
        />
      </label>
      <p className="min-h-[18px] text-[12.5px] text-[var(--agent-coral)]" role="alert">
        {error}
      </p>
      <button type="submit" className="boton-formulario" disabled={enviando}>
        {enviando ? c.creando : c.crear}
      </button>
    </form>
  );
}

function FilaDeCuenta({
  cuenta,
  roles,
  onCambio,
}: {
  cuenta: Cuenta;
  roles: Rol[];
  onCambio: (usuario: string, cambio: CambioDeCuenta, aviso?: string) => Promise<void>;
}) {
  const { t } = useI18n();
  const c = t.cuentas;
  const [clave, setClave] = useState<string | null>(null);

  return (
    <li className="fila-cuenta-admin" data-activa={cuenta.activo ? 'si' : undefined}>
      <span className="avatar-cuenta" aria-hidden>
        {cuenta.usuario.slice(0, 1).toUpperCase()}
      </span>
      <div className="min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="geist text-[15px] text-white">{cuenta.usuario}</span>
          {cuenta.administrable ? (
            <span className="flex gap-1">
              {roles.map((r) => (
                <button
                  key={r}
                  onClick={() => r !== cuenta.rol && onCambio(cuenta.usuario, { rol: r })}
                  aria-pressed={cuenta.rol === r}
                  className="opcion-rol opcion-rol-chica"
                  data-rol={r}
                >
                  {t.roles[r]}
                </button>
              ))}
            </span>
          ) : (
            <span className="rol-cuenta" data-rol={cuenta.rol} title={c.noAdministrable}>
              {t.roles[cuenta.rol]}
            </span>
          )}
          {!cuenta.activo && <span className="chip-baja">{c.deBaja}</span>}
        </div>
        <p className="text-[12px] text-white/50 mt-1">
          {cuenta.ultimo_ingreso ? c.ultimoIngreso(fechaHora(cuenta.ultimo_ingreso)) : c.nunca}
          {cuenta.creada_por && (
            <span className="text-white/35">, {c.creadaPor(cuenta.creada_por).toLowerCase()}</span>
          )}
        </p>
        {clave !== null && (
          <form
            className="flex gap-2 mt-2.5 flex-wrap"
            onSubmit={(e) => {
              e.preventDefault();
              if (clave.length < MINIMO) return;
              onCambio(cuenta.usuario, { contrasena: clave }, c.restablecida(cuenta.usuario));
              setClave(null);
            }}
          >
            <input
              type="password"
              value={clave}
              onChange={(e) => setClave(e.target.value)}
              className="campo-formulario flex-1 min-w-[180px]"
              autoComplete="new-password"
              placeholder={c.restablecer}
              aria-label={c.restablecer}
              autoFocus
            />
            <button type="submit" className="boton-formulario" disabled={clave.length < MINIMO}>
              {c.aplicar}
            </button>
            <span className="w-full text-[11px] text-white/45">{c.restablecerAyuda}</span>
          </form>
        )}
      </div>
      {cuenta.administrable && (
        <div className="flex gap-1.5 shrink-0">
          <button
            onClick={() => setClave((v) => (v === null ? '' : null))}
            className="boton-icono"
            title={c.restablecer}
            aria-label={`${c.restablecer}: ${cuenta.usuario}`}
          >
            <KeyRound className="w-4 h-4" />
          </button>
          <button
            onClick={() => onCambio(cuenta.usuario, { activo: !cuenta.activo })}
            className="boton-icono"
            data-peligro={cuenta.activo ? 'si' : undefined}
            title={cuenta.activo ? c.darDeBaja : c.reactivar}
            aria-label={`${cuenta.activo ? c.darDeBaja : c.reactivar}: ${cuenta.usuario}`}
          >
            <Power className="w-4 h-4" />
          </button>
        </div>
      )}
    </li>
  );
}
