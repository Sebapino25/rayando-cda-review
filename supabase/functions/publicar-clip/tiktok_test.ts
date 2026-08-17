import { assertEquals } from 'https://deno.land/std@0.224.0/assert/mod.ts'
import { publicarTiktok } from './tiktok.ts'

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
    'Copy de prueba',
    { accessToken: 'token-tt' },
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
  assertEquals(initBody.source_info.source, 'FILE_UPLOAD')
  assertEquals(initBody.source_info.video_size, 4)
  assertEquals(initBody.source_info.chunk_size, 4)
  assertEquals(initBody.source_info.total_chunk_count, 1)

  assertEquals(subida.url, 'https://upload.ejemplo.com/subir')
  assertEquals(subida.method, 'PUT')
  assertEquals(subida.headers['Content-Range'], 'bytes 0-3/4')
})

Deno.test('publicarTiktok prefiere PUBLIC_TO_EVERYONE cuando creator_info lo ofrece (app ya auditada)', async () => {
  const { fakeFetch, llamadas } = fakeFetchExitoso(['SELF_ONLY', 'PUBLIC_TO_EVERYONE', 'MUTUAL_FOLLOW_FRIENDS'])
  await publicarTiktok('https://storage.ejemplo.com/clip.mp4', 'Copy', { accessToken: 'token-tt' }, fakeFetch)
  const init = llamadas.find((l) => l.url === 'https://open.tiktokapis.com/v2/post/publish/video/init/')!
  const initBody = JSON.parse(init.body as string)
  assertEquals(initBody.post_info.privacy_level, 'PUBLIC_TO_EVERYONE')
})

Deno.test('publicarTiktok lanza error si creator_info no trae ninguna privacy_level_options', async () => {
  const { fakeFetch } = fakeFetchExitoso([])
  let lanzo = false
  try {
    await publicarTiktok('url', 'caption', { accessToken: 'token' }, fakeFetch)
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
    await publicarTiktok('url', 'caption', { accessToken: 'token' }, fakeFetch as typeof fetch)
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
    await publicarTiktok('url', 'caption', { accessToken: 'token' }, fakeFetch as typeof fetch)
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
    await publicarTiktok('url', 'caption', { accessToken: 'token' }, fakeFetch as typeof fetch)
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
    await publicarTiktok('url', 'caption', { accessToken: 'token' }, fakeFetch as typeof fetch)
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
    await publicarTiktok('url', 'caption', { accessToken: 'token' }, fakeFetch as typeof fetch)
  } catch {
    lanzo = true
  }
  assertEquals(lanzo, true)
})
