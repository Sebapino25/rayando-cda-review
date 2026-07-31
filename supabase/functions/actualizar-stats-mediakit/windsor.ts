// Cliente de la API de Windsor.ai (https://connectors.windsor.ai) — trae
// los números de Instagram, TikTok y YouTube de Rayando el CDA desde los
// 3 connectors ya conectados en la cuenta de Windsor.ai del usuario
// (nombres exactos: "instagram", "tiktok_organic", "youtube").
//
// Cada connector se llama por separado y falla por separado — si uno cae,
// los otros dos igual deben poder guardarse (ver index.ts).

const WINDSOR_BASE = 'https://connectors.windsor.ai'

export class WindsorError extends Error {}

export async function fetchWindsorConnector(
  connector: string,
  fields: string[],
  datePreset: string | null,
  apiKey: string,
  fetchImpl: typeof fetch = fetch,
): Promise<Record<string, unknown>> {
  const params = new URLSearchParams({ api_key: apiKey, fields: fields.join(',') })
  if (datePreset) params.set('date_preset', datePreset)
  const url = `${WINDSOR_BASE}/${connector}?${params.toString()}`

  const resp = await fetchImpl(url)
  if (!resp.ok) {
    throw new WindsorError(`Windsor.ai (${connector}) devolvió ${resp.status}: ${await resp.text()}`)
  }
  const body = await resp.json()
  const fila = body?.data?.[0]
  if (!fila) {
    throw new WindsorError(`Windsor.ai (${connector}) no devolvió datos (respuesta: ${JSON.stringify(body)})`)
  }
  // No lanza: algunas llamadas legítimas (ej. stats de canal de YouTube)
  // devuelven varias filas idénticas a propósito. Pero quedarse callado acá
  // es justo lo que dejó pasar sin ser detectado el bug real de agregación
  // (ver notas más abajo) — si alguna vez vuelve a pasar algo parecido, que
  // quede en los logs en vez de en silencio.
  if (Array.isArray(body?.data) && body.data.length > 1) {
    console.warn(`Windsor.ai (${connector}) devolvió ${body.data.length} filas, se usó solo la primera`)
  }
  return fila
}

// Convierte a número y valida que sea finito — un campo de Windsor.ai
// renombrado/eliminado hace que `fila[campo]` venga `undefined`, y
// `Number(undefined)` es `NaN`, que Supabase serializa como `null` sin
// tirar ningún error (columna queda NULL en silencio, sin entrar en el
// array `fallas` de index.ts ni disparar alerta). Lanzar acá convierte ese
// caso en una falla normal por plataforma, ya manejada arriba.
function campoNumerico(plataforma: string, campo: string, valor: unknown): number {
  const n = Number(valor)
  if (!Number.isFinite(n)) {
    throw new WindsorError(`${plataforma}: campo '${campo}' no vino como número (${valor})`)
  }
  return n
}

export interface InstagramStats {
  seguidores: number
  vistas30d: number
  alcance90d: number
  interacciones90d: number
}

// Nota (bug real encontrado en producción, ver plan
// docs/superpowers/plans/2026-07-30-media-kit-vivo.md): `views`/
// `total_interactions` viven en la tabla interna `user_insights_day_total_value`
// de Windsor.ai, mientras que `reach_1d` vive en `user_insights_day` — pedirlos
// juntos en una sola consulta rompe el auto-agregado de Windsor.ai (devuelve
// filas por día en vez de una fila con el total del período). Por eso
// `reach_1d` va en su propia consulta, separada de `views`/`total_interactions`.
export async function fetchInstagramStats(apiKey: string, fetchImpl: typeof fetch = fetch): Promise<InstagramStats> {
  const [seguidoresFila, vistasFila, interaccionesFila, alcanceFila] = await Promise.all([
    fetchWindsorConnector('instagram', ['followers_count'], null, apiKey, fetchImpl),
    fetchWindsorConnector('instagram', ['views'], 'last_30d', apiKey, fetchImpl),
    fetchWindsorConnector('instagram', ['total_interactions'], 'last_90d', apiKey, fetchImpl),
    fetchWindsorConnector('instagram', ['reach_1d'], 'last_90d', apiKey, fetchImpl),
  ])
  return {
    seguidores: campoNumerico('Instagram', 'followers_count', seguidoresFila.followers_count),
    vistas30d: campoNumerico('Instagram', 'views', vistasFila.views),
    alcance90d: campoNumerico('Instagram', 'reach_1d', alcanceFila.reach_1d),
    interacciones90d: campoNumerico('Instagram', 'total_interactions', interaccionesFila.total_interactions),
  }
}

export interface TiktokStats {
  seguidores: number
  likes: number
  videoTopVistas: number
}

// Nota (mismo bug de producción): `video_views_count` es un campo a nivel de
// video individual (devolvía el video más visto, no el total de la cuenta).
// El campo correcto a nivel de cuenta es `video_views` — pasa a representar
// "vistas de video de la cuenta en 30 días", no "vistas del video más visto"
// (el nombre `videoTopVistas` se mantiene sin cambio para no tocar más
// archivos de los necesarios, ver el plan).
export async function fetchTiktokStats(apiKey: string, fetchImpl: typeof fetch = fetch): Promise<TiktokStats> {
  const fila = await fetchWindsorConnector(
    'tiktok_organic',
    ['total_followers_count', 'total_likes', 'video_views'],
    'last_30d',
    apiKey,
    fetchImpl,
  )
  return {
    seguidores: campoNumerico('TikTok', 'total_followers_count', fila.total_followers_count),
    likes: campoNumerico('TikTok', 'total_likes', fila.total_likes),
    videoTopVistas: campoNumerico('TikTok', 'video_views', fila.video_views),
  }
}

export interface YoutubeStats {
  suscriptores: number
  vistasHistoricas: number
  vistas30d: number
}

// Nota (mismo bug de producción): combinar `subscriber_count`/`view_count`
// (tabla `Data - Channel`) con `views` con `date_preset` (tabla `Video`) en
// una sola consulta también rompe el auto-agregado — `views` con
// `date_preset='last_30d'` va en su propia consulta, separada.
export async function fetchYoutubeStats(apiKey: string, fetchImpl: typeof fetch = fetch): Promise<YoutubeStats> {
  const [canalFila, vistas30dFila] = await Promise.all([
    fetchWindsorConnector('youtube', ['subscriber_count', 'view_count'], null, apiKey, fetchImpl),
    fetchWindsorConnector('youtube', ['views'], 'last_30d', apiKey, fetchImpl),
  ])
  return {
    suscriptores: campoNumerico('YouTube', 'subscriber_count', canalFila.subscriber_count),
    vistasHistoricas: campoNumerico('YouTube', 'view_count', canalFila.view_count),
    vistas30d: campoNumerico('YouTube', 'views', vistas30dFila.views),
  }
}
