import type { Bucket } from '../lib/api';
import Reveal from './Reveal';

// Why attackers reach for these specific credentials. This is the layer that turns a ranking
// into a lesson: the reader leaves knowing what to change on their own machine.
const USER_NOTES: Record<string, string> = {
  root: 'Existe en prácticamente toda instalación de Linux, y es el único con control total. Por eso concentra la mayoría de los intentos: no hay que adivinar el nombre de usuario.',
  admin: 'Nombre por defecto en routers, cámaras y paneles web. Se prueba apenas falla root.',
  user: 'Usuario genérico habitual en imágenes de sistema sin personalizar.',
  ubuntu: 'Usuario que crean por defecto las imágenes de Ubuntu en la nube.',
  test: 'Cuenta de prueba que alguien creó para algo puntual y quedó olvidada. Clásico olvido.',
  postgres: 'Usuario de servicio de la base de datos. Da acceso directo a los datos.',
  pi: 'Usuario por defecto de Raspberry Pi, con contraseña conocida por todos.',
  oracle: 'Usuario de servicio de Oracle, común en servidores corporativos.',
  git: 'Usuario de servicios de repositorios, a veces con acceso a código propietario.',
  deploy: 'Cuenta de despliegue automatizado, suele tener permisos amplios.',
};

const PASS_NOTES: Record<string, string> = {
  '123456': 'La contraseña más filtrada de la historia. Aparece primera en todos los diccionarios.',
  '123': 'Contraseña mínima que muchos sistemas todavía aceptan.',
  '1234': 'Variante corta, habitual en dispositivos con teclado numérico.',
  password: 'La palabra misma. Sigue siendo de las primeras que se prueban.',
  admin: 'Contraseña igual al usuario: el patrón por defecto más repetido en dispositivos.',
  root: 'Contraseña igual al usuario, otra vez.',
  '12345678': 'Cumple el mínimo de ocho caracteres sin aportar ninguna seguridad real.',
  '': 'Contraseña vacía: el dispositivo nunca fue configurado.',
};

function Panel({
  title,
  hint,
  buckets,
  notes,
  accent,
}: {
  title: string;
  hint: string;
  buckets: Bucket[];
  notes: Record<string, string>;
  accent: string;
}) {
  const max = Math.max(...buckets.map((b) => b.count), 1);
  return (
    <div className="rounded-xl ring-1 ring-white/5 bg-white/[0.03] p-4">
      <div className="text-[9px] uppercase tracking-wider text-white/35">{title}</div>
      <div className="text-[11px] text-white/45 mt-1 mb-3 leading-relaxed">{hint}</div>
      <div className="flex flex-col gap-2.5">
        {buckets.slice(0, 8).map((b) => (
          <div key={b.key}>
            <div className="flex items-baseline justify-between">
              <span className="font-data text-[12px] text-white/85">{b.key || '(vacía)'}</span>
              <span className="font-data text-[10px] text-white/40">
                {b.count.toLocaleString('es-AR')}
              </span>
            </div>
            <div className="h-1 rounded bg-white/5 mt-1">
              <div
                className="h-1 rounded"
                style={{ width: `${(b.count / max) * 100}%`, background: accent }}
              />
            </div>
            {notes[b.key] && (
              <div className="text-[10px] text-white/45 mt-1.5 leading-relaxed">
                {notes[b.key]}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

/** Credentials and commands, each with the reason behind it. */
export default function Dictionary({
  users,
  passwords,
}: {
  users: Bucket[];
  passwords: Bucket[];
}) {
  return (
    <section className="grid md:grid-cols-2 gap-4">
      <Reveal>
        <Panel
        title="Usuarios más probados"
        hint="Los atacantes no adivinan: prueban los nombres que casi siempre existen."
        buckets={users}
        notes={USER_NOTES}
          accent="var(--honey-amber)"
        />
      </Reveal>
      <Reveal delay={120}>
        <Panel
        title="Contraseñas más probadas"
        hint="Todas salen de diccionarios públicos armados con filtraciones reales."
        buckets={passwords}
        notes={PASS_NOTES}
          accent="var(--agent-coral)"
        />
      </Reveal>
    </section>
  );
}
