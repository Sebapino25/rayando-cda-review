import { assertEquals, assertStringIncludes } from 'https://deno.land/std@0.224.0/assert/mod.ts'
import { refrescarTokenTiktok } from './refresh.ts'

Deno.test('refrescarTokenTiktok manda client_key/secret/refresh_token por POST y calcula vence_en', async () => {
  let urlCapturada: string | undefined
  let bodyCapturado: string | undefined
  const ahora = Date.now()
  const fakeFetch = async (url: string | URL, init?: RequestInit) => {
    urlCapturada = url.toString()
    bodyCapturado = init?.body?.toString()
    return new Response(
      JSON.stringify({ access_token: 'access-nuevo', refresh_token: 'refresh-nuevo', expires_in: 86400 }),
      { status: 200 },
    )
  }
  const resultado = await refrescarTokenTiktok('refresh-viejo', 'client-key-x', 'client-secret-x', fakeFetch as typeof fetch)
  assertEquals(urlCapturada, 'https://open.tiktokapis.com/v2/oauth/token/')
  assertStringIncludes(bodyCapturado!, 'client_key=client-key-x')
  assertStringIncludes(bodyCapturado!, 'client_secret=client-secret-x')
  assertStringIncludes(bodyCapturado!, 'grant_type=refresh_token')
  assertStringIncludes(bodyCapturado!, 'refresh_token=refresh-viejo')
  assertEquals(resultado.accessToken, 'access-nuevo')
  // El refresh_token nuevo tiene que ser el de la respuesta, no el que se mandó — TikTok lo rota en cada refresco.
  assertEquals(resultado.refreshToken, 'refresh-nuevo')
  const venceEnMs = new Date(resultado.venceEn).getTime()
  const esperado = ahora + 86400 * 1000
  assertEquals(Math.abs(venceEnMs - esperado) < 5000, true)
})

Deno.test('refrescarTokenTiktok lanza error si la respuesta no es ok', async () => {
  const fakeFetch = async () => new Response('refresh_token inválido', { status: 400 })
  let lanzo = false
  try {
    await refrescarTokenTiktok('refresh-viejo', 'k', 's', fakeFetch as typeof fetch)
  } catch (e) {
    lanzo = true
    assertStringIncludes((e as Error).message, '400')
  }
  assertEquals(lanzo, true)
})

Deno.test('refrescarTokenTiktok lanza error si la respuesta trae un campo error (200 con error lógico)', async () => {
  const fakeFetch = async () =>
    new Response(JSON.stringify({ error: 'invalid_grant', error_description: 'refresh_token expirado' }), {
      status: 200,
    })
  let lanzo = false
  try {
    await refrescarTokenTiktok('refresh-viejo', 'k', 's', fakeFetch as typeof fetch)
  } catch (e) {
    lanzo = true
    assertStringIncludes((e as Error).message, 'error')
  }
  assertEquals(lanzo, true)
})
