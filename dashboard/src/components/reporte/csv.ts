// Los CSV de la reportería se arman en el navegador con lo que ya trajo el reporte del rango: así
// salen exactamente los mismos números que se ven en la vista previa y en la versión impresa, sin volver a
// consultar. Llevan la marca de orden de bytes adelante porque, sin ella, Excel lee las tildes como
// Latin-1.

const BOM = '\ufeff';

function celda(v: unknown): string {
  const texto = v === null || v === undefined ? '' : String(v);
  return /[",\r\n]/.test(texto) ? `"${texto.replace(/"/g, '""')}"` : texto;
}

export function armarCsv(columnas: string[], filas: unknown[][]): string {
  return BOM + [columnas, ...filas].map((fila) => fila.map(celda).join(',')).join('\r\n');
}

export function descargar(nombre: string, contenido: string): void {
  const url = URL.createObjectURL(new Blob([contenido], { type: 'text/csv;charset=utf-8' }));
  const enlace = document.createElement('a');
  enlace.href = url;
  enlace.download = nombre;
  document.body.appendChild(enlace);
  enlace.click();
  enlace.remove();
  // el navegador ya tomó el archivo; el enlace temporal no hace falta más
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
