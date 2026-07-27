import { getSupabaseAdmin } from '../_shared/supabaseAdmin.ts'
import { enviarAlerta } from '../_shared/email.ts'
import { excedeLimite } from './pin.ts'
import { obtenerAccessTokenYoutube, publicarYoutube } from './youtube.ts'
import { publicarReel } from './instagram.ts'
import { publicarTiktok } from './tiktok.ts'

const CLAIM_EXPIRA_MINUTOS = 10
const RATE_LIMIT_VENTANA_MINUTOS = 10

Deno.serve(async (req: Request) => {
  if (req.method !== 'POST') {
    return new Response(JSON.stringify({ error: 'Método no permitido' }), { status: 405 })
  }

  let body: { clip_id?: string; pin?: string; dry_run?: boolean }
  try {
    body = await req.json()
  } catch {
    return new Response(JSON.stringify({ error: 'Body inválido, se espera JSON' }), { status: 400 })
  }

  const { clip_id: clipId, pin, dry_run: dryRun = false } = body
  if (!clipId || !pin) {
    return new Response(JSON.stringify({ error: 'Faltan clip_id y/o pin' }), { status: 400 })
  }

  const supabase = getSupabaseAdmin()

  // --- Rate limit de intentos fallidos de PIN ---
  const desde = new Date(Date.now() - RATE_LIMIT_VENTANA_MINUTOS * 60_000).toISOString()
  const { count: intentosRecientes, error: countError } = await supabase
    .from('pin_intentos')
    .select('*', { count: 'exact', head: true })
    .gte('creado_en', desde)
  if (countError) {
    return new Response(
      JSON.stringify({ error: `No se pudo chequear el límite de intentos: ${countError.message}` }),
      { status: 500 },
    )
  }
  if (excedeLimite(intentosRecientes ?? 0)) {
    await enviarAlerta(
      'Rayando el CDA: demasiados intentos de PIN',
      `Se superó el límite de intentos de PIN (${intentosRecientes} en los últimos ${RATE_LIMIT_VENTANA_MINUTOS} minutos). Alguien podría estar intentando adivinarlo.`,
    )
    return new Response(JSON.stringify({ error: 'Demasiados intentos fallidos, esperá unos minutos.' }), {
      status: 429,
    })
  }

  // --- Validar PIN ---
  const pinEsperado = Deno.env.get('PUBLISH_PIN')
  if (!pinEsperado || pin !== pinEsperado) {
    await supabase.from('pin_intentos').insert({})
    return new Response(JSON.stringify({ error: 'PIN incorrecto' }), { status: 401 })
  }

  // --- Reclamar la fila de forma atómica (evita duplicados por doble click) ---
  const expiraAntes = new Date(Date.now() - CLAIM_EXPIRA_MINUTOS * 60_000).toISOString()
  const { data: reclamada, error: claimError } = await supabase
    .from('clips')
    .update({ publicando_en: new Date().toISOString() })
    .eq('id', clipId)
    .eq('estado', 'aprobado')
    .eq('publicado', false)
    .or(`publicando_en.is.null,publicando_en.lt.${expiraAntes}`)
    .select()
    .maybeSingle()

  if (claimError) {
    return new Response(JSON.stringify({ error: `No se pudo reclamar el clip: ${claimError.message}` }), {
      status: 500,
    })
  }
  if (!reclamada) {
    return new Response(
      JSON.stringify({ error: 'El clip ya se está publicando, ya se publicó, o no está en estado aprobado.' }),
      { status: 409 },
    )
  }

  if (!reclamada.video_url) {
    await supabase.from('clips').update({ publicando_en: null }).eq('id', clipId)
    return new Response(
      JSON.stringify({
        error: 'Falta video_url en este clip (es anterior a este subsistema) — re-procesar el clip o subir el video a Storage a mano.',
      }),
      { status: 422 },
    )
  }

  if (dryRun) {
    await supabase.from('clips').update({ publicando_en: null }).eq('id', clipId)
    return new Response(
      JSON.stringify({
        dry_run: true,
        clip: reclamada,
        mensaje: 'Dry-run OK: PIN válido, clip reclamable, video_url presente. No se publicó nada real.',
      }),
      { status: 200 },
    )
  }

  const publicarYoutubeFlag = Deno.env.get('PUBLICAR_YOUTUBE') === 'true'
  const publicarInstagramFlag = Deno.env.get('PUBLICAR_INSTAGRAM') === 'true'
  const publicarTiktokFlag = Deno.env.get('PUBLICAR_TIKTOK') === 'true'

  const errores: string[] = []
  const actualizacion: Record<string, unknown> = {}

  if (publicarYoutubeFlag) {
    try {
      const accessToken = await obtenerAccessTokenYoutube({
        clientId: Deno.env.get('YOUTUBE_CLIENT_ID')!,
        clientSecret: Deno.env.get('YOUTUBE_CLIENT_SECRET')!,
        refreshToken: Deno.env.get('YOUTUBE_REFRESH_TOKEN')!,
      })
      await publicarYoutube(
        reclamada.youtube_video_id,
        reclamada.youtube_titulo || reclamada.titulo || '',
        reclamada.youtube_descripcion || '',
        accessToken,
      )
    } catch (e) {
      errores.push(`YouTube: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  if (publicarInstagramFlag && !reclamada.instagram_media_id) {
    try {
      const { data: tokenRow, error: tokenError } = await supabase
        .from('instagram_token')
        .select('access_token')
        .eq('id', true)
        .maybeSingle()
      if (tokenError || !tokenRow) {
        throw new Error('No hay token de Instagram guardado — revisar refrescar-token-instagram.')
      }
      const mediaId = await publicarReel(
        reclamada.video_url,
        reclamada.copy_instagram || '',
        reclamada.portada_url ?? null,
        {
          igUserId: Deno.env.get('INSTAGRAM_BUSINESS_ACCOUNT_ID')!,
          accessToken: tokenRow.access_token,
          containerTimeoutMs: 60_000,
        },
      )
      actualizacion.instagram_media_id = mediaId
    } catch (e) {
      errores.push(`Instagram: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  if (publicarTiktokFlag) {
    try {
      const publishId = await publicarTiktok(reclamada.video_url, reclamada.copy_tiktok || '', {
        accessToken: Deno.env.get('TIKTOK_ACCESS_TOKEN')!,
      })
      actualizacion.tiktok_publish_id = publishId
    } catch (e) {
      errores.push(`TikTok: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  if (errores.length > 0) {
    await supabase.from('clips').update({ ...actualizacion, publicando_en: null }).eq('id', clipId)
    await enviarAlerta(`Rayando el CDA: falló la publicación de un clip (${clipId})`, errores.join('\n'))
    return new Response(JSON.stringify({ error: errores.join(' | ') }), { status: 502 })
  }

  const { data: publicado, error: finalError } = await supabase
    .from('clips')
    .update({ ...actualizacion, publicado: true, publicado_en: new Date().toISOString(), publicando_en: null })
    .eq('id', clipId)
    .select()
    .single()

  if (finalError) {
    await enviarAlerta(
      `Rayando el CDA: clip ${clipId} se publicó pero no se pudo marcar publicado=true`,
      finalError.message,
    )
    return new Response(
      JSON.stringify({ error: `Se publicó pero no se pudo actualizar el registro: ${finalError.message}` }),
      { status: 500 },
    )
  }

  return new Response(JSON.stringify({ ok: true, clip: publicado }), { status: 200 })
})
