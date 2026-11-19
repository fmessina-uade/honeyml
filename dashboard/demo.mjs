// Publica el panel compilado en la red local, para abrirlo desde los teléfonos en una demostración.
//
// Sirve solo lo que dejó `vite build` en dist/, nunca el servidor de desarrollo: ese sirve los
// archivos del proyecto y no está hecho para quedar expuesto a una red. /api se reenvía al túnel de
// esta máquina, así los teléfonos nunca llegan al servidor: llegan acá, y acá se pide el ingreso.
import os from 'node:os';
import { preview } from 'vite';

const PUERTO = 4173;
const API = 'http://localhost:8000';

// /api/health arma los contadores de la portada sobre el índice entero, y en frío puede tardar
// varios segundos: con poco margen, el primer intento parece un túnel caído.
console.log('\n  Comprobando la API a través del túnel...');
try {
  const r = await fetch(`${API}/api/health`, { signal: AbortSignal.timeout(30000) });
  if (!r.ok) throw new Error(String(r.status));
} catch {
  console.error(
    `\n  La API no contesta en ${API}. Corré "make tunel" en otra terminal y volvé a probar.\n`,
  );
  process.exit(1);
}

await preview({
  preview: {
    host: '0.0.0.0',
    port: PUERTO,
    strictPort: true,
    proxy: { '/api': API },
    headers: {
      'X-Content-Type-Options': 'nosniff',
      'X-Frame-Options': 'DENY',
      'Referrer-Policy': 'no-referrer',
    },
  },
});

// Las direcciones de esta máquina en las redes a las que está conectada. Con el hotspot del
// teléfono suele ser una sola; si hay varias, la buena es la de la red a la que se suman los demás.
const direcciones = Object.values(os.networkInterfaces())
  .flat()
  .filter((i) => i && i.family === 'IPv4' && !i.internal)
  .map((i) => i.address);

console.log('\n  Panel de HoneyML publicado en la red local.\n');
for (const d of direcciones) console.log(`    http://${d}:${PUERTO}`);
if (direcciones.length === 0)
  console.log('    Sin red: conectá esta máquina al hotspot y volvé a correrlo.');
console.log('\n  Los teléfonos tienen que estar en la misma red. Ctrl+C para cerrar.\n');
