import { createClient, SupabaseClient } from '@supabase/supabase-js'

// SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY los inyecta Supabase
// automáticamente en toda Edge Function — no hace falta configurarlos
// como secretos custom.
// `schema` permite usar el mismo cliente para otro programa (SPA vive en
// `siempre_pasa_algo`); sin argumento sigue siendo `rayando_cda`, como siempre.
// deno-lint-ignore no-explicit-any
export function getSupabaseAdmin(schema = 'rayando_cda'): SupabaseClient<any, any, any> {
  const url = Deno.env.get('SUPABASE_URL')
  const key = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')
  if (!url || !key) {
    throw new Error('Faltan SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY en el entorno de la función')
  }
  return createClient(url, key, { db: { schema } })
}
