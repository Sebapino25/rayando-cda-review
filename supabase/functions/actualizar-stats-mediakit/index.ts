import { getSupabaseAdmin } from '../_shared/supabaseAdmin.ts'
import { enviarAlerta } from '../_shared/email.ts'
import { fetchInstagramStats, fetchTiktokStats, fetchYoutubeStats, WindsorError } from './windsor.ts'

const DIAS_ANTES_DE_ALERTAR = 3

Deno.serve(async (_req: Request) => {
  const apiKey = Deno.env.get('WINDSOR_API_KEY')
  if (!apiKey) {
    await enviarAlerta(
      'Rayando el CDA: falta WINDSOR_API_KEY',
      'La Edge Function actualizar-stats-mediakit no tiene el secreto WINDSOR_API_KEY configurado. Cargarlo en Project Settings > Edge Functions > Secrets.',
    )
    return new Response(JSON.stringify({ error: 'Falta WINDSOR_API_KEY' }), { status: 500 })
  }

  const supabase = getSupabaseAdmin()
  const ahora = new Date().toISOString()
  const actualizacion: Record<string, unknown> = {}
  const fallas: string[] = []

  try {
    const ig = await fetchInstagramStats(apiKey)
    Object.assign(actualizacion, {
      ig_seguidores: ig.seguidores,
      ig_vistas_30d: ig.vistas30d,
      ig_alcance_90d: ig.alcance90d,
      ig_interacciones_90d: ig.interacciones90d,
      ig_actualizado_en: ahora,
    })
  } catch (e) {
    fallas.push(`Instagram: ${e instanceof WindsorError ? e.message : String(e)}`)
  }

  try {
    const tiktok = await fetchTiktokStats(apiKey)
    Object.assign(actualizacion, {
      tiktok_seguidores: tiktok.seguidores,
      tiktok_likes: tiktok.likes,
      tiktok_video_top_vistas: tiktok.videoTopVistas,
      tiktok_actualizado_en: ahora,
    })
  } catch (e) {
    fallas.push(`TikTok: ${e instanceof WindsorError ? e.message : String(e)}`)
  }

  try {
    const yt = await fetchYoutubeStats(apiKey)
    Object.assign(actualizacion, {
      yt_suscriptores: yt.suscriptores,
      yt_vistas_historicas: yt.vistasHistoricas,
      yt_vistas_30d: yt.vistas30d,
      yt_actualizado_en: ahora,
    })
  } catch (e) {
    fallas.push(`YouTube: ${e instanceof WindsorError ? e.message : String(e)}`)
  }

  if (Object.keys(actualizacion).length > 0) {
    const { error: updateError } = await supabase
      .from('media_kit_stats')
      .update(actualizacion)
      .eq('id', true)
    if (updateError) {
      fallas.push(`Guardar en Supabase: ${updateError.message}`)
    }
  }

  if (fallas.length > 0) {
    await alertarSiCorresponde(supabase, fallas, apiKey)
  }

  return new Response(
    JSON.stringify({ ok: fallas.length === 0, actualizados: Object.keys(actualizacion), fallas }),
    { status: fallas.length === 0 ? 200 : 207 },
  )
})

// Solo manda mail si alguna plataforma lleva más de DIAS_ANTES_DE_ALERTAR
// sin actualizarse — evita mandar un mail cada 5 minutos por una falla de
// un día que se puede resolver sola en la próxima corrida.
async function alertarSiCorresponde(
  supabase: ReturnType<typeof getSupabaseAdmin>,
  fallas: string[],
  apiKey: string,
): Promise<void> {
  const { data: fila } = await supabase
    .from('media_kit_stats')
    .select('ig_actualizado_en, tiktok_actualizado_en, yt_actualizado_en')
    .eq('id', true)
    .maybeSingle()

  const limite = Date.now() - DIAS_ANTES_DE_ALERTAR * 24 * 60 * 60 * 1000
  const timestamps = [fila?.ig_actualizado_en, fila?.tiktok_actualizado_en, fila?.yt_actualizado_en]
  const hayAlgunaVencida = timestamps.some((t) => !t || new Date(t as string).getTime() < limite)
  if (!hayAlgunaVencida) return

  const pistaWindsorTrial = apiKey
    ? '\n\nSi las 3 plataformas fallan con error de autenticación, revisar si venció el trial de Windsor.ai y pasarlo a plan pago.'
    : ''
  await enviarAlerta(
    'Rayando el CDA: el media kit vivo lleva días sin actualizarse',
    `${fallas.join('\n')}${pistaWindsorTrial}`,
  )
}
