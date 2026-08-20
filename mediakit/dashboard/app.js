// Dashboard interno: mismo historial que las 2 sparklines resumidas del
// media kit público (../public/app.js), pero graficando los 9 números
// completos. Anon key de solo lectura, protegida por RLS — ver
// mediakit/supabase_migration_media_kit_stats_history.sql.

const SUPABASE_URL = 'https://qfxfwfcdgqcbmdspjvtk.supabase.co'
const SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InFmeGZ3ZmNkZ3FjYm1kc3BqdnRrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODMzNTczMzEsImV4cCI6MjA5ODkzMzMzMX0.A6faHhleIsyOAlix8H7OEHjT406eZEUiOdCoBwYbUkE'

const fmtPct = (n) => `${n >= 0 ? '+' : ''}${n}%`
const fmtFecha = new Intl.DateTimeFormat('es-CL', { day: 'numeric', month: 'short', year: '2-digit' })

function dibujar(idSvg, idGrowth, puntos) {
  const svg = document.getElementById(idSvg)
  const elGrowth = document.getElementById(idGrowth)
  if (!svg) return false
  const resultado = construirSparkline(svg, puntos)
  if (!resultado) {
    // Ej. yt_vistas_30d, que solo empezó a guardarse en el snapshot de hoy:
    // menos de 2 puntos con valor real todavía. Se avisa en vez de dejar el
    // svg en blanco sin explicación.
    if (elGrowth) elGrowth.textContent = 'Necesita más semanas de datos'
    return false
  }
  if (elGrowth) {
    const base = `${fmtFecha.format(resultado.primero.t)} → ${fmtFecha.format(resultado.ultimo.t)}`
    elGrowth.textContent = resultado.crecimientoPct !== null ? `${fmtPct(resultado.crecimientoPct)} · ${base}` : base
  }
  return true
}

async function cargarDashboard() {
  const wrap = document.querySelector('.dashboard-wrap')
  try {
    const resp = await fetch(
      `${SUPABASE_URL}/rest/v1/media_kit_stats_history?select=*&order=snapshot_en.asc`,
      {
        headers: {
          apikey: SUPABASE_ANON_KEY,
          Authorization: `Bearer ${SUPABASE_ANON_KEY}`,
          'Accept-Profile': 'rayando_cda',
        },
      },
    )
    if (!resp.ok) throw new Error(`Supabase REST devolvió ${resp.status}`)
    const filas = await resp.json()
    if (!Array.isArray(filas) || filas.length < 2) {
      document.getElementById('sin-datos').hidden = false
      return
    }

    const serie = (campo) => filas.map((f) => ({ t: new Date(f.snapshot_en), v: f[campo] }))
    const serieCombinada = (...campos) =>
      filas.map((f) => ({
        t: new Date(f.snapshot_en),
        v: campos.reduce((acc, c) => acc + (f[c] ?? 0), 0),
      }))

    dibujar('chart-alcance', 'growth-alcance', serieCombinada('ig_vistas_30d', 'tiktok_video_top_vistas', 'yt_vistas_30d'))
    dibujar('chart-audiencia', 'growth-audiencia', serieCombinada('ig_seguidores', 'tiktok_seguidores', 'yt_suscriptores'))

    dibujar('chart-ig-seguidores', 'growth-ig-seguidores', serie('ig_seguidores'))
    dibujar('chart-ig-vistas', 'growth-ig-vistas', serie('ig_vistas_30d'))
    dibujar('chart-ig-interacciones', 'growth-ig-interacciones', serie('ig_interacciones_90d'))

    dibujar('chart-tiktok-seguidores', 'growth-tiktok-seguidores', serie('tiktok_seguidores'))
    dibujar('chart-tiktok-likes', 'growth-tiktok-likes', serie('tiktok_likes'))
    dibujar('chart-tiktok-video-top', 'growth-tiktok-video-top', serie('tiktok_video_top_vistas'))

    dibujar('chart-yt-suscriptores', 'growth-yt-suscriptores', serie('yt_suscriptores'))
    dibujar('chart-yt-vistas-historicas', 'growth-yt-vistas-historicas', serie('yt_vistas_historicas'))
    dibujar('chart-yt-vistas-30d', 'growth-yt-vistas-30d', serie('yt_vistas_30d'))

    dibujar('chart-programas', 'growth-programas', serie('programas_emitidos'))
  } catch (err) {
    console.error('No se pudo cargar el dashboard:', err)
    if (wrap) {
      const aviso = document.createElement('p')
      aviso.className = 'dashboard-empty'
      aviso.textContent = 'No se pudo cargar el historial ahora mismo. Probá recargar la página.'
      wrap.appendChild(aviso)
    }
  }
}

cargarDashboard()
