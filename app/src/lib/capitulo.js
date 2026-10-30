// Valores del filtro por capítulo (ver components/CapituloFiltro.jsx).
export const TODOS = 'todos'
export const SIN_CAPITULO = 'sin'

const sinCapitulo = (c) => c.capitulo === null || c.capitulo === undefined

export function filtrarPorCapitulo(clips, filtro) {
  if (filtro === TODOS) return clips
  if (filtro === SIN_CAPITULO) return clips.filter(sinCapitulo)
  return clips.filter((c) => String(c.capitulo) === filtro)
}

export function opcionesCapitulo(clips) {
  const numeros = [...new Set(clips.filter((c) => !sinCapitulo(c)).map((c) => c.capitulo))].sort((a, b) => b - a)
  return { numeros, haySinCapitulo: clips.some(sinCapitulo) }
}
