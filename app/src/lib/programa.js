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
    puedePublicar: false, // por ahora: se aprueba acá y se descarga el clip para subirlo a mano
    guia: false,
  },
}

const pedido = new URLSearchParams(window.location.search).get('p')
export const PROGRAMA = PROGRAMAS[pedido] || PROGRAMAS.rayando
