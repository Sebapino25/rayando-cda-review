import { assertEquals } from 'https://deno.land/std@0.224.0/assert/mod.ts'
import { obtenerCreatorInfoParaUI, publicarTiktok, TikTokPostOpciones } from './tiktok.ts'

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
    await publicarTiktok('https://storage.ejemplo.com/clip.mp4', { accessToken: 'token' }, opcionesBase(), fakeFetch)
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
    await publicarTiktok('url', { accessToken: 'token' }, opcionesBase(), fakeFetch as typeof fetch)
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
    await publicarTiktok('url', { accessToken: 'token' }, opcionesBase(), fakeFetch as typeof fetch)
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
    await publicarTiktok('url', { accessToken: 'token' }, opcionesBase(), fakeFetch as typeof fetch)
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
    await publicarTiktok('url', { accessToken: 'token' }, opcionesBase(), fakeFetch as typeof fetch)
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
    await publicarTiktok('url', { accessToken: 'token' }, opcionesBase(), fakeFetch as typeof fetch)
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
