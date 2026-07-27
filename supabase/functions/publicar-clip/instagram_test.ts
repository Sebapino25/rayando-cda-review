import { assertEquals, assertStringIncludes } from 'https://deno.land/std@0.224.0/assert/mod.ts'
import { publicarReel } from './instagram.ts'

const CONFIG_TEST = { igUserId: 'ig-user-1', accessToken: 'token-ig', containerTimeoutMs: 5000 }
const sinEsperar = async (_ms: number) => {}

Deno.test('publicarReel crea contenedor, espera FINISHED y publica', async () => {
  const llamadas: string[] = []
  let headersEstado: HeadersInit | undefined
  const fakeFetch = async (url: string | URL, init?: RequestInit) => {
    const u = url.toString()
    llamadas.push(u)
    if (u.includes('/media_publish')) {
      return new Response(JSON.stringify({ id: 'media-final-1' }), { status: 200 })
    }
    if (u.includes('/ig-user-1/media')) {
      return new Response(JSON.stringify({ id: 'creation-1' }), { status: 200 })
    }
    if (u.includes('status_code')) {
      headersEstado = init?.headers
      return new Response(JSON.stringify({ status_code: 'FINISHED' }), { status: 200 })
    }
    throw new Error(`URL no esperada en el test: ${u}`)
  }
  const mediaId = await publicarReel(
    'https://storage.ejemplo.com/clip.mp4',
    'Copy de prueba',
    'https://storage.ejemplo.com/portada.jpg',
    CONFIG_TEST,
    fakeFetch as typeof fetch,
    sinEsperar,
  )
  assertEquals(mediaId, 'media-final-1')
  assertEquals(llamadas.some((u) => u.includes('creation-1')), true)
  // El token no debe viajar en la URL del polling de estado (se filtraría en
  // logs/errores de red) — tiene que ir en el header Authorization.
  const urlEstado = llamadas.find((u) => u.includes('status_code'))
  assertEquals(urlEstado?.includes('access_token'), false)
  assertEquals((headersEstado as Record<string, string> | undefined)?.Authorization, 'Bearer token-ig')
})

Deno.test('publicarReel reintenta mientras el status_code es IN_PROGRESS y corta en FINISHED', async () => {
  let consultas = 0
  const fakeFetch = async (url: string | URL) => {
    const u = url.toString()
    if (u.includes('/media_publish')) return new Response(JSON.stringify({ id: 'm1' }), { status: 200 })
    if (u.includes('/ig-user-1/media')) return new Response(JSON.stringify({ id: 'c1' }), { status: 200 })
    if (u.includes('status_code')) {
      consultas++
      const status = consultas < 3 ? 'IN_PROGRESS' : 'FINISHED'
      return new Response(JSON.stringify({ status_code: status }), { status: 200 })
    }
    throw new Error(`URL no esperada: ${u}`)
  }
  await publicarReel('url', 'caption', null, CONFIG_TEST, fakeFetch as typeof fetch, sinEsperar)
  assertEquals(consultas, 3)
})

Deno.test('publicarReel lanza error si el contenedor devuelve ERROR', async () => {
  const fakeFetch = async (url: string | URL) => {
    const u = url.toString()
    if (u.includes('/ig-user-1/media')) return new Response(JSON.stringify({ id: 'c1' }), { status: 200 })
    if (u.includes('status_code')) return new Response(JSON.stringify({ status_code: 'ERROR' }), { status: 200 })
    throw new Error(`URL no esperada: ${u}`)
  }
  let lanzo = false
  try {
    await publicarReel('url', 'caption', null, CONFIG_TEST, fakeFetch as typeof fetch, sinEsperar)
  } catch (e) {
    lanzo = true
    assertStringIncludes((e as Error).message, 'ERROR')
  }
  assertEquals(lanzo, true)
})

Deno.test('publicarReel manda cover_url solo si viene definida', async () => {
  let bodyCapturado: string | undefined
  const fakeFetch = async (url: string | URL, init?: RequestInit) => {
    const u = url.toString()
    if (u.includes('/ig-user-1/media')) {
      bodyCapturado = init?.body?.toString()
      return new Response(JSON.stringify({ id: 'c1' }), { status: 200 })
    }
    if (u.includes('status_code')) return new Response(JSON.stringify({ status_code: 'FINISHED' }), { status: 200 })
    if (u.includes('/media_publish')) return new Response(JSON.stringify({ id: 'm1' }), { status: 200 })
    throw new Error(`URL no esperada: ${u}`)
  }
  await publicarReel('url-video', 'caption', null, CONFIG_TEST, fakeFetch as typeof fetch, sinEsperar)
  assertEquals(bodyCapturado?.includes('cover_url'), false)
})
