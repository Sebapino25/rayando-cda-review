// Recordatorio semanal (lunes) de actualización manual de los números del
// media kit. Reemplaza al cron de actualizar-stats-mediakit, que dejó de
// servir cuando venció el trial de Windsor.ai (09/08/2026) — ver
// mediakit/README.md.
//
// No escribe nada: solo lee la fila de media_kit_stats para armar un mail
// con los valores publicados hoy y el UPDATE listo para editar.

import { getSupabaseAdmin } from '../_shared/supabaseAdmin.ts'
import { enviarAlerta } from '../_shared/email.ts'
import { armarMensaje, type StatsActuales } from './mensaje.ts'

Deno.serve(async (_req: Request) => {
  const supabase = getSupabaseAdmin()

  const { data: fila, error } = await supabase
    .from('media_kit_stats')
    .select(
      'ig_seguidores, ig_vistas_30d, ig_interacciones_90d, ' +
        'tiktok_seguidores, tiktok_likes, tiktok_video_top_vistas, ' +
        'yt_suscriptores, yt_vistas_historicas, yt_vistas_30d, ' +
        'programas_emitidos, ig_actualizado_en, tiktok_actualizado_en, yt_actualizado_en',
    )
    .eq('id', true)
    .maybeSingle()

  if (error) {
    // Se manda el mail igual (con el texto de fallback de armarMensaje): el
    // punto de este recordatorio es que el lunes llegue algo a la bandeja.
    // Quedarse callado por un error de lectura sería justo lo contrario.
    console.error('No se pudo leer media_kit_stats:', error.message)
  }

  await enviarAlerta(
    'Rayando el CDA: números del media kit para actualizar',
    armarMensaje((fila as StatsActuales | null) ?? null, new Date()),
  )

  return new Response(JSON.stringify({ ok: true, leyo_fila: Boolean(fila) }), { status: 200 })
})
