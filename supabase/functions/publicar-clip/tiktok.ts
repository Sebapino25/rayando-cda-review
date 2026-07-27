const TIKTOK_API_BASE = 'https://open.tiktokapis.com/v2'

export interface TikTokConfig {
  accessToken: string
}

// NOTA: sin verificar contra la API real — la app de TikTok Developers no
// estaba aprobada al momento de escribir esto (ver spec, "Expectativa
// honesta sobre TikTok"). Implementado contra la documentación pública de
// la Content Posting API v2 (init con source PULL_FROM_URL). Solo se llama
// desde index.ts si PUBLICAR_TIKTOK=true.
export async function publicarTiktok(
  videoUrl: string,
  caption: string,
  config: TikTokConfig,
  fetchImpl: typeof fetch = fetch,
): Promise<string> {
  const resp = await fetchImpl(`${TIKTOK_API_BASE}/post/publish/video/init/`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${config.accessToken}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      post_info: {
        title: caption,
        privacy_level: 'PUBLIC_TO_EVERYONE',
      },
      source_info: {
        source: 'PULL_FROM_URL',
        video_url: videoUrl,
      },
    }),
  })
  if (!resp.ok) {
    throw new Error(`TikTok: error al iniciar la publicación (${resp.status}): ${await resp.text()}`)
  }
  const data = await resp.json()
  if (data.error && data.error.code && data.error.code !== 'ok') {
    throw new Error(`TikTok: la API devolvió un error: ${JSON.stringify(data.error)}`)
  }
  return data.data?.publish_id as string
}
