import { useEffect, useState } from 'react';
import { ShieldCheck, ShieldAlert, Lock, Loader2 } from 'lucide-react';
import { api } from '../lib/api';
import { useI18n } from '../lib/i18n';
import { n } from '../lib/format';
import ManoAlzada from './ManoAlzada';
import { Hexagono } from './Instrumento';

type Result = { found: boolean; count: number } | null;

/** Cuántos caracteres del resumen salen del navegador. */
const PREFIJO = 5;

/** SHA-256 del texto tipeado, en hexadecimal, calculado en el navegador. */
async function sha256Hex(text: string): Promise<string> {
  const bytes = new TextEncoder().encode(text);
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

/**
 * Deja que un visitante compare su propia contraseña con las capturadas, sin mandarla.
 *
 * El navegador hashea localmente y pide solo los primeros cinco caracteres del resumen; el servicio
 * contesta con todos los hashes capturados que comparten ese prefijo y la comparación termina acá.
 * En un panel sobre ataques a credenciales, un formulario que transmitiera la contraseña
 * contradiría todo lo que el panel argumenta, así que el mecanismo se muestra en vez de esconderse:
 * después de comparar aparece el prefijo que viajó, y el resto del resumen queda como una franja
 * sin mostrar, porque en pantalla también se podría leer.
 */
export default function PasswordCheck() {
  const { t } = useI18n();
  const [value, setValue] = useState('');
  const [result, setResult] = useState<Result>(null);
  const [prefijo, setPrefijo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const [distintas, setDistintas] = useState<number | null>(null);

  // Contra cuántas se compara sale del índice vigente, así el texto no envejece con cada corte.
  useEffect(() => {
    api
      .passwordResumen()
      .then((r) => setDistintas(r.distintas))
      .catch(() => setDistintas(null));
  }, []);

  async function check(e: React.FormEvent) {
    e.preventDefault();
    if (!value) return;
    setBusy(true);
    setFailed(false);
    setResult(null);
    try {
      const digest = await sha256Hex(value);
      const prefix = digest.slice(0, PREFIJO);
      const suffix = digest.slice(PREFIJO);
      setPrefijo(prefix);
      const res = await api.passwordCheck(prefix);
      const hit = res.matches.find((m) => m.suffix === suffix);
      setResult({ found: Boolean(hit), count: hit?.count ?? 0 });
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="panel p-4">
      <div className="flex items-center gap-2.5">
        <Hexagono color="var(--honey-amber)">
          <Lock className="w-3.5 h-3.5" />
        </Hexagono>
        <span className="rotulo">{t.passcheck.title}</span>
      </div>
      <div className="text-[11px] text-white/50 mt-2 leading-relaxed">
        {t.passcheck.intro(distintas !== null ? n(distintas) : null)}
      </div>

      <form onSubmit={check} className="flex gap-2 mt-3 max-w-xl">
        <input
          type="password"
          value={value}
          onChange={(e) => {
            setValue(e.target.value);
            setResult(null);
            setPrefijo(null);
          }}
          placeholder={t.passcheck.placeholder}
          autoComplete="off"
          spellCheck={false}
          className="flex-1 min-w-0 rounded-md bg-white/[0.04] ring-1 ring-white/10 focus:ring-white/25
                     px-3 py-2 text-[12px] text-white/85 placeholder:text-white/25 outline-none
                     transition font-data"
        />
        <button
          type="submit"
          disabled={!value || busy}
          className="rounded-md px-3 py-2 text-[11px] font-medium transition
                     bg-[var(--honey-amber)]/15 text-[var(--honey-amber)]
                     ring-1 ring-[var(--honey-amber)]/30 hover:bg-[var(--honey-amber)]/25
                     disabled:opacity-30 disabled:cursor-not-allowed"
        >
          {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : t.passcheck.button}
        </button>
      </form>

      {failed && <div className="text-[11px] text-white/45 mt-3">{t.passcheck.failed}</div>}

      {/* Lo que salió del navegador, marcado a mano sobre el resumen */}
      {prefijo && !failed && (
        <div className="section-in mt-9 max-w-xl">
          <div className="flex items-center gap-2">
            <span className="relative inline-block font-data text-[13px] tracking-wider text-[var(--honey-amber)]">
              {prefijo}
              <ManoAlzada
                key={prefijo}
                acotar={false}
                trazos={[{ tipo: 'elipse', x: 50, y: 50, ancho: 160, alto: 190 }]}
                notas={[{ x: 0, y: -175, texto: t.passcheck.noteSent, ancho: 220 }]}
              />
            </span>
            <span
              className="flex-1 h-5 rounded-md ring-1 ring-white/10 flex items-center px-2 text-[9px] text-white/35 truncate"
              style={{
                background:
                  'repeating-linear-gradient(135deg, rgb(var(--tinta) / 0.06) 0 4px, transparent 4px 8px)',
              }}
            >
              {t.passcheck.restStays(64 - PREFIJO)}
            </span>
          </div>
          <div className="text-[10px] text-white/30 mt-1.5">{t.passcheck.hashTitle}</div>
        </div>
      )}

      {result && (
        <div
          key={String(result.found) + result.count}
          className="section-in flex items-start gap-2.5 mt-3 rounded-lg p-3"
          style={{
            background: result.found ? 'rgba(255,107,53,0.08)' : 'rgba(0,184,148,0.08)',
            boxShadow: `inset 0 0 0 1px ${result.found ? 'rgba(255,107,53,0.3)' : 'rgba(0,184,148,0.3)'}`,
          }}
        >
          {result.found ? (
            <ShieldAlert className="w-4 h-4 shrink-0 mt-0.5 text-[var(--agent-coral)]" />
          ) : (
            <ShieldCheck className="w-4 h-4 shrink-0 mt-0.5 text-[var(--neural-teal)]" />
          )}
          <div>
            <div className="text-[12px] text-white/85">
              {result.found ? t.passcheck.foundTitle : t.passcheck.safeTitle}
            </div>
            <div className="text-[11px] text-white/55 mt-1 leading-relaxed">
              {result.found ? t.passcheck.foundBody(n(result.count)) : t.passcheck.safeBody}
            </div>
          </div>
        </div>
      )}

      {/* El mecanismo es parte de la lección, así que se dice en vez de quedar escondido. */}
      <div className="text-[10px] text-white/30 mt-3 leading-relaxed">{t.passcheck.privacy}</div>
    </div>
  );
}
