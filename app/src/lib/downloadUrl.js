// Convierte una URL pública de Supabase Storage en una URL de descarga
// directa: agregando ?download=<nombre> el propio Storage de Supabase
// responde con Content-Disposition: attachment, así que el navegador baja
// el archivo en vez de solo abrirlo (funciona cross-origin, a diferencia
// del atributo HTML `download`, que los navegadores ignoran cuando la URL
// es de otro dominio).
export function downloadUrl(url, filename) {
  if (!url) return url
  const separator = url.includes('?') ? '&' : '?'
  return `${url}${separator}download=${encodeURIComponent(filename)}`
}
