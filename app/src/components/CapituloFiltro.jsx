import { TODOS, SIN_CAPITULO, opcionesCapitulo } from '../lib/capitulo'

// Filtro por capítulo de "Por publicar", "Antiguas" y "Publicados". Las
// opciones salen de los clips ya cargados en la pestaña (no hay consulta
// aparte). Si ningún clip tiene capítulo (ej. SPA), no se muestra.
export default function CapituloFiltro({ clips, value, onChange }) {
  const { numeros, haySinCapitulo } = opcionesCapitulo(clips)
  if (numeros.length === 0) return null

  return (
    <label className="flex items-center gap-2 text-sm font-semibold text-foreground">
      Capítulo
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-10 px-3 rounded-xl border border-border bg-surface text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring cursor-pointer"
      >
        <option value={TODOS}>Todos</option>
        {numeros.map((n) => (
          <option key={n} value={String(n)}>
            Cap. {n}
          </option>
        ))}
        {haySinCapitulo && <option value={SIN_CAPITULO}>Sin capítulo</option>}
      </select>
    </label>
  )
}
