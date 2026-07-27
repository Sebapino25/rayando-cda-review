import { getSupabaseAdmin } from '../_shared/supabaseAdmin.ts'
import { enviarAlerta } from '../_shared/email.ts'
import { refrescarTokenInstagram } from './refresh.ts'

Deno.serve(async (_req: Request) => {
  const supabase = getSupabaseAdmin()

  const { data: tokenRow } = await supabase
    .from('instagram_token')
    .select('access_token')
    .eq('id', true)
    .maybeSingle()

  if (!tokenRow) {
    await enviarAlerta(
      'Rayando el CDA: no hay token de Instagram guardado',
      'La tabla rayando_cda.instagram_token está vacía. Hay que cargar un token inicial a mano (ver pipeline/README.md, sección Instagram Graph API) antes de que el refresco automático pueda seguir funcionando.',
    )
    return new Response(JSON.stringify({ error: 'No hay token guardado' }), { status: 500 })
  }

  try {
    const nuevo = await refrescarTokenInstagram(tokenRow.access_token)
    await supabase.from('instagram_token').upsert({
      id: true,
      access_token: nuevo.accessToken,
      vence_en: nuevo.venceEn,
      actualizado_en: new Date().toISOString(),
    })
    return new Response(JSON.stringify({ ok: true, vence_en: nuevo.venceEn }), { status: 200 })
  } catch (e) {
    const mensaje = e instanceof Error ? e.message : String(e)
    await enviarAlerta(
      'Rayando el CDA: falló el refresco automático del token de Instagram',
      `${mensaje}\n\nHay que renovarlo a mano: ver pipeline/README.md, sección Instagram Graph API. Este es el único caso que queda como tarea manual.`,
    )
    return new Response(JSON.stringify({ error: mensaje }), { status: 500 })
  }
})
