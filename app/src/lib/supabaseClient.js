import { createClient } from '@supabase/supabase-js'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY

if (!supabaseUrl || !supabaseAnonKey) {
  throw new Error(
    'Faltan VITE_SUPABASE_URL y/o VITE_SUPABASE_ANON_KEY. Definilas en un archivo .env (ver .env.example).'
  )
}

// La tabla "clips" vive en el schema "rayando_cda", no en "public".
// Ese schema tiene que estar en la lista de "Exposed schemas" del proyecto
// en Supabase (Project Settings > Data API).
export const supabase = createClient(supabaseUrl, supabaseAnonKey, {
  db: { schema: 'rayando_cda' },
})
