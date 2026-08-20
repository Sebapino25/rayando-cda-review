// Arma el cuerpo del recordatorio semanal de actualización manual de los
// números del media kit. Lógica pura (sin red ni Supabase) para poder
// testearla con Deno.test, siguiendo la convención del resto de las Edge
// Functions de este repo.

export interface StatsActuales {
  ig_seguidores: number | null
  ig_vistas_30d: number | null
  ig_interacciones_90d: number | null
  tiktok_seguidores: number | null
  tiktok_likes: number | null
  tiktok_video_top_vistas: number | null
  yt_suscriptores: number | null
  yt_vistas_historicas: number | null
  yt_vistas_30d: number | null
  programas_emitidos: number | null
  ig_actualizado_en: string | null
  tiktok_actualizado_en: string | null
  yt_actualizado_en: string | null
}

interface CampoManual {
  columna: keyof StatsActuales
  etiqueta: string
  donde: string
}

// Solo los campos que la página realmente lee (ver mediakit/app.js).
// `ig_alcance_90d` quedó en la tabla pero ningún elemento del HTML lo
// muestra, así que no se pide — es un número menos que juntar a mano.
export const CAMPOS_MANUALES: CampoManual[] = [
  { columna: 'ig_seguidores', etiqueta: 'Instagram · seguidores', donde: 'Instagram > Insights' },
  { columna: 'ig_vistas_30d', etiqueta: 'Instagram · vistas (30 días)', donde: 'Instagram > Insights > últimos 30 días' },
  { columna: 'ig_interacciones_90d', etiqueta: 'Instagram · interacciones (90 días)', donde: 'Instagram > Insights > últimos 90 días' },
  { columna: 'tiktok_seguidores', etiqueta: 'TikTok · seguidores', donde: 'TikTok Studio > Analytics' },
  { columna: 'tiktok_likes', etiqueta: 'TikTok · likes totales', donde: 'TikTok Studio > Analytics' },
  { columna: 'tiktok_video_top_vistas', etiqueta: 'TikTok · vistas (30 días)', donde: 'TikTok Studio > Analytics > últimos 30 días' },
  { columna: 'yt_suscriptores', etiqueta: 'YouTube · suscriptores', donde: 'YouTube Studio' },
  { columna: 'yt_vistas_historicas', etiqueta: 'YouTube · vistas totales', donde: 'YouTube Studio > todo el tiempo' },
  { columna: 'yt_vistas_30d', etiqueta: 'YouTube · vistas (últimos 28/30 días)', donde: 'YouTube Studio > últimos 28 días' },
]

// Días completos entre `iso` y `ahora`. Devuelve null si no hay timestamp
// (nunca se actualizó) para que quien llame decida qué texto mostrar, en
// vez de inventar un 0 que se leería como "actualizado hoy".
export function diasDesde(iso: string | null, ahora: Date): number | null {
  if (!iso) return null
  const ms = ahora.getTime() - new Date(iso).getTime()
  if (!Number.isFinite(ms)) return null
  return Math.floor(ms / (24 * 60 * 60 * 1000))
}

function textoAntiguedad(iso: string | null, ahora: Date): string {
  const dias = diasDesde(iso, ahora)
  if (dias === null) return 'nunca se actualizó a mano'
  if (dias === 0) return 'actualizado hoy'
  if (dias === 1) return 'actualizado ayer'
  return `actualizado hace ${dias} días`
}

function valorActual(valor: number | null): string {
  return valor === null || valor === undefined ? 'sin dato' : String(valor)
}

export function armarMensaje(stats: StatsActuales | null, ahora: Date): string {
  if (!stats) {
    return (
      'No se pudo leer la fila de rayando_cda.media_kit_stats para armar el recordatorio.\n' +
      'Revisar que la tabla tenga su fila única (id = true) — ver mediakit/README.md.'
    )
  }

  const lineas: string[] = []
  lineas.push('Los números del media kit se actualizan a mano desde que venció el trial de Windsor.ai (09/08/2026).')
  lineas.push('')
  lineas.push('Estado de cada plataforma:')
  lineas.push(`  - Instagram: ${textoAntiguedad(stats.ig_actualizado_en, ahora)}`)
  lineas.push(`  - TikTok:    ${textoAntiguedad(stats.tiktok_actualizado_en, ahora)}`)
  lineas.push(`  - YouTube:   ${textoAntiguedad(stats.yt_actualizado_en, ahora)}`)
  lineas.push('')
  lineas.push('Números que necesito, con el valor que está publicado hoy en la página:')
  lineas.push('')
  for (const campo of CAMPOS_MANUALES) {
    const actual = valorActual(stats[campo.columna] as number | null)
    lineas.push(`  ${campo.etiqueta}`)
    lineas.push(`      hoy dice: ${actual}   |   dónde: ${campo.donde}`)
  }
  lineas.push('')

  const programas = stats.programas_emitidos
  const sugerido = typeof programas === 'number' ? programas + 1 : null
  lineas.push(
    `  Programas emitidos — hoy dice: ${valorActual(programas)}` +
      (sugerido !== null ? ` (si se emitió el programa de esta semana, va ${sugerido})` : ''),
  )
  lineas.push('')
  lineas.push('---')
  lineas.push('')
  lineas.push('Pasale estos números a Claude Code y él corre el UPDATE, o pegá esto directo en el SQL Editor')
  lineas.push('reemplazando los valores que hayan cambiado:')
  lineas.push('')
  lineas.push('update rayando_cda.media_kit_stats set')
  for (const campo of CAMPOS_MANUALES) {
    const actual = stats[campo.columna]
    lineas.push(`    ${campo.columna} = ${actual === null || actual === undefined ? 'null' : actual},`)
  }
  lineas.push(`    programas_emitidos = ${valorActual(programas) === 'sin dato' ? 'null' : programas},`)
  lineas.push('    ig_actualizado_en = now(),')
  lineas.push('    tiktok_actualizado_en = now(),')
  lineas.push('    yt_actualizado_en = now()')
  lineas.push('where id = true;')
  lineas.push('')
  lineas.push('La página no muestra ninguna fecha de actualización, así que un número atrasado no se delata solo —')
  lineas.push('pero tampoco se rompe nada ni se ve un error: quedan publicados los últimos valores buenos.')

  return lineas.join('\n')
}
