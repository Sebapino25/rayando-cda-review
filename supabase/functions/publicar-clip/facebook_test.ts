import { assertEquals, assertRejects } from 'https://deno.land/std@0.224.0/assert/mod.ts'
import { publicarReelFacebook } from './facebook.ts'

function fakeFetch(respuestas: Array<{ status?: number; body: unknown }>) {
  const llamadas: Array<{ url: string; init?: RequestInit }> = []
  const impl = (url: string | URL | Request, init?: RequestInit) => {
    llamadas.push({ url: String(url), init })
    const r = respuestas.shift()!
    return Promise.resolve(new Response(JSON.stringify(r.body), { status: r.status ?? 200 }))
  }
  return { impl: impl as typeof fetch, llamadas }
}

const config = { pageId: 'PAGE1', pageToken: 'TOK' }

Deno.test('publicarReelFacebook hace start, subida por file_url y finish PUBLISHED', async () => {
  const { impl, llamadas } = fakeFetch([
    { body: { video_id: 'V1', upload_url: 'x' } },
    { body: { success: true } },
    { body: { success: true } },
  ])
  const id = await publicarReelFacebook('https://storage/x.mp4', 'copy #SPA', config, impl)
  assertEquals(id, 'V1')
  assertEquals(llamadas.length, 3)
  assertEquals(llamadas[0].url, 'https://graph.facebook.com/v24.0/PAGE1/video_reels')
  assertEquals((llamadas[0].init!.body as URLSearchParams).get('upload_phase'), 'start')
  assertEquals(llamadas[1].url, 'https://rupload.facebook.com/video-upload/v24.0/V1')
  const h = llamadas[1].init!.headers as Record<string, string>
  assertEquals(h.file_url, 'https://storage/x.mp4')
  assertEquals(h.Authorization, 'OAuth TOK')
  const fin = llamadas[2].init!.body as URLSearchParams
  assertEquals(fin.get('upload_phase'), 'finish')
  assertEquals(fin.get('video_state'), 'PUBLISHED')
  assertEquals(fin.get('video_id'), 'V1')
  assertEquals(fin.get('description'), 'copy #SPA')
})

Deno.test('publicarReelFacebook falla claro si Meta rechaza el inicio', async () => {
  const { impl } = fakeFetch([{ status: 400, body: { error: { message: 'Invalid token', code: 190 } } }])
  await assertRejects(() => publicarReelFacebook('u', 'd', config, impl), Error, 'inicio de la subida (400)')
})

Deno.test('publicarReelFacebook falla si la subida no devuelve success', async () => {
  const { impl } = fakeFetch([{ body: { video_id: 'V1' } }, { body: { success: false, debug_info: 'x' } }])
  await assertRejects(() => publicarReelFacebook('u', 'd', config, impl), Error, 'subida del video no terminó bien')
})

Deno.test('publicarReelFacebook falla si finish no devuelve success', async () => {
  const { impl } = fakeFetch([{ body: { video_id: 'V1' } }, { body: { success: true } }, { body: {} }])
  await assertRejects(() => publicarReelFacebook('u', 'd', config, impl), Error, 'publicación no terminó bien')
})
