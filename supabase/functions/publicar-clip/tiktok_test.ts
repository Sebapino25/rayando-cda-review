import { assertEquals, assertStringIncludes } from 'https://deno.land/std@0.224.0/assert/mod.ts'
import {
  obtenerCreatorInfoParaUI,
  publicarTiktok,
  consultarEstadoPublicacion,
  TikTokPostOpciones,
} from './tiktok.ts'

// max_video_post_duration_sec en fakeFetchExitoso es 600s — todos los tests
// existentes usan un clip bien por debajo para no gatillar el chequeo de
// duración (que tiene sus propios tests más abajo).
const DURACION_OK = 60

function opcionesBase(over: Partial<TikTokPostOpciones> = {}): TikTokPostOpciones {
  return {
    title: 'Copy de prueba',
    privacyLevel: 'SELF_ONLY',
    disableComment: true,
    disableDuet: true,
    disableStitch: true,
    brandContentToggle: false,
    brandOrganicToggle: false,
    auditoriaAprobada: false,
    ...over,
  }
}

function fakeFetchExitoso(privacyLevelOptions: string[] = ['SELF_ONLY']) {
  const llamadas: { url: string; method: string; body: unknown; headers: Record<string, string> }[] = []
  const fakeFetch = async (url: string | URL, init?: RequestInit) => {
    const urlStr = url.toString()
    llamadas.push({
      url: urlStr,
      method: init?.method ?? 'GET',
      body: init?.body,
      headers: (init?.headers as Record<string, string>) ?? {},
    })
    if (urlStr === 'https://open.tiktokapis.com/v2/post/publish/creator_info/query/') {
      return new Response(
        JSON.stringify({
          data: {
            privacy_level_options: privacyLevelOptions,
            comment_disabled: false,
            duet_disabled: true,
            stitch_disabled: false,
            max_video_post_duration_sec: 600,
            creator_nickname: 'Rayando el CDA',
            creator_username: 'rayandoelcda',
            creator_avatar_url: 'https://cdn.ejemplo.com/avatar.jpg',
          },
          error: { code: 'ok' },
        }),
        { status: 200 },
      )
    }
    if (urlStr === 'https://storage.ejemplo.com/clip.mp4') {
      return new Response(new Uint8Array([1, 2, 3, 4]), { status: 200 })
    }
    if (urlStr === 'https://open.tiktokapis.com/v2/post/publish/video/init/') {
      return new Response(
        JSON.stringify({
          data: { publish_id: 'pub-1', upload_url: 'https://upload.ejemplo.com/subir' },
          error: { code: 'ok' },
        }),
        { status: 200 },
      )
    }
    if (urlStr === 'https://upload.ejemplo.com/subir') {
      return new Response(null, { status: 201 })
    }
    throw new Error(`fakeFetch: URL inesperada ${urlStr}`)
  }
  return { fakeFetch: fakeFetch as typeof fetch, llamadas }
}

Deno.test('publicarTiktok consulta creator_info, descarga el video, inicia con FILE_UPLOAD y sube los bytes', async () => {
  const { fakeFetch, llamadas } = fakeFetchExitoso(['SELF_ONLY'])
  const publishId = await publicarTiktok(
    'https://storage.ejemplo.com/clip.mp4',
    { accessToken: 'token-tt' },
    opcionesBase(),
    DURACION_OK,
    fakeFetch,
  )
  assertEquals(publishId, 'pub-1')
  assertEquals(llamadas.length, 4)

  const [creatorInfo, descarga, init, subida] = llamadas
  assertEquals(creatorInfo.url, 'https://open.tiktokapis.com/v2/post/publish/creator_info/query/')

  assertEquals(descarga.url, 'https://storage.ejemplo.com/clip.mp4')

  assertEquals(init.url, 'https://open.tiktokapis.com/v2/post/publish/video/init/')
  const initBody = JSON.parse(init.body as string)
  assertEquals(initBody.post_info.privacy_level, 'SELF_ONLY')
  assertEquals(initBody.post_info.disable_duet, true)
  assertEquals(initBody.post_info.brand_content_toggle, false)
  assertEquals(initBody.post_info.brand_organic_toggle, false)
  assertEquals(initBody.source_info.source, 'FILE_UPLOAD')
  assertEquals(initBody.source_info.video_size, 4)
  assertEquals(initBody.source_info.chunk_size, 4)
  assertEquals(initBody.source_info.total_chunk_count, 1)

  assertEquals(subida.url, 'https://upload.ejemplo.com/subir')
  assertEquals(subida.method, 'PUT')
  assertEquals(subida.headers['Content-Range'], 'bytes 0-3/4')
})

Deno.test('publicarTiktok usa el privacy_level que se le pasa (no lo calcula solo)', async () => {
  const { fakeFetch, llamadas } = fakeFetchExitoso(['SELF_ONLY', 'PUBLIC_TO_EVERYONE', 'MUTUAL_FOLLOW_FRIENDS'])
  await publicarTiktok(
    'https://storage.ejemplo.com/clip.mp4',
    { accessToken: 'token-tt' },
    opcionesBase({ privacyLevel: 'PUBLIC_TO_EVERYONE', auditoriaAprobada: true }),
    DURACION_OK,
    fakeFetch,
  )
  const init = llamadas.find((l) => l.url === 'https://open.tiktokapis.com/v2/post/publish/video/init/')!
  const initBody = JSON.parse(init.body as string)
  assertEquals(initBody.post_info.privacy_level, 'PUBLIC_TO_EVERYONE')
})

Deno.test('publicarTiktok lanza error si el privacy_level pedido no está entre las opciones de creator_info', async () => {
  const { fakeFetch } = fakeFetchExitoso(['SELF_ONLY'])
  let lanzo = false
  try {
    await publicarTiktok(
      'https://storage.ejemplo.com/clip.mp4',
      { accessToken: 'token-tt' },
      opcionesBase({ privacyLevel: 'PUBLIC_TO_EVERYONE' }),
      DURACION_OK,
      fakeFetch,
    )
  } catch {
    lanzo = true
  }
  assertEquals(lanzo, true)
})

Deno.test('publicarTiktok lanza error si se pide PUBLIC_TO_EVERYONE sin auditoría aprobada', async () => {
  const { fakeFetch } = fakeFetchExitoso(['SELF_ONLY', 'PUBLIC_TO_EVERYONE'])
  let lanzo = false
  try {
    await publicarTiktok(
      'https://storage.ejemplo.com/clip.mp4',
      { accessToken: 'token-tt' },
      opcionesBase({ privacyLevel: 'PUBLIC_TO_EVERYONE', auditoriaAprobada: false }),
      DURACION_OK,
      fakeFetch,
    )
  } catch {
    lanzo = true
  }
  assertEquals(lanzo, true)
})

Deno.test('publicarTiktok fuerza disable_duet=true si creator_info lo restringe aunque el cliente mande false', async () => {
  const { fakeFetch, llamadas } = fakeFetchExitoso(['SELF_ONLY'])
  await publicarTiktok(
    'https://storage.ejemplo.com/clip.mp4',
    { accessToken: 'token-tt' },
    opcionesBase({ disableDuet: false }),
    DURACION_OK,
    fakeFetch,
  )
  const init = llamadas.find((l) => l.url === 'https://open.tiktokapis.com/v2/post/publish/video/init/')!
  const initBody = JSON.parse(init.body as string)
  assertEquals(initBody.post_info.disable_duet, true)
})

Deno.test('publicarTiktok manda los brand toggles al init', async () => {
  const { fakeFetch, llamadas } = fakeFetchExitoso(['SELF_ONLY', 'FOLLOWER_OF_CREATOR'])
  await publicarTiktok(
    'https://storage.ejemplo.com/clip.mp4',
    { accessToken: 'token-tt' },
    opcionesBase({
      privacyLevel: 'FOLLOWER_OF_CREATOR',
      brandContentToggle: true,
      brandOrganicToggle: true,
    }),
    DURACION_OK,
    fakeFetch,
  )
  const init = llamadas.find((l) => l.url === 'https://open.tiktokapis.com/v2/post/publish/video/init/')!
  const initBody = JSON.parse(init.body as string)
  assertEquals(initBody.post_info.brand_content_toggle, true)
  assertEquals(initBody.post_info.brand_organic_toggle, true)
})

Deno.test('publicarTiktok lanza error si el contenido de marca se quiere publicar como privado', async () => {
  const { fakeFetch } = fakeFetchExitoso(['SELF_ONLY'])
  let lanzo = false
  try {
    await publicarTiktok(
      'https://storage.ejemplo.com/clip.mp4',
      { accessToken: 'token-tt' },
      opcionesBase({ privacyLevel: 'SELF_ONLY', brandContentToggle: true }),
      DURACION_OK,
      fakeFetch,
    )
  } catch {
    lanzo = true
  }
  assertEquals(lanzo, true)
})

Deno.test('publicarTiktok lanza error si creator_info no trae ninguna privacy_level_options', async () => {
  const { fakeFetch } = fakeFetchExitoso([])
  let lanzo = false
  try {
    await publicarTiktok(
      'https://storage.ejemplo.com/clip.mp4',
      { accessToken: 'token' },
      opcionesBase(),
      DURACION_OK,
      fakeFetch,
    )
  } catch {
    lanzo = true
  }
  assertEquals(lanzo, true)
})

Deno.test('publicarTiktok lanza error si no se puede descargar el video', async () => {
  let llamada = 0
  const fakeFetch = async (url: string | URL) => {
    llamada++
    if (llamada === 1) {
      return new Response(
        JSON.stringify({ data: { privacy_level_options: ['SELF_ONLY'] }, error: { code: 'ok' } }),
        { status: 200 },
      )
    }
    return new Response('not found', { status: 404 })
  }
  let lanzo = false
  try {
    await publicarTiktok('url', { accessToken: 'token' }, opcionesBase(), DURACION_OK, fakeFetch as typeof fetch)
  } catch {
    lanzo = true
  }
  assertEquals(lanzo, true)
})

Deno.test('publicarTiktok lanza error si el init no es 200', async () => {
  let llamada = 0
  const fakeFetch = async () => {
    llamada++
    if (llamada === 1) {
      return new Response(
        JSON.stringify({ data: { privacy_level_options: ['SELF_ONLY'] }, error: { code: 'ok' } }),
        { status: 200 },
      )
    }
    if (llamada === 2) return new Response(new Uint8Array([1]), { status: 200 })
    return new Response('error', { status: 401 })
  }
  let lanzo = false
  try {
    await publicarTiktok('url', { accessToken: 'token' }, opcionesBase(), DURACION_OK, fakeFetch as typeof fetch)
  } catch {
    lanzo = true
  }
  assertEquals(lanzo, true)
})

Deno.test('publicarTiktok lanza error si el init responde con error.code distinto de ok', async () => {
  let llamada = 0
  const fakeFetch = async () => {
    llamada++
    if (llamada === 1) {
      return new Response(
        JSON.stringify({ data: { privacy_level_options: ['SELF_ONLY'] }, error: { code: 'ok' } }),
        { status: 200 },
      )
    }
    if (llamada === 2) return new Response(new Uint8Array([1]), { status: 200 })
    return new Response(JSON.stringify({ error: { code: 'access_token_invalid', message: 'x' } }), { status: 200 })
  }
  let lanzo = false
  try {
    await publicarTiktok('url', { accessToken: 'token' }, opcionesBase(), DURACION_OK, fakeFetch as typeof fetch)
  } catch {
    lanzo = true
  }
  assertEquals(lanzo, true)
})

Deno.test('publicarTiktok lanza error si falta upload_url o publish_id en la respuesta del init', async () => {
  let llamada = 0
  const fakeFetch = async () => {
    llamada++
    if (llamada === 1) {
      return new Response(
        JSON.stringify({ data: { privacy_level_options: ['SELF_ONLY'] }, error: { code: 'ok' } }),
        { status: 200 },
      )
    }
    if (llamada === 2) return new Response(new Uint8Array([1]), { status: 200 })
    return new Response(JSON.stringify({ data: {}, error: { code: 'ok' } }), { status: 200 })
  }
  let lanzo = false
  try {
    await publicarTiktok('url', { accessToken: 'token' }, opcionesBase(), DURACION_OK, fakeFetch as typeof fetch)
  } catch {
    lanzo = true
  }
  assertEquals(lanzo, true)
})

Deno.test('publicarTiktok lanza error si la subida del video no es 2xx', async () => {
  let llamada = 0
  const fakeFetch = async () => {
    llamada++
    if (llamada === 1) {
      return new Response(
        JSON.stringify({ data: { privacy_level_options: ['SELF_ONLY'] }, error: { code: 'ok' } }),
        { status: 200 },
      )
    }
    if (llamada === 2) return new Response(new Uint8Array([1]), { status: 200 })
    if (llamada === 3) {
      return new Response(
        JSON.stringify({ data: { publish_id: 'pub-1', upload_url: 'https://upload.ejemplo.com/subir' }, error: { code: 'ok' } }),
        { status: 200 },
      )
    }
    return new Response('error', { status: 500 })
  }
  let lanzo = false
  try {
    await publicarTiktok('url', { accessToken: 'token' }, opcionesBase(), DURACION_OK, fakeFetch as typeof fetch)
  } catch {
    lanzo = true
  }
  assertEquals(lanzo, true)
})

Deno.test('publicarTiktok lanza error si el clip dura más que max_video_post_duration_sec', async () => {
  const { fakeFetch, llamadas } = fakeFetchExitoso(['SELF_ONLY']) // max_video_post_duration_sec: 600
  let mensaje = ''
  try {
    await publicarTiktok(
      'https://storage.ejemplo.com/clip.mp4',
      { accessToken: 'token-tt' },
      opcionesBase(),
      601,
      fakeFetch,
    )
  } catch (e) {
    mensaje = e instanceof Error ? e.message : String(e)
  }
  assertStringIncludes(mensaje, '601')
  assertStringIncludes(mensaje, '600')
  // No debe haber llegado a descargar el video ni a llamar a init/upload.
  assertEquals(llamadas.length, 1)
})

Deno.test('publicarTiktok no lanza por duración si el clip entra justo en el máximo', async () => {
  const { fakeFetch } = fakeFetchExitoso(['SELF_ONLY']) // max_video_post_duration_sec: 600
  const publishId = await publicarTiktok(
    'https://storage.ejemplo.com/clip.mp4',
    { accessToken: 'token-tt' },
    opcionesBase(),
    600,
    fakeFetch,
  )
  assertEquals(publishId, 'pub-1')
})

Deno.test('publicarTiktok da un mensaje claro de "reintentá más tarde" si TikTok dice que se alcanzó el límite de posteo', async () => {
  let llamada = 0
  const fakeFetch = async () => {
    llamada++
    if (llamada === 1) {
      return new Response(
        JSON.stringify({ data: { privacy_level_options: ['SELF_ONLY'], max_video_post_duration_sec: 600 }, error: { code: 'ok' } }),
        { status: 200 },
      )
    }
    if (llamada === 2) return new Response(new Uint8Array([1]), { status: 200 })
    return new Response(
      JSON.stringify({ error: { code: 'spam_risk_too_many_posts', message: 'x' } }),
      { status: 200 },
    )
  }
  let mensaje = ''
  try {
    await publicarTiktok('url', { accessToken: 'token' }, opcionesBase(), DURACION_OK, fakeFetch as typeof fetch)
  } catch (e) {
    mensaje = e instanceof Error ? e.message : String(e)
  }
  assertStringIncludes(mensaje, 'reintentá más tarde')
})

Deno.test('consultarEstadoPublicacion devuelve el status y fail_reason que manda TikTok', async () => {
  const fakeFetch = async (url: string | URL, init?: RequestInit) => {
    assertEquals(url.toString(), 'https://open.tiktokapis.com/v2/post/publish/status/fetch/')
    assertEquals(JSON.parse(init!.body as string), { publish_id: 'pub-1' })
    return new Response(
      JSON.stringify({ data: { status: 'PUBLISH_COMPLETE' }, error: { code: 'ok' } }),
      { status: 200 },
    )
  }
  const estado = await consultarEstadoPublicacion('pub-1', { accessToken: 'token' }, fakeFetch as typeof fetch)
  assertEquals(estado.status, 'PUBLISH_COMPLETE')
  assertEquals(estado.failReason, undefined)
})

Deno.test('consultarEstadoPublicacion trae el fail_reason cuando el status es FAILED', async () => {
  const fakeFetch = async () =>
    new Response(
      JSON.stringify({ data: { status: 'FAILED', fail_reason: 'video_pull_failed' }, error: { code: 'ok' } }),
      { status: 200 },
    )
  const estado = await consultarEstadoPublicacion('pub-1', { accessToken: 'token' }, fakeFetch as typeof fetch)
  assertEquals(estado.status, 'FAILED')
  assertEquals(estado.failReason, 'video_pull_failed')
})

Deno.test('consultarEstadoPublicacion lanza error si la respuesta no es 200', async () => {
  const fakeFetch = async () => new Response('error', { status: 500 })
  let lanzo = false
  try {
    await consultarEstadoPublicacion('pub-1', { accessToken: 'token' }, fakeFetch as typeof fetch)
  } catch {
    lanzo = true
  }
  assertEquals(lanzo, true)
})

Deno.test('obtenerCreatorInfoParaUI saca PUBLIC_TO_EVERYONE si la auditoría no está aprobada', async () => {
  const { fakeFetch } = fakeFetchExitoso(['PUBLIC_TO_EVERYONE', 'MUTUAL_FOLLOW_FRIENDS', 'SELF_ONLY'])
  const info = await obtenerCreatorInfoParaUI({ accessToken: 'token' }, false, fakeFetch)
  assertEquals(info.privacyLevelOptions, ['MUTUAL_FOLLOW_FRIENDS', 'SELF_ONLY'])
  assertEquals(info.auditoriaAprobada, false)
  assertEquals(info.creatorNickname, 'Rayando el CDA')
  assertEquals(info.maxVideoPostDurationSec, 600)
})

Deno.test('obtenerCreatorInfoParaUI deja PUBLIC_TO_EVERYONE si la auditoría está aprobada', async () => {
  const { fakeFetch } = fakeFetchExitoso(['PUBLIC_TO_EVERYONE', 'SELF_ONLY'])
  const info = await obtenerCreatorInfoParaUI({ accessToken: 'token' }, true, fakeFetch)
  assertEquals(info.privacyLevelOptions, ['PUBLIC_TO_EVERYONE', 'SELF_ONLY'])
  assertEquals(info.auditoriaAprobada, true)
})
