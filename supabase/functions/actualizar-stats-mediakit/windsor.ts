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
  return fila
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
    seguidores: Number(seguidoresFila.followers_count),
    vistas30d: Number(vistasFila.views),
    alcance90d: Number(alcanceFila.reach_1d),
    interacciones90d: Number(interaccionesFila.total_interactions),
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
    seguidores: Number(fila.total_followers_count),
    likes: Number(fila.total_likes),
    videoTopVistas: Number(fila.video_views),
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
    suscriptores: Number(canalFila.subscriber_count),
    vistasHistoricas: Number(canalFila.view_count),
    vistas30d: Number(vistas30dFila.views),
  }
}
