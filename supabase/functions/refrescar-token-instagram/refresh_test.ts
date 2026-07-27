import { assertEquals, assertStringIncludes } from 'https://deno.land/std@0.224.0/assert/mod.ts'
import { refrescarTokenInstagram } from './refresh.ts'

Deno.test('refrescarTokenInstagram arma la URL correcta y calcula vence_en', async () => {
  let urlCapturada: string | undefined
  const ahora = Date.now()
  const fakeFetch = async (url: string | URL) => {
    urlCapturada = url.toString()
    return new Response(JSON.stringify({ access_token: 'token-nuevo', expires_in: 5184000 }), { status: 200 })
  }
  const resultado = await refrescarTokenInstagram('token-viejo', fakeFetch as typeof fetch)
  assertStringIncludes(urlCapturada!, 'grant_type=ig_refresh_token')
  assertStringIncludes(urlCapturada!, 'access_token=token-viejo')
  assertEquals(resultado.accessToken, 'token-nuevo')
  const venceEnMs = new Date(resultado.venceEn).getTime()
  // Debe vencer ~5184000 segundos (60 días) después de ahora, con margen de 5s por el tiempo de test.
  const esperado = ahora + 5184000 * 1000
  assertEquals(Math.abs(venceEnMs - esperado) < 5000, true)
})

Deno.test('refrescarTokenInstagram lanza error si el refresh falla', async () => {
  const fakeFetch = async () => new Response('token inválido', { status: 400 })
  let lanzo = false
  try {
    await refrescarTokenInstagram('token-viejo', fakeFetch as typeof fetch)
  } catch {
    lanzo = true
  }
  assertEquals(lanzo, true)
})
