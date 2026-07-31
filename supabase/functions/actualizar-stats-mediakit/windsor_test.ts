import { assertEquals, assertRejects, assertStringIncludes } from 'https://deno.land/std@0.224.0/assert/mod.ts'
import {
  fetchWindsorConnector,
  fetchInstagramStats,
  fetchTiktokStats,
  fetchYoutubeStats,
  WindsorError,
} from './windsor.ts'

function fakeFetchOk(body: unknown) {
  return async (url: string | URL) => {
    return new Response(JSON.stringify(body), { status: 200 })
  }
}

Deno.test('fetchWindsorConnector arma la URL con connector, fields y api_key', async () => {
  let urlCapturada: string | undefined
  const fakeFetch = async (url: string | URL) => {
    urlCapturada = url.toString()
    return new Response(JSON.stringify({ data: [{ followers_count: 100 }] }), { status: 200 })
  }
  await fetchWindsorConnector('instagram', ['followers_count'], null, 'mi-api-key', fakeFetch as typeof fetch)
  assertStringIncludes(urlCapturada!, 'connectors.windsor.ai/instagram')
  assertStringIncludes(urlCapturada!, 'api_key=mi-api-key')
  assertStringIncludes(urlCapturada!, 'fields=followers_count')
})

Deno.test('fetchWindsorConnector agrega date_preset cuando se pasa', async () => {
  let urlCapturada: string | undefined
  const fakeFetch = async (url: string | URL) => {
    urlCapturada = url.toString()
    return new Response(JSON.stringify({ data: [{ views: 1 }] }), { status: 200 })
  }
  await fetchWindsorConnector('instagram', ['views'], 'last_30d', 'k', fakeFetch as typeof fetch)
  assertStringIncludes(urlCapturada!, 'date_preset=last_30d')
})

Deno.test('fetchWindsorConnector lanza WindsorError si la respuesta no es 200', async () => {
  const fakeFetch = async () => new Response('unauthorized', { status: 401 })
  await assertRejects(
    () => fetchWindsorConnector('instagram', ['followers_count'], null, 'k', fakeFetch as typeof fetch),
    WindsorError,
  )
})

Deno.test('fetchWindsorConnector lanza WindsorError si data viene vacío', async () => {
  const fakeFetch = fakeFetchOk({ data: [] })
  await assertRejects(
    () => fetchWindsorConnector('instagram', ['followers_count'], null, 'k', fakeFetch as typeof fetch),
    WindsorError,
  )
})

// Cada función hace ahora varias llamadas separadas a Windsor.ai (una por
// "tabla" interna, para no romper el auto-agregado — ver windsor.ts). Este
// fake inspecciona la URL de cada llamada y devuelve la fila mockeada que
// corresponda, para poder seguir verificando el mapeo de campos end to end.
function fakeFetchPorUrl(respuestas: Array<{ contiene: string; data: Record<string, unknown> }>) {
  return async (url: string | URL) => {
    const urlStr = url.toString()
    const match = respuestas.find((r) => urlStr.includes(r.contiene))
    if (!match) {
      throw new Error(`fakeFetchPorUrl: no hay mock para la URL ${urlStr}`)
    }
    return new Response(JSON.stringify({ data: [match.data] }), { status: 200 })
  }
}

Deno.test('fetchInstagramStats mapea los campos correctos (4 llamadas separadas)', async () => {
  const fakeFetch = fakeFetchPorUrl([
    { contiene: 'fields=followers_count', data: { followers_count: 13677 } },
    { contiene: 'fields=views', data: { views: 3200000 } },
    { contiene: 'fields=total_interactions', data: { total_interactions: 590000 } },
    { contiene: 'fields=reach_1d', data: { reach_1d: 560000 } },
  ])
  const stats = await fetchInstagramStats('k', fakeFetch as typeof fetch)
  assertEquals(stats, { seguidores: 13677, vistas30d: 3200000, alcance90d: 560000, interacciones90d: 590000 })
})

Deno.test('fetchTiktokStats mapea los campos correctos (video_views, no video_views_count)', async () => {
  let urlCapturada: string | undefined
  const fakeFetch = async (url: string | URL) => {
    urlCapturada = url.toString()
    return new Response(
      JSON.stringify({
        data: [{ total_followers_count: 4600, total_likes: 105000, video_views: 240000 }],
      }),
      { status: 200 },
    )
  }
  const stats = await fetchTiktokStats('k', fakeFetch as typeof fetch)
  assertEquals(stats, { seguidores: 4600, likes: 105000, videoTopVistas: 240000 })
  assertStringIncludes(urlCapturada!, 'fields=total_followers_count%2Ctotal_likes%2Cvideo_views')
  assertStringIncludes(urlCapturada!, 'date_preset=last_30d')
})

Deno.test('fetchYoutubeStats mapea los campos correctos (2 llamadas separadas)', async () => {
  const fakeFetch = fakeFetchPorUrl([
    { contiene: 'fields=subscriber_count%2Cview_count', data: { subscriber_count: 210, view_count: 1450000 } },
    { contiene: 'fields=views', data: { views: 24896 } },
  ])
  const stats = await fetchYoutubeStats('k', fakeFetch as typeof fetch)
  assertEquals(stats, { suscriptores: 210, vistasHistoricas: 1450000, vistas30d: 24896 })
})
