// Una sola app de revisión para varios programas. Se elige con ?p= en la URL:
//   .../rayando-cda-review/          -> Rayando el CDA (por defecto, igual que siempre)
//   .../rayando-cda-review/?p=spa    -> SPAreírse (Siempre Pasa Algo)
// Cada programa tiene su propio schema en Supabase y sus propios buckets.
const PROGRAMAS = {
  rayando: {
    id: 'rayando',
    nombre: 'Rayando el CDA',
    logo: 'logo.png',
    fondoLogo: undefined,
    schema: 'rayando_cda',
    bucketVideo: 'clips-video',
    bucketPortadas: 'portadas',
    puedePublicar: true, // botón "Publicar en redes" (YouTube + Instagram + TikTok)
    funcionPublicar: 'publicar-clip',
    redesPublicar: ['YouTube', 'Instagram'], // las que publica el botón (TikTok va aparte, en su panel)
    tiktok: true, // panel de TikTok dentro de "Publicar en redes"
    marcaManual: false, // botón "Ya lo publiqué" para marcar sin publicar por API
    limpiezaAutomatica: true, // limpiar_clips.py borra la reserva a los RESERVA_DIAS
    guia: true,
  },
  spa: {
    id: 'spa',
    nombre: 'SPAreírse',
    logo: 'logo-spa.png',
    fondoLogo: '#070A13', // el logo de SPA es neón sobre transparente: necesita fondo oscuro
    schema: 'siempre_pasa_algo',
    bucketVideo: 'clips-video-spa',
    bucketPortadas: 'portadas-spa',
    // Publica con su propia función y sus propias cuentas (secretos SPA_* en Supabase).
    puedePublicar: true,
    funcionPublicar: 'publicar-clip-spa',
    redesPublicar: ['YouTube', 'Instagram', 'Facebook'],
    tiktok: false, // TikTok se ve aparte; mientras, se descarga y se sube a mano
    marcaManual: true, // se mantiene "Ya lo publiqué" por si algo se sube a mano
    limpiezaAutomatica: false, // la reserva (Antiguas) se guarda hasta que se publique
    guia: false,
  },
}

const pedido = new URLSearchParams(window.location.search).get('p')
export const PROGRAMA = PROGRAMAS[pedido] || PROGRAMAS.rayando
