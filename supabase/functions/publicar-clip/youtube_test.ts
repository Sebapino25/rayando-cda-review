import { assertEquals, assertStringIncludes } from 'https://deno.land/std@0.224.0/assert/mod.ts'
import { obtenerAccessTokenYoutube, publicarYoutube } from './youtube.ts'

Deno.test('obtenerAccessTokenYoutube arma el POST de refresh y devuelve el access_token', async () => {
  let capturado: { url: string; body: string } | undefined
  const fakeFetch = async (url: string | URL, init?: RequestInit) => {
    capturado = { url: url.toString(), body: init?.body as string }
    return new Response(JSON.stringify({ access_token: 'token-123' }), { status: 200 })
  }
  const token = await obtenerAccessTokenYoutube(
    { clientId: 'id-test', clientSecret: 'secret-test', refreshToken: 'refresh_test' },
    fakeFetch as typeof fetch,
  )
  assertEquals(token, 'token-123')
  assertEquals(capturado?.url, 'https://oauth2.googleapis.com/token')
  assertStringIncludes(capturado!.body, 'grant_type=refresh_token')
  assertStringIncludes(capturado!.body, 'refresh_test')
})

Deno.test('obtenerAccessTokenYoutube lanza error si el refresh falla', async () => {
  const fakeFetch = async () => new Response('token revocado', { status: 400 })
  let lanzo = false
  try {
    await obtenerAccessTokenYoutube(
      { clientId: 'id', clientSecret: 'secret', refreshToken: 'refresh' },
      fakeFetch as typeof fetch,
    )
  } catch {
    lanzo = true
  }
  assertEquals(lanzo, true)
})

Deno.test('publicarYoutube lee el video, pisa título/descripción/privacyStatus y usa PUT', async () => {
  const llamadas: { url: string; method?: string; body?: string }[] = []
  const fakeFetch = async (url: string | URL, init?: RequestInit) => {
    llamadas.push({ url: url.toString(), method: init?.method, body: init?.body as string })
    if (llamadas.length === 1) {
      return new Response(
        JSON.stringify({
          items: [{ snippet: { title: 'viejo', categoryId: '17' }, status: { privacyStatus: 'unlisted' } }],
        }),
        { status: 200 },
      )
    }
    return new Response('{}', { status: 200 })
  }
  await publicarYoutube('vid1', 'Nuevo título', 'Nueva descripción', 'token-abc', fakeFetch as typeof fetch)

  assertEquals(llamadas.length, 2)
  assertEquals(llamadas[1].method, 'PUT')
  const body = JSON.parse(llamadas[1].body!)
  assertEquals(body.snippet.title, 'Nuevo título')
  assertEquals(body.snippet.description, 'Nueva descripción')
  assertEquals(body.snippet.categoryId, '17') // se preserva lo que no se pisa
  assertEquals(body.status.privacyStatus, 'public')
})

Deno.test('publicarYoutube lanza error si el video no existe', async () => {
  const fakeFetch = async () => new Response(JSON.stringify({ items: [] }), { status: 200 })
  let lanzo = false
  try {
    await publicarYoutube('vid-inexistente', 't', 'd', 'token', fakeFetch as typeof fetch)
  } catch {
    lanzo = true
  }
  assertEquals(lanzo, true)
})
