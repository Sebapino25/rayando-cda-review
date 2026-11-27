import { assertEquals } from 'https://deno.land/std@0.224.0/assert/mod.ts'
import { configPrograma, normalizarPrograma, secretosFaltantes } from './programa.ts'

const envDe = (o: Record<string, string>) => (n: string) => o[n]

Deno.test('normalizarPrograma: vacío y recda son rayando; spa; otro es null', () => {
  assertEquals(normalizarPrograma(undefined), 'rayando')
  assertEquals(normalizarPrograma(''), 'rayando')
  assertEquals(normalizarPrograma('recda'), 'rayando')
  assertEquals(normalizarPrograma('spa'), 'spa')
  assertEquals(normalizarPrograma('otro'), null)
})

Deno.test('Recda usa los secretos de siempre, sin prefijo, y Facebook apagado', () => {
  const p = configPrograma('rayando', envDe({
    PUBLISH_PIN: '1234', PUBLICAR_YOUTUBE: 'true', PUBLICAR_INSTAGRAM: 'true',
    YOUTUBE_CLIENT_ID: 'a', YOUTUBE_CLIENT_SECRET: 'b', YOUTUBE_REFRESH_TOKEN: 'c',
    INSTAGRAM_BUSINESS_ACCOUNT_ID: 'ig', SPA_PUBLISH_PIN: '9999',
  }))
  assertEquals(p.schema, 'rayando_cda')
  assertEquals(p.pin, '1234')
  assertEquals(p.instagram.graphBase, 'https://graph.instagram.com')
  assertEquals(p.instagram.origenToken, 'tabla')
  assertEquals(p.instagram.containerTimeoutMs, 120_000)
  assertEquals(p.facebook.activo, false)
  assertEquals(p.tiktokPermitido, true)
  assertEquals(p.usaCapitulo, true)
  assertEquals(secretosFaltantes(p), [])
})

Deno.test('SPA nunca hereda secretos de Recda', () => {
  const p = configPrograma('spa', envDe({
    PUBLISH_PIN: '1234', PUBLICAR_YOUTUBE: 'true', PUBLICAR_INSTAGRAM: 'true',
    YOUTUBE_CLIENT_ID: 'a', INSTAGRAM_BUSINESS_ACCOUNT_ID: 'ig',
  }))
  assertEquals(p.schema, 'siempre_pasa_algo')
  assertEquals(p.pin, undefined)
  assertEquals(p.youtube.activo, false)
  assertEquals(p.instagram.activo, false)
  assertEquals(p.facebook.activo, false)
  assertEquals(p.tiktokPermitido, false)
})

Deno.test('SPA: Instagram por graph.facebook.com con el token de página', () => {
  const p = configPrograma('spa', envDe({
    SPA_PUBLISH_PIN: '5555', SPA_PUBLICAR_INSTAGRAM: 'true', SPA_PUBLICAR_FACEBOOK: 'true',
    SPA_FACEBOOK_PAGE_ID: 'pg', SPA_FACEBOOK_PAGE_TOKEN: 'tk', SPA_INSTAGRAM_BUSINESS_ACCOUNT_ID: 'ig',
  }))
  assertEquals(p.pin, '5555')
  assertEquals(p.instagram.graphBase, 'https://graph.facebook.com/v24.0')
  assertEquals(p.instagram.origenToken, 'secreto')
  assertEquals(p.instagram.tokenFijo, 'tk')
  assertEquals(p.facebook.pageId, 'pg')
  assertEquals(secretosFaltantes(p), [])
})

Deno.test('secretosFaltantes avisa lo que falta en SPA', () => {
  const p = configPrograma('spa', envDe({
    SPA_PUBLICAR_YOUTUBE: 'true', SPA_PUBLICAR_INSTAGRAM: 'true', SPA_PUBLICAR_FACEBOOK: 'true',
  }))
  assertEquals(secretosFaltantes(p), [
    'SPA_YOUTUBE_CLIENT_ID', 'SPA_YOUTUBE_CLIENT_SECRET', 'SPA_YOUTUBE_REFRESH_TOKEN',
    'SPA_INSTAGRAM_BUSINESS_ACCOUNT_ID', 'SPA_FACEBOOK_PAGE_TOKEN', 'SPA_FACEBOOK_PAGE_ID',
  ])
})
