import { getSupabaseAdmin } from '../_shared/supabaseAdmin.ts'
import { enviarAlerta } from '../_shared/email.ts'
import { excedeLimite, VENTANA_MINUTOS_PIN, MAX_INTENTOS_PIN } from './pin.ts'
import { obtenerAccessTokenYoutube, publicarYoutube } from './youtube.ts'
import { publicarReel } from './instagram.ts'
import { publicarTiktok } from './tiktok.ts'

const CLAIM_EXPIRA_MINUTOS = 10

// CORS: la función se llama desde el navegador (app React) vía
// supabase.functions.invoke(), que dispara un preflight OPTIONS porque
// manda Authorization + Content-Type: application/json entre orígenes
// distintos. Sin estos headers en TODAS las respuestas (incluidas las de
// error), el navegador bloquea la request antes de que llegue al handler.
const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
}
const jsonHeaders = { ...corsHeaders, 'Content-Type': 'application/json' }

Deno.serve(async (req: Request) => {
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders })
  }

  if (req.method !== 'POST') {
    return new Response(JSON.stringify({ error: 'Método no permitido' }), { status: 405, headers: jsonHeaders })
  }

  let body: { clip_id?: string; pin?: string; dry_run?: boolean }
  try {
    body = await req.json()
  } catch {
    return new Response(JSON.stringify({ error: 'Body inválido, se espera JSON' }), { status: 400, headers: jsonHeaders })
  }

  const { clip_id: clipId, pin, dry_run: dryRun = false } = body
  if (!clipId || !pin) {
    return new Response(JSON.stringify({ error: 'Faltan clip_id y/o pin' }), { status: 400, headers: jsonHeaders })
  }

  const supabase = getSupabaseAdmin()

  // --- Rate limit de intentos fallidos de PIN ---
  const desde = new Date(Date.now() - VENTANA_MINUTOS_PIN * 60_000).toISOString()
  const { count: intentosRecientes, error: countError } = await supabase
    .from('pin_intentos')
    .select('*', { count: 'exact', head: true })
    .gte('creado_en', desde)
  if (countError) {
    return new Response(
      JSON.stringify({ error: `No se pudo chequear el límite de intentos: ${countError.message}` }),
      { status: 500, headers: jsonHeaders },
    )
  }
  if (excedeLimite(intentosRecientes ?? 0)) {
    // La alerta NO se manda acá: mientras se está bloqueado por este 429 no
    // se llega nunca al insert de pin_intentos, así que intentosRecientes
    // queda congelado y este bloque se ejecutaría en cada request del
    // bloqueo (o ninguna, si varias requests concurrentes empujan el
    // conteo de un salto por encima del umbral). La alerta se manda una
    // sola vez, en el momento exacto en que el insert cruza el umbral —
    // ver más abajo, en la rama de PIN incorrecto.
    return new Response(JSON.stringify({ error: 'Demasiados intentos fallidos, esperá unos minutos.' }), {
      status: 429,
      headers: jsonHeaders,
    })
  }

  // --- Validar PIN ---
  const pinEsperado = Deno.env.get('PUBLISH_PIN')
  if (!pinEsperado || pin !== pinEsperado) {
    // Se manda la alerta solo en el insert que empuja el conteo al umbral
    // por primera vez: una vez alcanzado, todas las requests siguientes se
    // frenan en el 429 de arriba antes de llegar a este insert, así que
    // esto ocurre a lo sumo una vez por breach (salvo carreras en paralelo,
    // que son un caso raro y acotado, no el spam sin límite del bug original).
    const alcanzaLimite = (intentosRecientes ?? 0) + 1 === MAX_INTENTOS_PIN
    await supabase.from('pin_intentos').insert({})
    if (alcanzaLimite) {
      await enviarAlerta(
        'Rayando el CDA: demasiados intentos de PIN',
        `Se alcanzó el límite de intentos de PIN (${MAX_INTENTOS_PIN} en los últimos ${VENTANA_MINUTOS_PIN} minutos). Alguien podría estar intentando adivinarlo.`,
      )
    }
    return new Response(JSON.stringify({ error: 'PIN incorrecto' }), { status: 401, headers: jsonHeaders })
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
      headers: jsonHeaders,
    })
  }
  if (!reclamada) {
    return new Response(
      JSON.stringify({ error: 'El clip ya se está publicando, ya se publicó, o no está en estado aprobado.' }),
      { status: 409, headers: jsonHeaders },
    )
  }

  if (!reclamada.video_url) {
    await supabase.from('clips').update({ publicando_en: null }).eq('id', clipId)
    return new Response(
      JSON.stringify({
        error: 'Falta video_url en este clip (es anterior a este subsistema) — re-procesar el clip o subir el video a Storage a mano.',
      }),
      { status: 422, headers: jsonHeaders },
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
      { status: 200, headers: jsonHeaders },
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
          // Instagram no deja FINISHED un Reel al toque: tiene que procesar el
          // video primero, y a veces tarda más de 60s (caso real 2026-08-05:
          // un contenedor tardó ~65s y esto lo cortaba antes de tiempo, aunque
          // el video terminaba bien). 120s dejan margen real sin acercarse al
          // límite duro de la plataforma: Supabase corta la función a los 150s
          // si no responde nada (Request idle timeout), y todavía falta lugar
          // en ese presupuesto para YouTube/TikTok en el mismo request.
          containerTimeoutMs: 120_000,
        },
      )
      actualizacion.instagram_media_id = mediaId
    } catch (e) {
      errores.push(`Instagram: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  if (publicarTiktokFlag) {
    try {
      // El access token de TikTok vence a las 24hs (a diferencia del de
      // Instagram, que dura 60 días) — no alcanza con un secret estático,
      // se lee de rayando_cda.tiktok_token, que refrescar-token-tiktok
      // mantiene al día.
      const { data: tiktokTokenRow, error: tiktokTokenError } = await supabase
        .from('tiktok_token')
        .select('access_token')
        .eq('id', true)
        .maybeSingle()
      if (tiktokTokenError || !tiktokTokenRow) {
        throw new Error('No hay token de TikTok guardado — revisar refrescar-token-tiktok.')
      }
      const publishId = await publicarTiktok(reclamada.video_url, reclamada.copy_tiktok || '', {
        accessToken: tiktokTokenRow.access_token,
      })
      actualizacion.tiktok_publish_id = publishId
    } catch (e) {
      errores.push(`TikTok: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  if (errores.length > 0) {
    await supabase.from('clips').update({ ...actualizacion, publicando_en: null }).eq('id', clipId)
    await enviarAlerta(`Rayando el CDA: falló la publicación de un clip (${clipId})`, errores.join('\n'))
    return new Response(JSON.stringify({ error: errores.join(' | ') }), { status: 502, headers: jsonHeaders })
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
      { status: 500, headers: jsonHeaders },
    )
  }

  // Best-effort: borrar el video de Storage ahora que ya se publicó en todas
  // las redes habilitadas. Los uploads a cut-time hacen que el bucket
  // clips-video crezca sin límite si nadie lo limpia (mismo criterio que el
  // borrado al rechazar un clip, del lado del frontend) — un fallo acá no
  // debe afectar la respuesta: el clip ya quedó publicado=true.
  const marker = '/object/public/clips-video/'
  const idx = reclamada.video_url.indexOf(marker)
  if (idx !== -1) {
    const path = reclamada.video_url.slice(idx + marker.length)
    try {
      await supabase.storage.from('clips-video').remove([path])
    } catch (e) {
      console.error(`No se pudo borrar el video de Storage para el clip ${clipId}:`, e)
    }
  }

  return new Response(JSON.stringify({ ok: true, clip: publicado }), { status: 200, headers: jsonHeaders })
})
