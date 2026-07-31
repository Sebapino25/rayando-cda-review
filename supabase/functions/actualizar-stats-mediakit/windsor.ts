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

export async function fetchInstagramStats(apiKey: string, fetchImpl: typeof fetch = fetch): Promise<InstagramStats> {
  const [seguidoresFila, vistasFila] = await Promise.all([
    fetchWindsorConnector('instagram', ['followers_count'], null, apiKey, fetchImpl),
    fetchWindsorConnector(
      'instagram',
      ['views', 'reach_1d', 'total_interactions'],
      'last_30d',
      apiKey,
      fetchImpl,
    ),
  ])
  return {
    seguidores: Number(seguidoresFila.followers_count),
    vistas30d: Number(vistasFila.views),
    alcance90d: Number(vistasFila.reach_1d),
    interacciones90d: Number(vistasFila.total_interactions),
  }
}

export interface TiktokStats {
  seguidores: number
  likes: number
  videoTopVistas: number
}

export async function fetchTiktokStats(apiKey: string, fetchImpl: typeof fetch = fetch): Promise<TiktokStats> {
  const fila = await fetchWindsorConnector(
    'tiktok_organic',
    ['total_followers_count', 'total_likes', 'video_views_count'],
    null,
    apiKey,
    fetchImpl,
  )
  return {
    seguidores: Number(fila.total_followers_count),
    likes: Number(fila.total_likes),
    videoTopVistas: Number(fila.video_views_count),
  }
}

export interface YoutubeStats {
  suscriptores: number
  vistasHistoricas: number
}

export async function fetchYoutubeStats(apiKey: string, fetchImpl: typeof fetch = fetch): Promise<YoutubeStats> {
  const fila = await fetchWindsorConnector(
    'youtube',
    ['subscriber_count', 'view_count'],
    null,
    apiKey,
    fetchImpl,
  )
  return {
    suscriptores: Number(fila.subscriber_count),
    vistasHistoricas: Number(fila.view_count),
  }
}
