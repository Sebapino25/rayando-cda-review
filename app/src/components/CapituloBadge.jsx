// Capítulo del programa del que salió el clip. Solo lectura: si está mal se
// corrige con pipeline/corregir_capitulo.py (también arregla YouTube).
// Clips sin capítulo (anteriores al cap. 80, extraordinarios sin marcar o
// programas sin capítulos, como SPA) no muestran nada.
export default function CapituloBadge({ capitulo }) {
  if (capitulo === null || capitulo === undefined) return null
  return (
    <span className="inline-flex w-fit items-center rounded-full bg-muted px-2.5 py-1 text-xs font-semibold text-muted-foreground">
      Cap. {capitulo}
    </span>
  )
}
