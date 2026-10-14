/**
 * El nombre del proyecto con "ML" en miel, como en el logo. Se dibuja siempre desde acá, así la
 * barra, el ingreso, el pie y el reporte no pueden quedar cada uno con su propia versión.
 */
export default function Marca({ className }: { className?: string }) {
  return (
    <span className={className ? `marca ${className}` : 'marca'}>
      Honey<span className="marca-ml">ML</span>
    </span>
  );
}
