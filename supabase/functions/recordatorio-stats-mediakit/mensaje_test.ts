import { assertEquals, assertStringIncludes } from 'https://deno.land/std@0.224.0/assert/mod.ts'
import { armarMensaje, CAMPOS_MANUALES, diasDesde, type StatsActuales } from './mensaje.ts'

const AHORA = new Date('2026-08-10T13:00:00Z')

const STATS_COMPLETAS: StatsActuales = {
  ig_seguidores: 13678,
  ig_vistas_30d: 2544087,
  ig_interacciones_90d: 482341,
  tiktok_seguidores: 4544,
  tiktok_likes: 103010,
  tiktok_video_top_vistas: 74822,
  yt_suscriptores: 2320,
  yt_vistas_historicas: 1402342,
  yt_vistas_30d: 24896,
  programas_emitidos: 72,
  ig_actualizado_en: '2026-08-03T13:00:00Z',
  tiktok_actualizado_en: '2026-08-09T13:00:00Z',
  yt_actualizado_en: null,
}

Deno.test('diasDesde cuenta días completos', () => {
  assertEquals(diasDesde('2026-08-03T13:00:00Z', AHORA), 7)
  assertEquals(diasDesde('2026-08-10T12:00:00Z', AHORA), 0)
})

Deno.test('diasDesde devuelve null sin timestamp', () => {
  assertEquals(diasDesde(null, AHORA), null)
})

Deno.test('diasDesde devuelve null con un timestamp inválido', () => {
  assertEquals(diasDesde('no es una fecha', AHORA), null)
})

Deno.test('armarMensaje pide los 9 números que la página realmente lee', () => {
  const mensaje = armarMensaje(STATS_COMPLETAS, AHORA)
  assertEquals(CAMPOS_MANUALES.length, 9)
  for (const campo of CAMPOS_MANUALES) {
    assertStringIncludes(mensaje, campo.etiqueta)
    assertStringIncludes(mensaje, campo.donde)
  }
})

Deno.test('armarMensaje no pide ig_alcance_90d (la página no lo muestra)', () => {
  const mensaje = armarMensaje(STATS_COMPLETAS, AHORA)
  assertEquals(mensaje.includes('ig_alcance_90d'), false)
})

Deno.test('armarMensaje incluye el valor publicado hoy de cada campo', () => {
  const mensaje = armarMensaje(STATS_COMPLETAS, AHORA)
  assertStringIncludes(mensaje, '13678')
  assertStringIncludes(mensaje, '2544087')
  assertStringIncludes(mensaje, '74822')
})

Deno.test('armarMensaje traduce la antigüedad de cada plataforma', () => {
  const mensaje = armarMensaje(STATS_COMPLETAS, AHORA)
  assertStringIncludes(mensaje, 'Instagram: actualizado hace 7 días')
  assertStringIncludes(mensaje, 'TikTok:    actualizado ayer')
  assertStringIncludes(mensaje, 'YouTube:   nunca se actualizó a mano')
})

Deno.test('armarMensaje sugiere el siguiente número de programa', () => {
  const mensaje = armarMensaje(STATS_COMPLETAS, AHORA)
  assertStringIncludes(mensaje, 'hoy dice: 72 (si se emitió el programa de esta semana, va 73)')
})

Deno.test('armarMensaje arma un UPDATE con todas las columnas y los timestamps', () => {
  const mensaje = armarMensaje(STATS_COMPLETAS, AHORA)
  assertStringIncludes(mensaje, 'update rayando_cda.media_kit_stats set')
  assertStringIncludes(mensaje, 'ig_seguidores = 13678,')
  assertStringIncludes(mensaje, 'ig_actualizado_en = now(),')
  assertStringIncludes(mensaje, 'yt_actualizado_en = now()')
  assertStringIncludes(mensaje, 'where id = true;')
})

Deno.test('armarMensaje escribe null (no "sin dato") en el SQL de un campo vacío', () => {
  const mensaje = armarMensaje({ ...STATS_COMPLETAS, yt_vistas_30d: null }, AHORA)
  assertStringIncludes(mensaje, 'yt_vistas_30d = null,')
  // El bloque legible sí dice "sin dato" — solo el SQL tiene que ser válido.
  assertStringIncludes(mensaje, 'hoy dice: sin dato')
})

Deno.test('armarMensaje no explota si no hay fila y avisa qué revisar', () => {
  const mensaje = armarMensaje(null, AHORA)
  assertStringIncludes(mensaje, 'media_kit_stats')
  assertStringIncludes(mensaje, 'id = true')
})
