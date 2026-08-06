import { getSupabaseAdmin } from '../_shared/supabaseAdmin.ts'
import { enviarAlerta } from '../_shared/email.ts'
import { refrescarTokenTiktok } from './refresh.ts'

Deno.serve(async (_req: Request) => {
  const supabase = getSupabaseAdmin()

  const clientKey = Deno.env.get('TIKTOK_CLIENT_KEY')
  const clientSecret = Deno.env.get('TIKTOK_CLIENT_SECRET')
  if (!clientKey || !clientSecret) {
    await enviarAlerta(
      'Rayando el CDA: faltan TIKTOK_CLIENT_KEY/TIKTOK_CLIENT_SECRET',
      'La Edge Function refrescar-token-tiktok no tiene los secrets de la app de TikTok configurados. Cargarlos en Project Settings > Edge Functions > Secrets.',
    )
    return new Response(JSON.stringify({ error: 'Faltan TIKTOK_CLIENT_KEY/TIKTOK_CLIENT_SECRET' }), { status: 500 })
  }

  const { data: tokenRow } = await supabase
    .from('tiktok_token')
    .select('refresh_token')
    .eq('id', true)
    .maybeSingle()

  if (!tokenRow) {
    // Esperado hasta que se haga la autorización manual inicial (ver
    // pipeline/tiktok_oauth_intercambiar_codigo.py) — no manda alerta para
    // no spamear mientras TikTok todavía no está en uso.
    return new Response(JSON.stringify({ ok: true, mensaje: 'No hay token de TikTok guardado todavía' }), {
      status: 200,
    })
  }

  try {
    const nuevo = await refrescarTokenTiktok(tokenRow.refresh_token, clientKey, clientSecret)
    const { error: upsertError } = await supabase.from('tiktok_token').upsert({
      id: true,
      access_token: nuevo.accessToken,
      refresh_token: nuevo.refreshToken,
      vence_en: nuevo.venceEn,
      actualizado_en: new Date().toISOString(),
    })
    if (upsertError) {
      await enviarAlerta(
        'Rayando el CDA: el token de TikTok se refrescó pero no se pudo guardar en la base de datos',
        `${upsertError.message}\n\nEl token VIEJO sigue en la base de datos (el nuevo se perdió). Esto necesita atención manual.`,
      )
      return new Response(JSON.stringify({ error: `Se refrescó pero no se pudo guardar: ${upsertError.message}` }), {
        status: 500,
      })
    }
    return new Response(JSON.stringify({ ok: true, vence_en: nuevo.venceEn }), { status: 200 })
  } catch (e) {
    const mensaje = e instanceof Error ? e.message : String(e)
    await enviarAlerta(
      'Rayando el CDA: falló el refresco automático del token de TikTok',
      `${mensaje}\n\nEl access token de TikTok vence a las 24hs — si esto sigue fallando, hay que rehacer la autorización manual (ver pipeline/README.md).`,
    )
    return new Response(JSON.stringify({ error: mensaje }), { status: 500 })
  }
})
