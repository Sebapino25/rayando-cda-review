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

// Solo escribe si el valor es un número real. Un campo NULL en la fila
// (o ausente) no es 'number', así que esta función no toca el DOM y el
// span se queda con el snapshot horneado en el HTML (ver Task 3/finding 3
// de la revisión final) en vez de mostrar "0" — que es lo que devolvía
// `fmt.format(null)` antes de este chequeo, y que una marca podría leer
// como "0 seguidores" real.
function setStatSiEsNumero(id, valor) {
  if (typeof valor === 'number' && Number.isFinite(valor)) {
    setText(id, fmt.format(valor))
  }
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
    // Sin fila todavía, o falla de red/Supabase más abajo (catch): la
    // página se queda con el snapshot horneado en el HTML — números reales
    // (aunque desactualizados) de la última vez que se editó index.html a
    // mano con datos frescos de media_kit_stats, no placeholders "—". Ver
    // finding 3 de la revisión final: nunca se muestra ni un error ni una
    // pared de guiones a la marca que está mirando la página.
    if (!stats) return

    // El total del hero sí usa `?? 0`: es una suma de 3 campos, y si uno
    // solo viene NULL (plataforma caída) preferimos un total parcial en
    // vivo antes que descartar todo el hero y mostrar el snapshot viejo.
    const heroTotal = (stats.ig_vistas_30d ?? 0) + (stats.tiktok_video_top_vistas ?? 0) + (stats.yt_vistas_30d ?? 0)
    setText('stat-hero-vistas', fmt.format(heroTotal))

    // Costo por 1.000 vistas del plan Presencia, recalculado del alcance
    // real en vivo (no un benchmark externo — es puro $500.000 / vistas).
    if (heroTotal > 0) {
      setText('stat-cpm-presencia', fmt.format(Math.round((500000 / heroTotal) * 1000)))
    }

    setStatSiEsNumero('stat-ig-seguidores', stats.ig_seguidores)
    setStatSiEsNumero('stat-ig-vistas', stats.ig_vistas_30d)
    setStatSiEsNumero('stat-ig-interacciones', stats.ig_interacciones_90d)

    setStatSiEsNumero('stat-tiktok-seguidores', stats.tiktok_seguidores)
    setStatSiEsNumero('stat-tiktok-likes', stats.tiktok_likes)
    setStatSiEsNumero('stat-tiktok-video-top', stats.tiktok_video_top_vistas)

    setStatSiEsNumero('stat-yt-suscriptores', stats.yt_suscriptores)
    setStatSiEsNumero('stat-yt-vistas-card', stats.yt_vistas_historicas)
    setStatSiEsNumero('stat-programas', stats.programas_emitidos)

    setStatSiEsNumero('stat-audiencia-hombres', stats.audiencia_hombres_pct)
    setStatSiEsNumero('stat-audiencia-25-44', stats.audiencia_25_44_pct)
    setStatSiEsNumero('stat-audiencia-hombres-25-44', stats.audiencia_hombres_25_44_pct)

    if (
      typeof stats.ig_seguidores === 'number' && Number.isFinite(stats.ig_seguidores) && stats.ig_seguidores > 0 &&
      typeof stats.ig_vistas_30d === 'number' && Number.isFinite(stats.ig_vistas_30d)
    ) {
      const multiplicador = stats.ig_vistas_30d / stats.ig_seguidores
      // Math.round, no .toFixed(1): en esta página el "." es el separador
      // de miles de todos los demás números (es-CL), así que "186.0" al
      // lado de "2.544.087" lee como un glitch de formato, no un decimal.
      setText('stat-multiplicador', String(Math.round(multiplicador)))
    }
  } catch (err) {
    // Falla de red o de Supabase: la página se queda con el snapshot
    // horneado en el HTML — nunca se muestra un error a la marca que está
    // mirando la página.
    console.error('No se pudieron cargar los números en vivo:', err)
  }
}

document.getElementById('btn-descargar-pdf').addEventListener('click', () => {
  window.print()
})

cargarStats()
