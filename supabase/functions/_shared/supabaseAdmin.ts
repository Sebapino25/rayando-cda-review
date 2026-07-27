import { createClient, SupabaseClient } from '@supabase/supabase-js'

// SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY los inyecta Supabase
// automáticamente en toda Edge Function — no hace falta configurarlos
// como secretos custom.
export function getSupabaseAdmin(): SupabaseClient {
  const url = Deno.env.get('SUPABASE_URL')
  const key = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')
  if (!url || !key) {
    throw new Error('Faltan SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY en el entorno de la función')
  }
  return createClient(url, key, { db: { schema: 'rayando_cda' } })
}
