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
//
// El routing exige el `date_preset` correcto (o su ausencia, vía
// `sinDatePreset`) además del campo — si el código pidiera, por ejemplo,
// `total_interactions` con `date_preset=last_30d` en vez de `last_90d`,
// ninguna entrada de `mapeos` matchea y el fake lanza, haciendo fallar el
// test (exactamente la clase de bug que se corrigió: período equivocado).
// Además se capturan todas las URLs llamadas para poder hacer aserciones
// explícitas de `date_preset` por campo, igual que ya hacía el test de
// TikTok.
function fakeFetchPorUrl(
  mapeos: Array<{ contiene: string[]; sinDatePreset?: boolean; data: Record<string, unknown> }>,
) {
  const urlsCapturadas: string[] = []
  const fetchImpl = async (url: string | URL) => {
    const urlStr = url.toString()
    urlsCapturadas.push(urlStr)
    const match = mapeos.find((m) => {
      const cumpleContiene = m.contiene.every((sub) => urlStr.includes(sub))
      const cumpleSinDatePreset = !m.sinDatePreset || !urlStr.includes('date_preset=')
      return cumpleContiene && cumpleSinDatePreset
    })
    if (!match) {
      throw new Error(`fakeFetchPorUrl: no hay mock para la URL ${urlStr}`)
    }
    return new Response(JSON.stringify({ data: [match.data] }), { status: 200 })
  }
  return { fetchImpl: fetchImpl as typeof fetch, urlsCapturadas }
}

Deno.test('fetchInstagramStats mapea los campos correctos y usa el date_preset correcto por campo (4 llamadas separadas)', async () => {
  const { fetchImpl, urlsCapturadas } = fakeFetchPorUrl([
    { contiene: ['fields=followers_count'], sinDatePreset: true, data: { followers_count: 13677 } },
    { contiene: ['fields=views', 'date_preset=last_30d'], data: { views: 3200000 } },
    { contiene: ['fields=total_interactions', 'date_preset=last_90d'], data: { total_interactions: 590000 } },
    { contiene: ['fields=reach_1d', 'date_preset=last_90d'], data: { reach_1d: 560000 } },
  ])
  const stats = await fetchInstagramStats('k', fetchImpl)
  assertEquals(stats, { seguidores: 13677, vistas30d: 3200000, alcance90d: 560000, interacciones90d: 590000 })

  // Aserciones explícitas de date_preset por campo (no solo el routing del
  // mock, que ya haría fallar el test si el período estuviera mal): esto es
  // justo el tipo de parámetro que causó el bug real en producción (ver
  // docs/superpowers/plans/2026-07-30-media-kit-vivo.md).
  assertStringIncludes(urlsCapturadas.find((u) => u.includes('fields=views'))!, 'date_preset=last_30d')
  assertStringIncludes(urlsCapturadas.find((u) => u.includes('fields=total_interactions'))!, 'date_preset=last_90d')
  assertStringIncludes(urlsCapturadas.find((u) => u.includes('fields=reach_1d'))!, 'date_preset=last_90d')
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

Deno.test('fetchInstagramStats lanza WindsorError si un campo de Windsor.ai no viene como número', async () => {
  // Simula un campo renombrado/eliminado en Windsor.ai: `views` viene
  // `undefined` en la fila devuelta. Antes de la validación, esto se
  // convertía en NaN y terminaba guardándose como NULL en Supabase sin
  // ningún error — ver windsor.ts (campoNumerico).
  const { fetchImpl } = fakeFetchPorUrl([
    { contiene: ['fields=followers_count'], sinDatePreset: true, data: { followers_count: 13677 } },
    { contiene: ['fields=views', 'date_preset=last_30d'], data: { views_renombrado: 3200000 } },
    { contiene: ['fields=total_interactions', 'date_preset=last_90d'], data: { total_interactions: 590000 } },
    { contiene: ['fields=reach_1d', 'date_preset=last_90d'], data: { reach_1d: 560000 } },
  ])
  await assertRejects(() => fetchInstagramStats('k', fetchImpl), WindsorError)
})

Deno.test('fetchWindsorConnector avisa por console.warn si Windsor.ai devuelve más de una fila', async () => {
  const fakeFetch = fakeFetchOk({ data: [{ followers_count: 100 }, { followers_count: 100 }] })
  const warnOriginal = console.warn
  let avisoCapturado: string | undefined
  console.warn = (msg: string) => {
    avisoCapturado = msg
  }
  try {
    await fetchWindsorConnector('instagram', ['followers_count'], null, 'k', fakeFetch as typeof fetch)
  } finally {
    console.warn = warnOriginal
  }
  assertStringIncludes(avisoCapturado ?? '', 'devolvió 2 filas')
})

Deno.test('fetchYoutubeStats mapea los campos correctos y usa el date_preset correcto (2 llamadas separadas)', async () => {
  const { fetchImpl, urlsCapturadas } = fakeFetchPorUrl([
    {
      contiene: ['fields=subscriber_count%2Cview_count'],
      sinDatePreset: true,
      data: { subscriber_count: 210, view_count: 1450000 },
    },
    { contiene: ['fields=views', 'date_preset=last_30d'], data: { views: 24896 } },
  ])
  const stats = await fetchYoutubeStats('k', fetchImpl)
  assertEquals(stats, { suscriptores: 210, vistasHistoricas: 1450000, vistas30d: 24896 })

  // Igual que en Instagram: `views` debe llevar date_preset=last_30d, no
  // combinarse sin fecha con el resto (esa combinación fue el mismo bug de
  // agregación, ver windsor.ts).
  assertStringIncludes(urlsCapturadas.find((u) => u.includes('fields=views'))!, 'date_preset=last_30d')
})
