const GRAPH_API_BASE = 'https://graph.instagram.com'

export interface InstagramConfig {
  igUserId: string
  accessToken: string
  containerTimeoutMs: number
}

export async function crearContenedorReel(
  videoUrl: string,
  caption: string,
  coverUrl: string | null,
  config: InstagramConfig,
  fetchImpl: typeof fetch = fetch,
): Promise<string> {
  const params = new URLSearchParams({
    media_type: 'REELS',
    video_url: videoUrl,
    caption,
    access_token: config.accessToken,
  })
  if (coverUrl) params.set('cover_url', coverUrl)

  const resp = await fetchImpl(`${GRAPH_API_BASE}/${config.igUserId}/media`, {
    method: 'POST',
    body: params,
  })
  if (!resp.ok) {
    throw new Error(`Instagram: error al crear el contenedor de media (${resp.status}): ${await resp.text()}`)
  }
  const data = await resp.json()
  return data.id as string
}

// A diferencia de una foto, un contenedor de Reel no queda FINISHED al
// toque: Instagram tiene que procesar el video primero.
export async function esperarContenedorListo(
  creationId: string,
  config: InstagramConfig,
  fetchImpl: typeof fetch = fetch,
  sleepMs: (ms: number) => Promise<void> = (ms) => new Promise((r) => setTimeout(r, ms)),
): Promise<void> {
  const inicio = Date.now()
  while (Date.now() - inicio < config.containerTimeoutMs) {
    const resp = await fetchImpl(
      `${GRAPH_API_BASE}/${creationId}?fields=status_code&access_token=${config.accessToken}`,
    )
    if (!resp.ok) {
      throw new Error(`Instagram: error consultando el contenedor (${resp.status}): ${await resp.text()}`)
    }
    const data = await resp.json()
    if (data.status_code === 'FINISHED') return
    if (data.status_code === 'ERROR') {
      throw new Error(`Instagram: el contenedor de media falló: ${JSON.stringify(data)}`)
    }
    await sleepMs(3000)
  }
  throw new Error(`Instagram: el contenedor ${creationId} no llegó a FINISHED en ${config.containerTimeoutMs}ms`)
}

export async function publicarContenedor(
  creationId: string,
  config: InstagramConfig,
  fetchImpl: typeof fetch = fetch,
): Promise<string> {
  const resp = await fetchImpl(`${GRAPH_API_BASE}/${config.igUserId}/media_publish`, {
    method: 'POST',
    body: new URLSearchParams({ creation_id: creationId, access_token: config.accessToken }),
  })
  if (!resp.ok) {
    throw new Error(`Instagram: error al publicar (${resp.status}): ${await resp.text()}`)
  }
  const data = await resp.json()
  return data.id as string
}

export async function publicarReel(
  videoUrl: string,
  caption: string,
  coverUrl: string | null,
  config: InstagramConfig,
  fetchImpl: typeof fetch = fetch,
  sleepMs?: (ms: number) => Promise<void>,
): Promise<string> {
  const creationId = await crearContenedorReel(videoUrl, caption, coverUrl, config, fetchImpl)
  await esperarContenedorListo(creationId, config, fetchImpl, sleepMs)
  return await publicarContenedor(creationId, config, fetchImpl)
}
