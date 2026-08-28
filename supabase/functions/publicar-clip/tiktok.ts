const TIKTOK_API_BASE = 'https://open.tiktokapis.com/v2'

export interface TikTokConfig {
  accessToken: string
}

export interface CreatorInfo {
  privacyLevelOptions: string[]
  commentDisabled: boolean
  duetDisabled: boolean
  stitchDisabled: boolean
  maxVideoPostDurationSec: number
  creatorNickname: string
  creatorUsername: string
  creatorAvatarUrl: string
}

// Opciones de publicación que elige el usuario en la pantalla de TikTok de la
// app (ver app/src/components/TikTokPublishPanel.jsx). Las Content Sharing
// Guidelines de TikTok exigen que estos valores los elija la persona a mano
// antes de publicar — no se pueden inferir ni poner por defecto.
export interface TikTokPostOpciones {
  title: string
  privacyLevel: string
  disableComment: boolean
  disableDuet: boolean
  disableStitch: boolean
  brandContentToggle: boolean
  brandOrganicToggle: boolean
  // Espejo del secret TIKTOK_AUDITORIA_APROBADA. Mientras sea false, TikTok
  // rechaza (403) cualquier post que no sea privado si la cuenta está pública,
  // así que no se permite PUBLIC_TO_EVERYONE.
  auditoriaAprobada: boolean
}

// Las Content Sharing Guidelines de TikTok exigen consultar esto antes de
// cada post: da las opciones de privacidad disponibles (según el estado
// público/privado de la CUENTA), si el usuario deshabilitó
// comentarios/duet/stitch, la duración máxima de video, y los datos de la
// cuenta para mostrar en la UI.
export async function consultarCreatorInfo(
  config: TikTokConfig,
  fetchImpl: typeof fetch = fetch,
): Promise<CreatorInfo> {
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
  const d = data.data ?? {}
  return {
    privacyLevelOptions: d.privacy_level_options ?? [],
    commentDisabled: Boolean(d.comment_disabled),
    duetDisabled: Boolean(d.duet_disabled),
    stitchDisabled: Boolean(d.stitch_disabled),
    maxVideoPostDurationSec: Number(d.max_video_post_duration_sec ?? 0),
    creatorNickname: d.creator_nickname ?? '',
    creatorUsername: d.creator_username ?? '',
    creatorAvatarUrl: d.creator_avatar_url ?? '',
  }
}

// Confirmado en producción (25/08/2026): privacy_level_options refleja el
// estado público/privado de la CUENTA, no si esta app pasó la auditoría de
// Content Posting API de TikTok — con la cuenta pública, PUBLIC_TO_EVERYONE
// aparece en la lista aunque la app siga sin auditar, pero postear con él da
// 403 (unaudited_client_can_only_post_to_private_accounts). Por eso, mientras
// la auditoría no esté aprobada, se saca PUBLIC_TO_EVERYONE de las opciones
// que ve el usuario. El gate real vive en el secret TIKTOK_AUDITORIA_APROBADA
// (lo lee index.ts), no acá.
export interface CreatorInfoParaUI extends CreatorInfo {
  auditoriaAprobada: boolean
}

export async function obtenerCreatorInfoParaUI(
  config: TikTokConfig,
  auditoriaAprobada: boolean,
  fetchImpl: typeof fetch = fetch,
): Promise<CreatorInfoParaUI> {
  const info = await consultarCreatorInfo(config, fetchImpl)
  const privacyLevelOptions = auditoriaAprobada
    ? info.privacyLevelOptions
    : info.privacyLevelOptions.filter((o) => o !== 'PUBLIC_TO_EVERYONE')
  return { ...info, privacyLevelOptions, auditoriaAprobada }
}

// NOTA: usa FILE_UPLOAD (subir los bytes del video directo a TikTok) en vez
// de PULL_FROM_URL (pedirle a TikTok que vaya a buscar el video a una URL)
// porque PULL_FROM_URL exige verificar el dominio donde vive el video
// (Content Posting API > Verify domains), y el video vive en el dominio de
// Supabase Storage (*.supabase.co), que no se puede verificar como dominio
// propio. FILE_UPLOAD no tiene ese requisito. Nuestros clips (~90s,
// vertical) siempre entran en un solo chunk (límite de un chunk: 64MB).
// Solo se llama desde index.ts si PUBLICAR_TIKTOK=true y el usuario configuró
// la publicación a TikTok en la pantalla de la app.
export async function publicarTiktok(
  videoUrl: string,
  config: TikTokConfig,
  opciones: TikTokPostOpciones,
  fetchImpl: typeof fetch = fetch,
): Promise<string> {
  // Se re-consulta creator_info server-side para validar lo que mandó el
  // cliente: la elección de privacidad tiene que seguir siendo válida, y si
  // la cuenta deshabilitó comentarios/duet/stitch hay que respetarlo aunque
  // el cliente diga otra cosa (las guidelines de TikTok lo exigen).
  const creatorInfo = await consultarCreatorInfo(config, fetchImpl)

  if (!creatorInfo.privacyLevelOptions.includes(opciones.privacyLevel)) {
    throw new Error(
      `TikTok: privacy_level "${opciones.privacyLevel}" no está entre las opciones disponibles (${creatorInfo.privacyLevelOptions.join(', ') || 'ninguna'})`,
    )
  }
  if (!opciones.auditoriaAprobada && opciones.privacyLevel === 'PUBLIC_TO_EVERYONE') {
    throw new Error(
      'TikTok: no se puede publicar como PUBLIC_TO_EVERYONE hasta que se apruebe la auditoría de Direct Post (TIKTOK_AUDITORIA_APROBADA).',
    )
  }
  // El contenido de marca no puede ser privado (regla de TikTok).
  if (opciones.brandContentToggle && opciones.privacyLevel === 'SELF_ONLY') {
    throw new Error('TikTok: el contenido de marca no puede publicarse como privado (SELF_ONLY).')
  }

  const disableComment = opciones.disableComment || creatorInfo.commentDisabled
  const disableDuet = opciones.disableDuet || creatorInfo.duetDisabled
  const disableStitch = opciones.disableStitch || creatorInfo.stitchDisabled

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
        title: opciones.title,
        privacy_level: opciones.privacyLevel,
        disable_comment: disableComment,
        disable_duet: disableDuet,
        disable_stitch: disableStitch,
        brand_content_toggle: opciones.brandContentToggle,
        brand_organic_toggle: opciones.brandOrganicToggle,
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
