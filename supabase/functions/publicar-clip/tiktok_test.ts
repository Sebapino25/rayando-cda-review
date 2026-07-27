import { assertEquals } from 'https://deno.land/std@0.224.0/assert/mod.ts'
import { publicarTiktok } from './tiktok.ts'

Deno.test('publicarTiktok arma el request PULL_FROM_URL correcto', async () => {
  let capturado: { url: string; body: string; headers: Record<string, string> } | undefined
  const fakeFetch = async (url: string | URL, init?: RequestInit) => {
    capturado = {
      url: url.toString(),
      body: init?.body as string,
      headers: init?.headers as Record<string, string>,
    }
    return new Response(JSON.stringify({ data: { publish_id: 'pub-1' }, error: { code: 'ok' } }), { status: 200 })
  }
  const publishId = await publicarTiktok(
    'https://storage.ejemplo.com/clip.mp4',
    'Copy de prueba',
    { accessToken: 'token-tt' },
    fakeFetch as typeof fetch,
  )
  assertEquals(publishId, 'pub-1')
  assertEquals(capturado?.url, 'https://open.tiktokapis.com/v2/post/publish/video/init/')
  const body = JSON.parse(capturado!.body)
  assertEquals(body.source_info.source, 'PULL_FROM_URL')
  assertEquals(body.source_info.video_url, 'https://storage.ejemplo.com/clip.mp4')
})

Deno.test('publicarTiktok lanza error si la respuesta HTTP no es 200', async () => {
  const fakeFetch = async () => new Response('error', { status: 401 })
  let lanzo = false
  try {
    await publicarTiktok('url', 'caption', { accessToken: 'token' }, fakeFetch as typeof fetch)
  } catch {
    lanzo = true
  }
  assertEquals(lanzo, true)
})

Deno.test('publicarTiktok lanza error si la API responde con error.code distinto de ok', async () => {
  const fakeFetch = async () =>
    new Response(JSON.stringify({ error: { code: 'access_token_invalid', message: 'x' } }), { status: 200 })
  let lanzo = false
  try {
    await publicarTiktok('url', 'caption', { accessToken: 'token' }, fakeFetch as typeof fetch)
  } catch {
    lanzo = true
  }
  assertEquals(lanzo, true)
})
