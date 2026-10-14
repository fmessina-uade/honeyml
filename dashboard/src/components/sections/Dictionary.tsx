import type { Bucket } from '../../lib/api';
import Reveal from '../Reveal';
import Tooltip, { useTooltip } from '../Tooltip';
import { useI18n } from '../../lib/i18n';
import PasswordCheck from '../PasswordCheck';
import ManoAlzada from '../ManoAlzada';
import { Palabras } from '../Titular';
import { n, pct, dec } from '../../lib/format';

// Por qué los atacantes van a buscar justamente estas credenciales. Es la capa que convierte un
// ranking en una lección: el lector se va sabiendo qué cambiar en su propia máquina.
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
  user: 'A generic account common in unpersonalized system images.',
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

// Cuántos puestos del ranking se muestran con su explicación.
const PUESTOS = 8;
const PARECE_DIRECCION = /\d{1,3}\.\d{1,3}\.\d{1,3}/;

/**
 * Un ranking escrito como un diccionario: la palabra, cuántas veces se probó y su definición, que
 * es el motivo por el que el atacante la tiene en la lista.
 */
function Entradas({
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
  // la proporción se calcula sobre el ranking entero, así se ve la concentración y no solo el orden
  const total = buckets.reduce((a, b) => a + b.count, 0);
  const primero = buckets[0];
  const anchoPrimero = primero && total ? (primero.count / total) * 100 : 0;

  return (
    <div className="pliego">
      <Tooltip content={tip.content} at={tip.at} />
      <span className="ceja">{title}</span>
      <p className="text-[13px] text-white/50 mt-3 leading-relaxed">{hint}</p>

      {/* La concentración de un vistazo: el ranking entero como una sola tira, cada tramo del
          ancho de su parte. Lo que se anota es cuánto se lleva el primero solo. */}
      {primero && (
        <div className="relative pt-8 mt-2 mb-4">
          <div className="flex h-3 rounded-sm overflow-hidden ring-1 ring-white/5">
            {buckets.map((b, i) => (
              <div
                key={b.key}
                className="h-full"
                style={{
                  width: `${(b.count / total) * 100}%`,
                  background: `color-mix(in srgb, ${accent} ${Math.max(85 - i * 9, 12)}%, transparent)`,
                  borderRight: '1px solid rgba(13,17,23,0.7)',
                }}
              />
            ))}
          </div>
          <ManoAlzada
            trazos={[
              {
                tipo: 'elipse',
                x: anchoPrimero / 2,
                y: 85,
                ancho: anchoPrimero + 5,
                alto: 70,
              },
            ]}
            notas={[
              {
                x: 1,
                y: -6,
                texto: t.dictionary.noteTop(
                  primero.key || t.dictionary.empty,
                  pct(primero.count, total, 0),
                ),
                ancho: 300,
              },
            ]}
          />
        </div>
      )}

      <ol className="bar-group flex flex-col mt-2">
        {buckets.slice(0, PUESTOS).map((b, i) => (
          <li
            key={b.key}
            className="entrada bar-item"
            onMouseMove={(e) =>
              tip.show(
                e,
                <div className="min-w-[150px]">
                  <div className="font-data text-[12px] text-white/90">
                    {b.key || t.dictionary.empty}
                  </div>
                  <div className="cifra-chica text-white mt-0.5">{n(b.count)}</div>
                  <div className="text-[10px] text-white/45 mt-0.5">{unit}</div>
                  <div className="flex items-center justify-between gap-4 text-[10px] text-white/40 mt-1.5 pt-1.5 border-t border-white/8">
                    <span>
                      {pct(b.count, total)}% {t.dictionary.ofTop}
                    </span>
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
            <div className="flex items-baseline gap-3 flex-wrap">
              <span className="entrada-palabra" style={i === 0 ? { color: accent } : undefined}>
                {b.key || t.dictionary.empty}
              </span>
              <span className="font-data text-[11px] text-white/45">{n(b.count)}</span>
              <span className="ml-auto font-data text-[10px] text-white/25">{i + 1}</span>
            </div>
            <div className="h-[3px] rounded bg-white/5 mt-2 overflow-hidden">
              <div
                className="h-full rounded transition-all duration-700"
                style={{
                  width: `${(b.count / max) * 100}%`,
                  background: accent,
                  transitionDelay: `${i * 60}ms`,
                }}
              />
            </div>
            {notes[b.key] && <p className="entrada-definicion">{notes[b.key]}</p>}
          </li>
        ))}
      </ol>
    </div>
  );
}

/** Credenciales y comandos, cada uno con el motivo detrás. */
export default function Dictionary({ users, passwords }: { users: Bucket[]; passwords: Bucket[] }) {
  const { t, lang } = useI18n();
  const usuario = users[0];
  const clave = passwords[0];
  // La pared del fondo son las mismas credenciales que muestra el ranking, repetidas. Solo los
  // puestos visibles, y sin nada con forma de dirección: hay atacantes que prueban como usuario la
  // dirección del propio señuelo, y esa no se publica.
  const pared = [...users.slice(0, PUESTOS), ...passwords.slice(0, PUESTOS)]
    .map((b) => b.key || t.dictionary.empty)
    .filter((k) => !PARECE_DIRECCION.test(k))
    .join('   ');

  return (
    <section className="flex flex-col gap-14">
      {/* La presentación: un cartel con el usuario y la contraseña que más se prueban */}
      <div className="presentacion presentacion-diccionario">
        <div className="pared-de-claves" aria-hidden>
          {Array.from({ length: 18 }, (_, i) => (
            <p key={i} style={{ marginLeft: `${-(i * 37) % 160}px` }}>
              {pared} {pared}
            </p>
          ))}
        </div>
        <div className="relative max-w-[1320px] mx-auto px-4 md:px-8 pt-12 sm:pt-16 pb-12 grid lg:grid-cols-[minmax(0,1.15fr)_minmax(0,420px)] gap-10 lg:gap-14 items-center">
          <div className="min-w-0">
            <span className="ceja section-in">{t.dictionary.heroBadge}</span>
            <h1 className="titulo-bloque mt-4 section-in">{t.nav.diccionario}</h1>
            {usuario && clave && (
              <div className="cartel mt-6">
                <div className="cartel-palabra" style={{ color: 'var(--honey-amber)' }}>
                  <Palabras texto={usuario.key || t.dictionary.empty} />
                </div>
                <div className="cartel-dato">
                  {n(usuario.count)} {t.dictionary.unitUsers}
                </div>
                <div className="cartel-palabra mt-3" style={{ color: 'var(--agent-coral)' }}>
                  <Palabras texto={clave.key || t.dictionary.empty} />
                </div>
                <div className="cartel-dato">
                  {n(clave.count)} {t.dictionary.unitPass}
                </div>
              </div>
            )}
            <p className="portada-bajada section-in">{t.lead.diccionario}</p>
          </div>
          <div className="min-w-0 section-in">
            <PasswordCheck />
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-12">
        <Reveal>
          <Entradas
            title={t.dictionary.usersTitle}
            hint={t.dictionary.usersHint}
            buckets={users}
            notes={lang === 'en' ? USER_NOTES_EN : USER_NOTES}
            accent="var(--honey-amber)"
            unit={t.dictionary.unitUsers}
          />
        </Reveal>
        <Reveal delay={120}>
          <Entradas
            title={t.dictionary.passTitle}
            hint={t.dictionary.passHint}
            buckets={passwords}
            notes={lang === 'en' ? PASS_NOTES_EN : PASS_NOTES}
            accent="var(--agent-coral)"
            unit={t.dictionary.unitPass}
          />
        </Reveal>
      </div>
      <p className="text-[13px] text-white/50 mt-8 leading-relaxed max-w-[48rem]">
        {t.dictionary.filterNote}
      </p>
    </section>
  );
}
