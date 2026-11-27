// Qué cambia entre programas al publicar un clip. Recda ("rayando") usa
// exactamente los mismos secretos y flags de siempre (sin prefijo); SPA
// ("spa") usa los suyos con prefijo SPA_, para que nunca publique por error
// en las cuentas de Recda (ni al revés).
//
// Secretos de SPA (Supabase > Edge Functions > Secrets):
//   SPA_PUBLISH_PIN                     PIN propio de SPA
//   SPA_PUBLICAR_YOUTUBE / _INSTAGRAM / _FACEBOOK = "true" para prender cada red
//   SPA_YOUTUBE_CLIENT_ID / _CLIENT_SECRET / _REFRESH_TOKEN  (proyecto Google Cloud de SPA)
//   SPA_FACEBOOK_PAGE_ID / SPA_FACEBOOK_PAGE_TOKEN           (token de PÁGINA, no vence)
//   SPA_INSTAGRAM_BUSINESS_ACCOUNT_ID   (Instagram vinculado a esa página)
// En SPA, Instagram usa el mismo token de página por graph.facebook.com
// (inicio de sesión con Facebook), así que no hay token que refrescar.
// TikTok queda apagado en SPA hasta que se vea aparte.

export const GRAPH_FACEBOOK_BASE = 'https://graph.facebook.com/v24.0'
export const GRAPH_INSTAGRAM_BASE = 'https://graph.instagram.com'

export type ProgramaId = 'rayando' | 'spa'

export interface ProgramaPublicacion {
  id: ProgramaId
  nombre: string
  schema: string
  pin: string | undefined
  youtube: { activo: boolean; clientId?: string; clientSecret?: string; refreshToken?: string }
  instagram: {
    activo: boolean
    igUserId?: string
    graphBase: string
    // 'tabla': token en <schema>.instagram_token (Recda, refrescado cada 60 días).
    // 'secreto': token de página fijo en los secretos (SPA).
    origenToken: 'tabla' | 'secreto'
    tokenFijo?: string
    containerTimeoutMs: number
  }
  facebook: { activo: boolean; pageId?: string; pageToken?: string }
  tiktokPermitido: boolean
  // Recda pone "Del capítulo N…" + #RECDA<N> en YouTube; SPA todavía no
  // tiene columna capitulo (A1b), así que su descripción queda tal cual.
  usaCapitulo: boolean
}

type Env = (nombre: string) => string | undefined

export function normalizarPrograma(valor: unknown): ProgramaId | null {
  if (valor === undefined || valor === null || valor === '') return 'rayando'
  if (valor === 'rayando' || valor === 'recda') return 'rayando'
  if (valor === 'spa') return 'spa'
  return null
}

export function configPrograma(id: ProgramaId, env: Env = (n) => Deno.env.get(n)): ProgramaPublicacion {
  if (id === 'spa') {
    return {
      id,
      nombre: 'SPAreírse',
      schema: 'siempre_pasa_algo',
      pin: env('SPA_PUBLISH_PIN'),
      youtube: {
        activo: env('SPA_PUBLICAR_YOUTUBE') === 'true',
        clientId: env('SPA_YOUTUBE_CLIENT_ID'),
        clientSecret: env('SPA_YOUTUBE_CLIENT_SECRET'),
        refreshToken: env('SPA_YOUTUBE_REFRESH_TOKEN'),
      },
      instagram: {
        activo: env('SPA_PUBLICAR_INSTAGRAM') === 'true',
        igUserId: env('SPA_INSTAGRAM_BUSINESS_ACCOUNT_ID'),
        graphBase: GRAPH_FACEBOOK_BASE,
        origenToken: 'secreto',
        tokenFijo: env('SPA_FACEBOOK_PAGE_TOKEN'),
        // Facebook va antes que Instagram en el mismo request y Supabase corta
        // a los 150 s: se deja algo menos de espera que en Recda.
        containerTimeoutMs: 110_000,
      },
      facebook: {
        activo: env('SPA_PUBLICAR_FACEBOOK') === 'true',
        pageId: env('SPA_FACEBOOK_PAGE_ID'),
        pageToken: env('SPA_FACEBOOK_PAGE_TOKEN'),
      },
      tiktokPermitido: false,
      usaCapitulo: false,
    }
  }
  return {
    id: 'rayando',
    nombre: 'Rayando el CDA',
    schema: 'rayando_cda',
    pin: env('PUBLISH_PIN'),
    youtube: {
      activo: env('PUBLICAR_YOUTUBE') === 'true',
      clientId: env('YOUTUBE_CLIENT_ID'),
      clientSecret: env('YOUTUBE_CLIENT_SECRET'),
      refreshToken: env('YOUTUBE_REFRESH_TOKEN'),
    },
    instagram: {
      activo: env('PUBLICAR_INSTAGRAM') === 'true',
      igUserId: env('INSTAGRAM_BUSINESS_ACCOUNT_ID'),
      graphBase: GRAPH_INSTAGRAM_BASE,
      origenToken: 'tabla',
      containerTimeoutMs: 120_000,
    },
    // Recda no publica en Facebook hoy: queda apagado salvo que se definan
    // PUBLICAR_FACEBOOK=true y FACEBOOK_PAGE_ID / FACEBOOK_PAGE_TOKEN.
    facebook: {
      activo: env('PUBLICAR_FACEBOOK') === 'true',
      pageId: env('FACEBOOK_PAGE_ID'),
      pageToken: env('FACEBOOK_PAGE_TOKEN'),
    },
    tiktokPermitido: true,
    usaCapitulo: true,
  }
}

// Lista de secretos que faltan para las redes prendidas. Se revisa antes de
// reclamar el clip, para no dejar a medio publicar por un secreto olvidado.
export function secretosFaltantes(p: ProgramaPublicacion): string[] {
  const pre = p.id === 'spa' ? 'SPA_' : ''
  const faltan: string[] = []
  if (p.youtube.activo) {
    if (!p.youtube.clientId) faltan.push(`${pre}YOUTUBE_CLIENT_ID`)
    if (!p.youtube.clientSecret) faltan.push(`${pre}YOUTUBE_CLIENT_SECRET`)
    if (!p.youtube.refreshToken) faltan.push(`${pre}YOUTUBE_REFRESH_TOKEN`)
  }
  if (p.instagram.activo) {
    if (!p.instagram.igUserId) faltan.push(`${pre}INSTAGRAM_BUSINESS_ACCOUNT_ID`)
    if (p.instagram.origenToken === 'secreto' && !p.instagram.tokenFijo) faltan.push(`${pre}FACEBOOK_PAGE_TOKEN`)
  }
  if (p.facebook.activo) {
    if (!p.facebook.pageId) faltan.push(`${pre}FACEBOOK_PAGE_ID`)
    if (!p.facebook.pageToken) faltan.push(`${pre}FACEBOOK_PAGE_TOKEN`)
  }
  return [...new Set(faltan)]
}
