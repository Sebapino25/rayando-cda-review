// Publica un Reel en una página de Facebook con la Reels Publishing API:
//   1. POST /{page_id}/video_reels  upload_phase=start   -> video_id
//   2. POST rupload.facebook.com/video-upload/{v}/{video_id} con header file_url
//      (Facebook descarga el mp4 desde Storage; no pasa por la función)
//   3. POST /{page_id}/video_reels  upload_phase=finish, video_state=PUBLISHED
// Facebook procesa y publica después, en segundo plano. Requiere un token de
// PÁGINA con pages_manage_posts, pages_read_engagement y pages_show_list.
import { GRAPH_FACEBOOK_BASE } from './programa.ts'

const RUPLOAD_BASE = 'https://rupload.facebook.com/video-upload/v24.0'

export interface FacebookConfig {
  pageId: string
  pageToken: string
}

async function leerJson(resp: Response, paso: string): Promise<Record<string, unknown>> {
  const texto = await resp.text()
  if (!resp.ok) {
    throw new Error(`Facebook: error en ${paso} (${resp.status}): ${texto}`)
  }
  try {
    return JSON.parse(texto)
  } catch {
    throw new Error(`Facebook: respuesta no JSON en ${paso}: ${texto}`)
  }
}

export async function publicarReelFacebook(
  videoUrl: string,
  descripcion: string,
  config: FacebookConfig,
  fetchImpl: typeof fetch = fetch,
): Promise<string> {
  const inicio = await leerJson(
    await fetchImpl(`${GRAPH_FACEBOOK_BASE}/${config.pageId}/video_reels`, {
      method: 'POST',
      body: new URLSearchParams({ upload_phase: 'start', access_token: config.pageToken }),
    }),
    'el inicio de la subida',
  )
  const videoId = inicio.video_id as string | undefined
  if (!videoId) {
    throw new Error(`Facebook: el inicio de la subida no devolvió video_id: ${JSON.stringify(inicio)}`)
  }

  const subida = await leerJson(
    await fetchImpl(`${RUPLOAD_BASE}/${videoId}`, {
      method: 'POST',
      headers: { Authorization: `OAuth ${config.pageToken}`, file_url: videoUrl },
    }),
    'la subida del video',
  )
  if (subida.success !== true) {
    throw new Error(`Facebook: la subida del video no terminó bien: ${JSON.stringify(subida)}`)
  }

  const fin = await leerJson(
    await fetchImpl(`${GRAPH_FACEBOOK_BASE}/${config.pageId}/video_reels`, {
      method: 'POST',
      body: new URLSearchParams({
        upload_phase: 'finish',
        video_id: videoId,
        video_state: 'PUBLISHED',
        description: descripcion,
        access_token: config.pageToken,
      }),
    }),
    'la publicación',
  )
  if (fin.success !== true) {
    throw new Error(`Facebook: la publicación no terminó bien: ${JSON.stringify(fin)}`)
  }
  return videoId
}
