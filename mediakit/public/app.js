// Media kit vivo: lee rayando_cda.media_kit_stats vía la API REST de
// Supabase (PostgREST) con la anon key — de solo lectura, protegido por
// la policy media_kit_stats_anon_select (ver mediakit/supabase_migration_media_kit_stats.sql).
// Sin build tool: la anon key es pública por diseño (Supabase la protege
// con RLS, no con secreto), así que va hardcodeada acá, igual de expuesta
// que en cualquier bundle de frontend.

const SUPABASE_URL = 'https://qfxfwfcdgqcbmdspjvtk.supabase.co'
const SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InFmeGZ3ZmNkZ3FjYm1kc3BqdnRrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODMzNTczMzEsImV4cCI6MjA5ODkzMzMzMX0.A6faHhleIsyOAlix8H7OEHjT406eZEUiOdCoBwYbUkE'

const fmt = new Intl.NumberFormat('es-CL')

function setText(id, value) {
  const el = document.getElementById(id)
  if (el) el.textContent = value
}

async function cargarStats() {
  try {
    const resp = await fetch(
      `${SUPABASE_URL}/rest/v1/media_kit_stats?select=*&id=eq.true`,
      {
        headers: {
          apikey: SUPABASE_ANON_KEY,
          Authorization: `Bearer ${SUPABASE_ANON_KEY}`,
          // La tabla vive en el schema rayando_cda, no en public (el default
          // expuesto por PostgREST). Sin este header, PostgREST busca
          // media_kit_stats en public y devuelve 404 (PGRST205) — verificado
          // con curl contra el proyecto real antes de agregar esta línea.
          'Accept-Profile': 'rayando_cda',
        },
      },
    )
    if (!resp.ok) throw new Error(`Supabase REST devolvió ${resp.status}`)
    const filas = await resp.json()
    const stats = filas[0]
    if (!stats) return // sin fila todavía: quedan los defaults del HTML

    const heroTotal = (stats.ig_vistas_30d ?? 0) + (stats.tiktok_video_top_vistas ?? 0) + (stats.yt_vistas_30d ?? 0)
    setText('stat-hero-vistas', fmt.format(heroTotal))

    setText('stat-ig-seguidores', fmt.format(stats.ig_seguidores))
    setText('stat-ig-vistas', fmt.format(stats.ig_vistas_30d))
    setText('stat-ig-interacciones', fmt.format(stats.ig_interacciones_90d))

    setText('stat-tiktok-seguidores', fmt.format(stats.tiktok_seguidores))
    setText('stat-tiktok-likes', fmt.format(stats.tiktok_likes))
    setText('stat-tiktok-video-top', fmt.format(stats.tiktok_video_top_vistas))

    setText('stat-yt-suscriptores', fmt.format(stats.yt_suscriptores))
    setText('stat-yt-vistas-card', fmt.format(stats.yt_vistas_historicas))
    setText('stat-programas', fmt.format(stats.programas_emitidos))

    if (stats.ig_seguidores > 0) {
      const multiplicador = stats.ig_vistas_30d / stats.ig_seguidores
      setText('stat-multiplicador', multiplicador.toFixed(1))
    }
  } catch (err) {
    // Falla de red o de Supabase: la página se queda con los valores por
    // defecto del HTML (Task 5) — nunca se muestra un error a la marca
    // que está mirando la página.
    console.error('No se pudieron cargar los números en vivo:', err)
  }
}

document.getElementById('btn-descargar-pdf').addEventListener('click', () => {
  window.print()
})

cargarStats()
