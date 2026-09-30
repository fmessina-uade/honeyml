import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';

export type Preferencia = 'sistema' | 'claro' | 'oscuro';
export type Tema = 'claro' | 'oscuro';

// La misma clave que lee el guion de index.html antes del primer pintado.
const CLAVE = 'honeyml-panel-tema';

const COLOR_DE_LA_BARRA: Record<Tema, string> = { oscuro: '#0d1117', claro: '#f4f1ea' };

function leerPreferencia(): Preferencia {
  try {
    const guardada = localStorage.getItem(CLAVE);
    return guardada === 'claro' || guardada === 'oscuro' ? guardada : 'sistema';
  } catch {
    return 'sistema';
  }
}

const consultaClara = () => window.matchMedia('(prefers-color-scheme: light)');

function resolver(preferencia: Preferencia): Tema {
  if (preferencia !== 'sistema') return preferencia;
  return consultaClara().matches ? 'claro' : 'oscuro';
}

interface ValorDelTema {
  preferencia: Preferencia;
  tema: Tema;
  elegir: (p: Preferencia) => void;
}

const Contexto = createContext<ValorDelTema | null>(null);

/**
 * El tema del panel, a elección de quien lo mira. No hay usuarios identificados, así que la
 * preferencia vive en el navegador, como el idioma. Mientras no se elija nada, sigue al sistema y
 * cambia con él.
 */
export function TemaProvider({ children }: { children: ReactNode }) {
  const [preferencia, setPreferencia] = useState<Preferencia>(leerPreferencia);
  const [tema, setTema] = useState<Tema>(() => resolver(leerPreferencia()));

  useEffect(() => {
    const aplicar = () => setTema(resolver(preferencia));
    aplicar();
    if (preferencia !== 'sistema') return;
    const consulta = consultaClara();
    consulta.addEventListener('change', aplicar);
    return () => consulta.removeEventListener('change', aplicar);
  }, [preferencia]);

  useEffect(() => {
    document.documentElement.dataset.tema = tema;
    document
      .querySelector('meta[name="theme-color"]')
      ?.setAttribute('content', COLOR_DE_LA_BARRA[tema]);
  }, [tema]);

  const elegir = (p: Preferencia) => {
    setPreferencia(p);
    try {
      localStorage.setItem(CLAVE, p);
    } catch {
      // sin almacenamiento la elección dura lo que dura la pestaña
    }
  };

  return <Contexto.Provider value={{ preferencia, tema, elegir }}>{children}</Contexto.Provider>;
}

export function useTema(): ValorDelTema {
  const valor = useContext(Contexto);
  if (!valor) throw new Error('useTema va dentro de TemaProvider');
  return valor;
}
