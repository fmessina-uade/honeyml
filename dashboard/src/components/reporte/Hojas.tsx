import type { ReactNode } from 'react';
import type { Bucket, ReporteGeneral } from '../../lib/api';
import { compacto, duracion, localeActual, n, nombreDePais, pct } from '../../lib/format';
import { useI18n } from '../../lib/i18n';
import { WORLD } from '../../lib/world';

/**
 * Las hojas A4 del reporte general. Se usan dos veces: achicadas en la vista previa de la sección y
 * en tamaño real para imprimir.
 *
 * Todos los colores son sólidos, sin transparencias ni degradados: al imprimir, algunos navegadores
 * aplanan un degradado translúcido en un bloque de color pleno que tapa lo que tiene encima. Por
 * eso los tonos intermedios del ámbar van calculados sobre el fondo y escritos como hex.
 */

export type Parte = 'captura' | 'origen' | 'credenciales' | 'motor';
export const PARTES: Parte[] = ['captura', 'origen', 'credenciales', 'motor'];

const C = {
  fondo: '#0d1117',
  panel: '#141a22',
  linea: '#232b36',
  pista: '#1a212b',
  texto: '#e8edf3',
  tenue: '#8d97a5',
  apagado: '#58626f',
  ambar: '#d4860a',
  teal: '#00b894',
  coral: '#ff6b35',
  pizarra: '#94a3b8',
  critico: '#e03131',
};

// La escala de la colmena-calendario: del panel vacío al ámbar de la marca, mezclado sobre el fondo.
const ESCALA = ['#161c24', '#2b2213', '#4a3311', '#76500f', '#a8690c', '#d4860a'];

const SEVERIDAD: Record<string, string> = {
  informativo: C.pizarra,
  bajo: C.teal,
  medio: C.ambar,
  alto: C.coral,
  critico: C.critico,
};
const ORDEN_SEVERIDAD = ['critico', 'alto', 'medio', 'bajo', 'informativo'];

const fechaLarga = (dia: string) =>
  new Date(`${dia}T00:00:00Z`).toLocaleDateString(localeActual(), {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  });

const fechaCorta = (dia: string) =>
  new Date(`${dia}T00:00:00Z`).toLocaleDateString(localeActual(), {
    day: '2-digit',
    month: '2-digit',
    timeZone: 'UTC',
  });

export interface Generado {
  fecha: string;
  usuario: string;
  rol: string;
}

export function rangoDelReporte(datos: ReporteGeneral): [string, string] {
  const c = datos.captura;
  return [
    datos.desde ?? c.first_event?.slice(0, 10) ?? '',
    datos.hasta ?? c.last_event?.slice(0, 10) ?? '',
  ];
}

export default function Hojas({
  datos,
  partes,
  generado,
}: {
  datos: ReporteGeneral;
  partes: Parte[];
  generado: Generado;
}) {
  const total = 1 + partes.length;
  return (
    <>
      <Portada datos={datos} generado={generado} total={total} />
      {partes.map((parte, i) => {
        const numero = i + 2;
        if (parte === 'captura')
          return (
            <Captura key={parte} datos={datos} numero={numero} total={total} generado={generado} />
          );
        if (parte === 'origen')
          return (
            <Origen key={parte} datos={datos} numero={numero} total={total} generado={generado} />
          );
        if (parte === 'credenciales')
          return (
            <Credenciales
              key={parte}
              datos={datos}
              numero={numero}
              total={total}
              generado={generado}
            />
          );
        return (
          <Motor key={parte} datos={datos} numero={numero} total={total} generado={generado} />
        );
      })}
    </>
  );
}

// La hoja y lo que se repite en todas

function Hoja({
  children,
  numero,
  total,
  generado,
  portada = false,
}: {
  children: ReactNode;
  numero: number;
  total: number;
  generado: Generado;
  portada?: boolean;
}) {
  const { t } = useI18n();
  return (
    <section className="hoja-reporte" data-portada={portada ? 'si' : undefined}>
      {children}
      <footer className="hoja-pie">
        <span>{t.hoja.generado(generado.fecha, generado.usuario, generado.rol)}</span>
        <span className="hoja-numero">{`${String(numero).padStart(2, '0')} / ${String(total).padStart(2, '0')}`}</span>
      </footer>
    </section>
  );
}

function Cabeza({
  datos,
  numero,
  titulo,
}: {
  datos: ReporteGeneral;
  numero: number;
  titulo: string;
}) {
  const { t } = useI18n();
  const [desde, hasta] = rangoDelReporte(datos);
  return (
    <>
      <header className="hoja-cabeza">
        <span className="hoja-marca">
          <img src="/logo.png" alt="" width={20} height={20} />
          HoneyML
        </span>
        <span>
          {t.hoja.titulo}, {t.hoja.del(fechaCorta(desde), fechaCorta(hasta)).toLowerCase()}
        </span>
      </header>
      <h2 className="hoja-titulo">
        <span>{String(numero - 1).padStart(2, '0')}</span>
        {titulo}
      </h2>
    </>
  );
}

function Barras({
  filas,
  color,
  nombre = (k) => k,
  mono = false,
}: {
  filas: Bucket[];
  color: string | ((k: string) => string);
  nombre?: (k: string) => string;
  mono?: boolean;
}) {
  const { t } = useI18n();
  if (filas.length === 0) return <p className="hoja-vacio">{t.hoja.sinDatos}</p>;
  const maximo = Math.max(1, ...filas.map((f) => f.count));
  return (
    <ul className="hoja-barras">
      {filas.map((f) => (
        <li key={f.key}>
          <span className={mono ? 'hoja-nombre hoja-mono' : 'hoja-nombre'}>{nombre(f.key)}</span>
          <span className="hoja-pista">
            <span
              style={{
                width: `${Math.max(1.5, (f.count / maximo) * 100)}%`,
                background: typeof color === 'string' ? color : color(f.key),
              }}
            />
          </span>
          <span className="hoja-valor">{n(f.count)}</span>
        </li>
      ))}
    </ul>
  );
}

function Cifra({
  valor,
  rotulo,
  color = C.texto,
}: {
  valor: string;
  rotulo: string;
  color?: string;
}) {
  return (
    <div className="hoja-cifra">
      <span style={{ color }}>{valor}</span>
      <small>{rotulo}</small>
    </div>
  );
}

// La portada

function Colmena({ dias }: { dias: { date: string; count: number }[] }) {
  const { t } = useI18n();
  // Pasadas las diez semanas, un hexágono por día no entra en la hoja: se agrupan por semana.
  const semanal = dias.length > 70;
  const celdas = semanal
    ? Array.from({ length: Math.ceil(dias.length / 7) }, (_, i) => {
        const tramo = dias.slice(i * 7, i * 7 + 7);
        return { date: tramo[0].date, count: tramo.reduce((s, d) => s + d.count, 0) };
      })
    : dias;
  const maximo = Math.max(1, ...celdas.map((c) => c.count));
  const pico = celdas.reduce(
    (a, b) => (b.count > a.count ? b : a),
    celdas[0] ?? { date: '', count: 0 },
  );
  const columnas = 7;
  const r = 15;
  const ancho = Math.sqrt(3) * r;
  const filas = Math.ceil(celdas.length / columnas);
  const w = columnas * ancho + ancho / 2 + 4;
  const h = filas * r * 1.5 + r / 2 + 4;
  const tono = (v: number) =>
    v === 0
      ? ESCALA[0]
      : ESCALA[Math.min(ESCALA.length - 1, 1 + Math.floor((v / maximo) * (ESCALA.length - 1.001)))];

  return (
    <figure className="hoja-colmena">
      <svg
        viewBox={`0 0 ${w} ${h}`}
        role="img"
        aria-label={semanal ? t.hoja.calendarioSemanas : t.hoja.calendario}
      >
        {celdas.map((c, i) => {
          const fila = Math.floor(i / columnas);
          const col = i % columnas;
          const cx = 2 + ancho / 2 + col * ancho + (fila % 2 ? ancho / 2 : 0);
          const cy = 2 + r + fila * r * 1.5;
          const puntos = Array.from({ length: 6 }, (_, k) => {
            const a = (Math.PI / 3) * k - Math.PI / 6;
            return `${cx + (r - 1.2) * Math.cos(a)},${cy + (r - 1.2) * Math.sin(a)}`;
          }).join(' ');
          const esPico = c === pico && c.count > 0;
          return (
            <polygon
              key={c.date}
              points={puntos}
              fill={tono(c.count)}
              stroke={esPico ? C.coral : C.linea}
              strokeWidth={esPico ? 2 : 0.8}
            />
          );
        })}
      </svg>
      <figcaption>
        <span>{semanal ? t.hoja.calendarioSemanas : t.hoja.calendario}</span>
        <span className="hoja-leyenda">
          {t.hoja.menos}
          {ESCALA.map((c) => (
            <i key={c} style={{ background: c }} />
          ))}
          {t.hoja.mas}
        </span>
      </figcaption>
    </figure>
  );
}

function Portada({
  datos,
  generado,
  total,
}: {
  datos: ReporteGeneral;
  generado: Generado;
  total: number;
}) {
  const { t } = useI18n();
  const h = t.hoja;
  const c = datos.captura;
  const m = datos.motor;
  const [desde, hasta] = rangoDelReporte(datos);
  const pico = c.por_dia.reduce(
    (a, b) => (b.count > a.count ? b : a),
    c.por_dia[0] ?? { date: '', count: 0, logins: 0 },
  );
  const remoto = c.by_sensor.cowrie ?? 0;

  const frases = [
    h.frase1(fechaLarga(desde), fechaLarga(hasta), n(c.events), n(c.unique_ips)),
    c.events ? h.frase2(pct(remoto, c.events, 0)) : '',
    pico.count ? h.frase3(fechaLarga(pico.date), n(pico.count)) : '',
    c.logins ? h.frase4(n(c.logins), n(c.logins_success)) : '',
    m && m.total && m.mediana_s != null
      ? h.frase5(n(m.total), pct(m.copiadas, m.total, 1), duracion(m.mediana_s))
      : '',
  ].filter(Boolean);

  return (
    <Hoja numero={1} total={total} generado={generado} portada>
      <header className="portada-marca">
        <img src="/logo.png" alt="" width={44} height={44} />
        <span>HoneyML</span>
      </header>
      <div className="portada-titulos">
        <p className="portada-ceja">{t.acceso.insignia}</p>
        <h1>{h.titulo}</h1>
        <p className="portada-rango">{h.del(fechaLarga(desde), fechaLarga(hasta))}</p>
      </div>
      <div className="portada-cuerpo">
        <Colmena dias={c.por_dia} />
        <div className="portada-sintesis">
          <h3>{h.sintesis}</h3>
          {frases.map((f) => (
            <p key={f}>{f}</p>
          ))}
        </div>
      </div>
      <div className="portada-cifras">
        <Cifra valor={n(c.events)} rotulo={h.eventos} color={C.ambar} />
        <Cifra valor={n(c.unique_ips)} rotulo={h.direcciones} color={C.teal} />
        <Cifra valor={n(c.logins_success)} rotulo={h.ingresos} color={C.coral} />
        <Cifra valor={n(c.commands)} rotulo={h.comandos} color={C.pizarra} />
      </div>
    </Hoja>
  );
}

// La captura

interface PropsDeHoja {
  datos: ReporteGeneral;
  numero: number;
  total: number;
  generado: Generado;
}

function PorDia({ dias }: { dias: { date: string; count: number; logins: number }[] }) {
  const { t } = useI18n();
  if (dias.length === 0) return <p className="hoja-vacio">{t.hoja.sinDatos}</p>;
  const W = 600;
  const H = 190;
  const izq = 42;
  const abajo = 22;
  const maximo = Math.max(1, ...dias.map((d) => d.count));
  const paso = (W - izq) / dias.length;
  const y = (v: number) => H - abajo - (v / maximo) * (H - abajo - 14);
  const pico = dias.reduce((a, b) => (b.count > a.count ? b : a), dias[0]);
  const iPico = dias.indexOf(pico);
  const linea = dias.map((d, i) => `${izq + paso * (i + 0.5)},${y(d.logins)}`).join(' ');
  const marcas = [0, Math.floor((dias.length - 1) / 2), dias.length - 1].filter(
    (v, i, a) => a.indexOf(v) === i,
  );
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="hoja-grafico">
      {[0, 0.5, 1].map((f) => (
        <g key={f}>
          <line
            x1={izq}
            x2={W}
            y1={y(maximo * f)}
            y2={y(maximo * f)}
            stroke={C.linea}
            strokeWidth={0.8}
          />
          <text x={izq - 6} y={y(maximo * f) + 3} textAnchor="end" className="hoja-eje">
            {compacto(maximo * f)}
          </text>
        </g>
      ))}
      {dias.map((d, i) => (
        <rect
          key={d.date}
          x={izq + paso * i + paso * 0.14}
          width={Math.max(0.8, paso * 0.72)}
          y={y(d.count)}
          height={H - abajo - y(d.count)}
          fill={i === iPico ? C.coral : C.ambar}
        />
      ))}
      <polyline
        points={linea}
        fill="none"
        stroke={C.teal}
        strokeWidth={1.6}
        strokeLinejoin="round"
      />
      <text
        x={Math.min(W - 4, izq + paso * (iPico + 0.5))}
        y={y(pico.count) - 5}
        textAnchor={iPico > dias.length * 0.8 ? 'end' : 'middle'}
        className="hoja-anota"
      >
        {t.hoja.pico(n(pico.count))}
      </text>
      {marcas.map((i) => {
        // la primera y la última se apoyan en su borde, así no se cortan contra el margen
        const ancla = i === 0 ? 'start' : i === dias.length - 1 ? 'end' : 'middle';
        const x = i === 0 ? izq : i === dias.length - 1 ? W : izq + paso * (i + 0.5);
        return (
          <text key={i} x={x} y={H - 6} textAnchor={ancla} className="hoja-eje">
            {fechaCorta(dias[i].date)}
          </text>
        );
      })}
    </svg>
  );
}

function PorHora({ horas }: { horas: number[] }) {
  const W = 300;
  const H = 120;
  const maximo = Math.max(1, ...horas);
  const paso = W / 24;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="hoja-grafico">
      <line x1={0} x2={W} y1={H - 16} y2={H - 16} stroke={C.linea} strokeWidth={0.8} />
      {horas.map((v, i) => {
        const alto = (v / maximo) * (H - 26);
        return (
          <rect
            key={i}
            x={i * paso + 1.5}
            width={paso - 3}
            y={H - 16 - alto}
            height={alto}
            fill={C.teal}
          />
        );
      })}
      {[0, 6, 12, 18, 23].map((hr) => (
        <text key={hr} x={hr * paso + paso / 2} y={H - 3} textAnchor="middle" className="hoja-eje">
          {String(hr).padStart(2, '0')}
        </text>
      ))}
    </svg>
  );
}

function Captura({ datos, numero, total, generado }: PropsDeHoja) {
  const { t } = useI18n();
  const h = t.hoja;
  const c = datos.captura;
  const remoto = c.by_sensor.cowrie ?? 0;
  const red = c.by_sensor.dionaea ?? 0;
  const suma = Math.max(1, remoto + red);
  return (
    <Hoja numero={numero} total={total} generado={generado}>
      <Cabeza datos={datos} numero={numero} titulo={t.reportes.partes.captura} />
      <div className="hoja-bloque">
        <h3 className="hoja-sub">
          {h.porDia}
          <span className="hoja-clave">
            <i style={{ background: C.ambar }} /> {h.eventos}
            <i style={{ background: C.teal }} /> {h.ingresosLinea}
          </span>
        </h3>
        <PorDia dias={c.por_dia} />
      </div>
      <div className="hoja-dos">
        <div className="hoja-bloque">
          <h3 className="hoja-sub">{h.porHora}</h3>
          <PorHora horas={c.por_hora} />
        </div>
        <div className="hoja-bloque">
          <h3 className="hoja-sub">{h.sensores}</h3>
          <div className="hoja-partida">
            <span style={{ width: `${(remoto / suma) * 100}%`, background: C.ambar }} />
            <span style={{ width: `${(red / suma) * 100}%`, background: '#60a5fa' }} />
          </div>
          <dl className="hoja-reparto">
            <div>
              <dt>
                <i style={{ background: C.ambar }} />
                {h.remoto}
              </dt>
              <dd>
                {n(remoto)} <small>{pct(remoto, suma, 1)} %</small>
              </dd>
            </div>
            <div>
              <dt>
                <i style={{ background: '#60a5fa' }} />
                {h.red}
              </dt>
              <dd>
                {n(red)} <small>{pct(red, suma, 1)} %</small>
              </dd>
            </div>
          </dl>
        </div>
      </div>
      <div className="hoja-bloque">
        <h3 className="hoja-sub">{h.protocolos}</h3>
        <table className="hoja-tabla">
          <thead>
            <tr>
              <th>{h.protocolo}</th>
              <th>{h.eventosCorto}</th>
              <th>{h.direccionesCorto}</th>
              <th>{h.parte}</th>
            </tr>
          </thead>
          <tbody>
            {c.protocolos.slice(0, 9).map((p) => (
              <tr key={p.protocol}>
                <td className="hoja-mono">{p.protocol}</td>
                <td>{n(p.count)}</td>
                <td>{n(p.sources)}</td>
                <td>
                  <span className="hoja-pista">
                    <span
                      style={{
                        width: `${(p.count / Math.max(1, c.events)) * 100}%`,
                        background: C.ambar,
                      }}
                    />
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Hoja>
  );
}

// El origen

function Mapa({ paises }: { paises: ReporteGeneral['captura']['paises'] }) {
  // Equirectangular recortado: de 84 al norte a 58 al sur, sin la Antártida, que no manda tráfico.
  const W = 360;
  const NORTE = 84;
  const SUR = -58;
  const H = NORTE - SUR;
  const px = (lon: number) => lon + 180;
  const py = (lat: number) => NORTE - lat;
  // Un contorno que cruza el antimeridiano salta de un borde al otro: ahí se corta el trazo, si no
  // queda una raya horizontal que atraviesa el mapa entero.
  const anillos = WORLD.map((anillo) => {
    let corta = false;
    const trazo = anillo
      .map(([lon, lat], i) => {
        const salta = i > 0 && Math.abs(lon - anillo[i - 1][0]) > 180;
        corta ||= salta;
        return `${i === 0 || salta ? 'M' : 'L'}${px(lon).toFixed(1)},${py(lat).toFixed(1)}`;
      })
      .join('');
    return corta ? trazo : `${trazo}Z`;
  }).join('');
  const conLugar = paises.filter((p) => p.lat != null && p.lon != null);
  const maximo = Math.max(1, ...conLugar.map((p) => p.count));
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="hoja-mapa">
      <rect width={W} height={H} fill={C.panel} />
      <path d={anillos} fill="#1d2530" stroke="#2a3441" strokeWidth={0.35} />
      {[...conLugar].reverse().map((p) => (
        <circle
          key={p.iso || p.country}
          cx={px(p.lon as number)}
          cy={py(p.lat as number)}
          r={1.6 + 9 * Math.sqrt(p.count / maximo)}
          fill={C.ambar}
          stroke={C.fondo}
          strokeWidth={0.7}
        />
      ))}
      {conLugar.slice(0, 5).map((p) => (
        <text
          key={`r-${p.iso}`}
          x={px(p.lon as number)}
          y={py(p.lat as number) - 3 - 9 * Math.sqrt(p.count / maximo)}
          textAnchor="middle"
          className="hoja-mapa-rotulo"
        >
          {p.iso}
        </text>
      ))}
    </svg>
  );
}

function Origen({ datos, numero, total, generado }: PropsDeHoja) {
  const { t } = useI18n();
  const h = t.hoja;
  const c = datos.captura;
  return (
    <Hoja numero={numero} total={total} generado={generado}>
      <Cabeza datos={datos} numero={numero} titulo={t.reportes.partes.origen} />
      <div className="hoja-bloque">
        <h3 className="hoja-sub">{h.mapa}</h3>
        <Mapa paises={c.paises} />
        <p className="hoja-nota">{h.cobertura(pct(c.con_geo, Math.max(1, c.events), 1))}</p>
      </div>
      <div className="hoja-dos hoja-dos-ancha">
        <div className="hoja-bloque">
          <h3 className="hoja-sub">{h.paises}</h3>
          <table className="hoja-tabla">
            <thead>
              <tr>
                <th>{h.pais}</th>
                <th>{h.eventosCorto}</th>
                <th>{h.direccionesCorto}</th>
              </tr>
            </thead>
            <tbody>
              {c.paises.slice(0, 10).map((p) => (
                <tr key={p.iso || p.country}>
                  <td>
                    <span className="hoja-iso">{p.iso}</span>
                    {nombreDePais(p.iso, p.country)}
                  </td>
                  <td>{n(p.count)}</td>
                  <td>{n(p.sources)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="hoja-bloque">
          <h3 className="hoja-sub">{h.redes}</h3>
          <table className="hoja-tabla">
            <thead>
              <tr>
                <th>{h.redCorta}</th>
                <th>{h.direccionesCorto}</th>
              </tr>
            </thead>
            <tbody>
              {c.sistemas.slice(0, 10).map((s) => (
                <tr key={s.organization}>
                  <td className="hoja-recorte">{s.organization}</td>
                  <td>{n(s.sources)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </Hoja>
  );
}

// Las credenciales

function Credenciales({ datos, numero, total, generado }: PropsDeHoja) {
  const { t } = useI18n();
  const h = t.hoja;
  const c = datos.captura;
  const maximo = Math.max(1, ...c.comandos.map((x) => x.count));
  return (
    <Hoja numero={numero} total={total} generado={generado}>
      <Cabeza datos={datos} numero={numero} titulo={t.reportes.partes.credenciales} />
      <div className="hoja-dos">
        <div className="hoja-bloque">
          <h3 className="hoja-sub">{h.usuarios}</h3>
          <Barras filas={c.usuarios} color={C.coral} mono />
        </div>
        <div className="hoja-bloque">
          <h3 className="hoja-sub">{h.contrasenas}</h3>
          <Barras filas={c.contrasenas} color={C.ambar} mono />
        </div>
      </div>
      <div className="hoja-bloque">
        <h3 className="hoja-sub">{h.comandosTop}</h3>
        <ol className="hoja-comandos">
          {c.comandos.map((x) => (
            <li key={x.key}>
              <code>{x.key.length > 96 ? `${x.key.slice(0, 95)}...` : x.key}</code>
              <span className="hoja-pista">
                <span style={{ width: `${(x.count / maximo) * 100}%`, background: C.pizarra }} />
              </span>
              <span className="hoja-valor">{n(x.count)}</span>
            </li>
          ))}
        </ol>
        <p className="hoja-nota">{h.comandosNota}</p>
      </div>
    </Hoja>
  );
}

// El motor

function Motor({ datos, numero, total, generado }: PropsDeHoja) {
  const { t } = useI18n();
  const h = t.hoja;
  const m = datos.motor;
  if (!m || m.total === 0) {
    return (
      <Hoja numero={numero} total={total} generado={generado}>
        <Cabeza datos={datos} numero={numero} titulo={t.reportes.partes.motor} />
        <p className="hoja-vacio">{h.sinMotor}</p>
      </Hoja>
    );
  }
  const severidades = ORDEN_SEVERIDAD.map((s) => ({
    key: s,
    count: m.por_severidad.find((b) => b.key === s)?.count ?? 0,
  })).filter((s) => s.count > 0);
  const nombreTactica = (k: string) =>
    k === 'ninguna' ? t.triage.noTactic : (t.tactics[k as keyof typeof t.tactics]?.name ?? k);
  return (
    <Hoja numero={numero} total={total} generado={generado}>
      <Cabeza datos={datos} numero={numero} titulo={t.reportes.partes.motor} />
      <div className="hoja-kpis">
        <Cifra valor={n(m.total)} rotulo={h.decisiones} color={C.ambar} />
        <Cifra valor={`${pct(m.copiadas, m.total, 1)} %`} rotulo={h.copiadas} color={C.teal} />
        <Cifra
          valor={m.mediana_s != null ? duracion(m.mediana_s) : '—'}
          rotulo={`${h.mediana}${m.p90_s != null ? `, ${h.p90(duracion(m.p90_s))}` : ''}`}
        />
        <Cifra
          valor={m.costo_usd.toLocaleString(localeActual(), { maximumFractionDigits: 2 })}
          rotulo={h.costo}
        />
        <Cifra valor={n(m.requieren)} rotulo={h.revision} color={C.coral} />
      </div>
      <div className="hoja-bloque">
        <h3 className="hoja-sub">{h.severidad}</h3>
        <div className="hoja-partida hoja-partida-alta">
          {severidades.map((s) => (
            <span
              key={s.key}
              style={{ width: `${(s.count / m.total) * 100}%`, background: SEVERIDAD[s.key] }}
            />
          ))}
        </div>
        <dl className="hoja-reparto hoja-reparto-cinco">
          {severidades.map((s) => (
            <div key={s.key}>
              <dt>
                <i style={{ background: SEVERIDAD[s.key] }} />
                {t.severities[s.key as keyof typeof t.severities] ?? s.key}
              </dt>
              <dd>
                {n(s.count)} <small>{pct(s.count, m.total, 1)} %</small>
              </dd>
            </div>
          ))}
        </dl>
      </div>
      <div className="hoja-dos">
        <div className="hoja-bloque">
          <h3 className="hoja-sub">{h.tactica}</h3>
          <Barras filas={m.por_tactica.slice(0, 8)} color={C.teal} nombre={nombreTactica} />
        </div>
        <div className="hoja-bloque">
          <h3 className="hoja-sub">{h.veredictos}</h3>
          <div className="hoja-veredictos">
            <Cifra valor={n(m.confirmadas)} rotulo={h.confirmadas} color={C.teal} />
            <Cifra valor={n(m.corregidas)} rotulo={h.corregidas} color={C.coral} />
            <Cifra valor={n(m.a_ciegas)} rotulo={h.aCiegas} color={C.ambar} />
          </div>
        </div>
      </div>
    </Hoja>
  );
}
