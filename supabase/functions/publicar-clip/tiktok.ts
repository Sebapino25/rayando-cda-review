const TIKTOK_API_BASE = 'https://open.tiktokapis.com/v2'

export interface TikTokConfig {
  accessToken: string
}

interface CreatorInfo {
  privacyLevelOptions: string[]
  commentDisabled: boolean
  duetDisabled: boolean
  stitchDisabled: boolean
}

// Confirmado en producción (25/08/2026): privacy_level_options refleja el
// estado público/privado de la CUENTA, no si esta app pasó la auditoría de
// Content Posting API de TikTok — con la cuenta pública, PUBLIC_TO_EVERYONE
// aparece en la lista aunque la app siga sin auditar. Por eso NO se puede
// confiar en creator_info para decidir si ya se puede postear público: hay
// que forzar SELF_ONLY a mano mientras la auditoría no esté aprobada. Una
// vez aprobada (TikTok Developers > Content Posting API), cambiar
// AUDITORIA_APROBADA a true acá abajo — ahí sí el código empieza a usar
// PUBLIC_TO_EVERYONE automáticamente cuando esté disponible.
const AUDITORIA_APROBADA = false

// Las Content Sharing Guidelines de TikTok exigen consultar esto antes de
// cada post para saber, entre otras cosas, si el usuario deshabilitó
// comentarios/duet/stitch.
async function consultarCreatorInfo(config: TikTokConfig, fetchImpl: typeof fetch): Promise<CreatorInfo> {
  const resp = await fetchImpl(`${TIKTOK_API_BASE}/post/publish/creator_info/query/`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${config.accessToken}`,
      'Content-Type': 'application/json; charset=UTF-8',
    },
  })
  if (!resp.ok) {
    throw new Error(`TikTok: error al consultar creator_info (${resp.status}): ${await resp.text()}`)
  }
  const data = await resp.json()
  if (data.error && data.error.code && data.error.code !== 'ok') {
    throw new Error(`TikTok: la API devolvió un error en creator_info: ${JSON.stringify(data.error)}`)
  }
  return {
    privacyLevelOptions: data.data?.privacy_level_options ?? [],
    commentDisabled: Boolean(data.data?.comment_disabled),
    duetDisabled: Boolean(data.data?.duet_disabled),
    stitchDisabled: Boolean(data.data?.stitch_disabled),
  }
}

// NOTA: usa FILE_UPLOAD (subir los bytes del video directo a TikTok) en vez
// de PULL_FROM_URL (pedirle a TikTok que vaya a buscar el video a una URL)
// porque PULL_FROM_URL exige verificar el dominio donde vive el video
// (Content Posting API > Verify domains), y el video vive en el dominio de
// Supabase Storage (*.supabase.co), que no se puede verificar como dominio
// propio. FILE_UPLOAD no tiene ese requisito. Nuestros clips (~90s,
// vertical) siempre entran en un solo chunk (límite de un chunk: 64MB).
// Solo se llama desde index.ts si PUBLICAR_TIKTOK=true.
export async function publicarTiktok(
  videoUrl: string,
  caption: string,
  config: TikTokConfig,
  fetchImpl: typeof fetch = fetch,
): Promise<string> {
  const creatorInfo = await consultarCreatorInfo(config, fetchImpl)
  // Un cliente sin auditar solo puede postear con SELF_ONLY (TikTok devuelve
  // unaudited_client_can_only_post_to_private_accounts si se manda otra
  // cosa) — ver el comentario de AUDITORIA_APROBADA más arriba sobre por qué
  // no se puede confiar en privacy_level_options para decidir esto.
  const privacyLevel = AUDITORIA_APROBADA && creatorInfo.privacyLevelOptions.includes('PUBLIC_TO_EVERYONE')
    ? 'PUBLIC_TO_EVERYONE'
    : creatorInfo.privacyLevelOptions.includes('SELF_ONLY')
      ? 'SELF_ONLY'
      : creatorInfo.privacyLevelOptions[0]
  if (!privacyLevel) {
    throw new Error('TikTok: creator_info no devolvió ningún privacy_level_options disponible')
  }

  const videoResp = await fetchImpl(videoUrl)
  if (!videoResp.ok) {
    throw new Error(`TikTok: no se pudo descargar el video desde ${videoUrl} (${videoResp.status})`)
  }
  const videoBuffer = await videoResp.arrayBuffer()
  const videoSize = videoBuffer.byteLength

  const initResp = await fetchImpl(`${TIKTOK_API_BASE}/post/publish/video/init/`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${config.accessToken}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      post_info: {
        title: caption,
        privacy_level: privacyLevel,
        disable_comment: creatorInfo.commentDisabled,
        disable_duet: creatorInfo.duetDisabled,
        disable_stitch: creatorInfo.stitchDisabled,
      },
      source_info: {
        source: 'FILE_UPLOAD',
        video_size: videoSize,
        chunk_size: videoSize,
        total_chunk_count: 1,
      },
    }),
  })
  if (!initResp.ok) {
    throw new Error(`TikTok: error al iniciar la publicación (${initResp.status}): ${await initResp.text()}`)
  }
  const initData = await initResp.json()
  if (initData.error && initData.error.code && initData.error.code !== 'ok') {
    throw new Error(`TikTok: la API devolvió un error: ${JSON.stringify(initData.error)}`)
  }
  const uploadUrl = initData.data?.upload_url as string | undefined
  const publishId = initData.data?.publish_id as string | undefined
  if (!uploadUrl || !publishId) {
    throw new Error(`TikTok: la respuesta de init no trajo upload_url/publish_id: ${JSON.stringify(initData)}`)
  }

  const uploadResp = await fetchImpl(uploadUrl, {
    method: 'PUT',
    headers: {
      'Content-Type': 'video/mp4',
      'Content-Range': `bytes 0-${videoSize - 1}/${videoSize}`,
    },
    body: videoBuffer,
  })
  if (!uploadResp.ok) {
    throw new Error(`TikTok: error al subir el video (${uploadResp.status}): ${await uploadResp.text()}`)
  }

  return publishId
}
