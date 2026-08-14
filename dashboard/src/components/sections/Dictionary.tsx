import type { Bucket } from '../../lib/api';
import Reveal from '../Reveal';
import Tooltip, { useTooltip } from '../Tooltip';
import { useI18n } from '../../lib/i18n';
import PasswordCheck from '../PasswordCheck';
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

const USER_NOTES_EN: Record<string, string> = {
  root: 'It exists on practically every Linux install, and it is the only account with full control. That is why it concentrates most attempts: there is no username to guess.',
  admin: 'The default name on routers, cameras and web panels. Tried as soon as root fails.',
  user: 'A generic account common in unpersonalised system images.',
  ubuntu: 'The account Ubuntu cloud images create by default.',
  test: 'A test account someone created for something specific and forgot about. A classic.',
  postgres: 'The database service account. It gives direct access to the data.',
  pi: 'The Raspberry Pi default account, with a password everybody knows.',
  oracle: 'The Oracle service account, common on corporate servers.',
  git: 'The account used by repository services, sometimes with access to proprietary code.',
  deploy: 'An automated deployment account, usually holding broad permissions.',
};

const PASS_NOTES_EN: Record<string, string> = {
  '123456': 'The most leaked password in history. It comes first in every dictionary.',
  '123': 'A minimal password that many systems still accept.',
  '1234': 'The short variant, common on devices with a numeric keypad.',
  password: 'The word itself. Still among the first ones tried.',
  admin: 'Password identical to the username: the most repeated default pattern on devices.',
  root: 'Password identical to the username, again.',
  '12345678': 'It meets the eight-character minimum without adding any real security.',
  '': 'An empty password: the device was never configured.',
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
  const { t } = useI18n();
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
                  <div className="font-data text-[12px] text-white/90">{b.key || t.dictionary.empty}</div>
                  <div className="font-data text-[15px] text-white mt-0.5">{n(b.count)}</div>
                  <div className="text-[10px] text-white/45 mt-0.5">{unit}</div>
                  <div className="flex items-center justify-between gap-4 text-[10px] text-white/40 mt-1.5 pt-1.5 border-t border-white/8">
                    <span>{pct(b.count, total)}% {t.dictionary.ofTop}</span>
                    <span className="font-data">#{i + 1}</span>
                  </div>
                  {i > 0 && (
                    <div className="text-[10px] text-white/35 mt-1">
                      {t.dictionary.timesLess(dec(buckets[0].count / b.count), buckets[0].key)}
                    </div>
                  )}
                </div>,
              )
            }
            onMouseLeave={tip.hide}
          >
            <div className="flex items-baseline justify-between">
              <span className="font-data text-[12px] text-white/85">{b.key || t.dictionary.empty}</span>
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
  const { t, lang } = useI18n();
  return (
    <section className="flex flex-col gap-4">
      <Reveal>
        <PasswordCheck />
      </Reveal>

      <div className="grid md:grid-cols-2 gap-4">
      <Reveal>
        <Panel
        title={t.dictionary.usersTitle}
        hint={t.dictionary.usersHint}
          buckets={users}
          notes={lang === "en" ? USER_NOTES_EN : USER_NOTES}
          accent="var(--honey-amber)"
          unit={t.dictionary.unitUsers}
        />
      </Reveal>
      <Reveal delay={120}>
        <Panel
        title={t.dictionary.passTitle}
        hint={t.dictionary.passHint}
          buckets={passwords}
          notes={lang === "en" ? PASS_NOTES_EN : PASS_NOTES}
          accent="var(--agent-coral)"
          unit={t.dictionary.unitPass}
        />
      </Reveal>
      </div>
    </section>
  );
}
