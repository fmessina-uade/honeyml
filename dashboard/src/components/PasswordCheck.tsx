import { useState } from 'react';
import { ShieldCheck, ShieldAlert, Lock, Loader2 } from 'lucide-react';
import { api } from '../lib/api';
import { useI18n } from '../lib/i18n';
import { n } from '../lib/format';

type Result = { found: boolean; count: number } | null;

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
 * contradiría todo lo que el panel argumenta, así que el mecanismo se muestra en vez de esconderse.
 */
export default function PasswordCheck() {
  const { t } = useI18n();
  const [value, setValue] = useState('');
  const [result, setResult] = useState<Result>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  async function check(e: React.FormEvent) {
    e.preventDefault();
    if (!value) return;
    setBusy(true);
    setFailed(false);
    setResult(null);
    try {
      const digest = await sha256Hex(value);
      const prefix = digest.slice(0, 5);
      const suffix = digest.slice(5);
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
    <div className="rounded-xl ring-1 ring-white/5 bg-white/[0.03] p-4">
      <div className="flex items-center gap-2">
        <Lock className="w-3.5 h-3.5 text-white/35" />
        <span className="text-[9px] uppercase tracking-wider text-white/35">
          {t.passcheck.title}
        </span>
      </div>
      <div className="text-[11px] text-white/50 mt-1.5 leading-relaxed">
        {t.passcheck.intro}
      </div>

      <form onSubmit={check} className="flex gap-2 mt-3 max-w-xl">
        <input
          type="password"
          value={value}
          onChange={(e) => {
            setValue(e.target.value);
            setResult(null);
          }}
          placeholder={t.passcheck.placeholder}
          autoComplete="off"
          spellCheck={false}
          className="flex-1 rounded-md bg-white/[0.04] ring-1 ring-white/10 focus:ring-white/25
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

      {result && (
        <div
          key={String(result.found) + result.count}
          className="section-in flex items-start gap-2.5 mt-3 rounded-lg p-3 ring-1"
          style={{
            background: result.found ? 'rgba(255,107,53,0.08)' : 'rgba(0,184,148,0.08)',
            borderColor: 'transparent',
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
              {result.found
                ? t.passcheck.foundBody(n(result.count))
                : t.passcheck.safeBody}
            </div>
          </div>
        </div>
      )}

      {/* The mechanism is part of the lesson, so it is stated rather than buried. */}
      <div className="text-[10px] text-white/30 mt-3 leading-relaxed">
        {t.passcheck.privacy}
      </div>
    </div>
  );
}
