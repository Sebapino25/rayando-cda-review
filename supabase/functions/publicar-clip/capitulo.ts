// Línea "Del capítulo N de Rayando el CDA" + hashtag #RECDA<N> en la
// descripción de YouTube. Misma lógica que descripcion_con_capitulo en
// pipeline/publicar.py (y mismos textos que config.CAPITULO_*): al pasar el
// video a público la descripción se reescribe con la de la app, así que hay
// que volver a ponerlas. Sin capítulo, la descripción queda tal cual.
// Idempotente: quita una línea/hashtag de capítulo previo antes de agregar.
const LINEA_RE = /^[ \t]*Del capítulo \d+ de Rayando el CDA[ \t]*$/gm
const HASHTAG_RE = /[ \t]*#RECDA\d+\b/g

export function descripcionConCapitulo(descripcion: string, capitulo: number | null | undefined): string {
  if (capitulo === null || capitulo === undefined) return descripcion
  const limpia = (descripcion || '')
    .replace(LINEA_RE, '')
    .replace(HASHTAG_RE, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
  const cierre = `Del capítulo ${capitulo} de Rayando el CDA\n#RECDA${capitulo}`
  return limpia ? `${limpia}\n\n${cierre}` : cierre
}
