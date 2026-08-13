import type { Bucket } from '../../lib/api';
import Reveal from '../Reveal';
import Tooltip, { useTooltip } from '../Tooltip';
import { n, pct, dec } from '../../lib/format';



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
  unit,
}: {
  title: string;
  hint: string;
  buckets: Bucket[];
  notes: Record<string, string>;
  accent: string;
  unit: string;
}) {
  const tip = useTooltip();
  const max = Math.max(...buckets.map((b) => b.count), 1);
  // share is computed over the whole ranking, so the reader sees concentration, not just order
  const total = buckets.reduce((a, b) => a + b.count, 0);

  return (
    <div className="rounded-xl ring-1 ring-white/5 bg-white/[0.03] p-4 h-full">
      <Tooltip content={tip.content} at={tip.at} />
      <div className="text-[9px] uppercase tracking-wider text-white/35">{title}</div>
      <div className="text-[11px] text-white/45 mt-1 mb-3 leading-relaxed">{hint}</div>
      <div className="bar-group flex flex-col gap-2.5">
        {buckets.slice(0, 8).map((b, i) => (
          <div
            key={b.key}
            className="bar-item transition-opacity duration-200 cursor-default"
            onMouseMove={(e) =>
              tip.show(
                e,
                <div className="min-w-[150px]">
                  <div className="font-data text-[12px] text-white/90">{b.key || '(vacía)'}</div>
                  <div className="font-data text-[15px] text-white mt-0.5">{n(b.count)}</div>
                  <div className="text-[10px] text-white/45 mt-0.5">{unit}</div>
                  <div className="flex items-center justify-between gap-4 text-[10px] text-white/40 mt-1.5 pt-1.5 border-t border-white/8">
                    <span>{pct(b.count, total)}% del top 10</span>
                    <span className="font-data">#{i + 1}</span>
                  </div>
                  {i > 0 && (
                    <div className="text-[10px] text-white/35 mt-1">
                      {dec(buckets[0].count / b.count)}× menos que{' '}
                      <span className="font-data">{buckets[0].key}</span>
                    </div>
                  )}
                </div>,
              )
            }
            onMouseLeave={tip.hide}
          >
            <div className="flex items-baseline justify-between">
              <span className="font-data text-[12px] text-white/85">{b.key || '(vacía)'}</span>
              <span className="font-data text-[10px] text-white/40">{n(b.count)}</span>
            </div>
            <div className="h-1 rounded bg-white/5 mt-1 overflow-hidden">
              <div
                className="h-1 rounded transition-all duration-700"
                style={{
                  width: `${(b.count / max) * 100}%`,
                  background: accent,
                  transitionDelay: `${i * 60}ms`,
                }}
              />
            </div>
            {notes[b.key] && (
              <div className="text-[10px] text-white/45 mt-1.5 leading-relaxed">{notes[b.key]}</div>
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
          unit="intentos de acceso con este usuario"
        />
      </Reveal>
      <Reveal delay={120}>
        <Panel
        title="Contraseñas más probadas"
        hint="Todas salen de diccionarios públicos armados con filtraciones reales."
          buckets={passwords}
          notes={PASS_NOTES}
          accent="var(--agent-coral)"
          unit="veces que se probó esta contraseña"
        />
      </Reveal>
    </section>
  );
}
