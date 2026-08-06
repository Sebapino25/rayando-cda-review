export interface TokenRefrescado {
  accessToken: string
  refreshToken: string
  venceEn: string
}

// TikTok, a diferencia de Instagram, exige client_key + client_secret en
// cada refresco (no alcanza con el token viejo) y devuelve un refresh_token
// NUEVO cada vez (rotación) — el viejo queda invalidado, así que hay que
// guardar el que llega en la respuesta, no reusar el de antes.
export async function refrescarTokenTiktok(
  refreshTokenActual: string,
  clientKey: string,
  clientSecret: string,
  fetchImpl: typeof fetch = fetch,
): Promise<TokenRefrescado> {
  const resp = await fetchImpl('https://open.tiktokapis.com/v2/oauth/token/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      'Cache-Control': 'no-cache',
    },
    body: new URLSearchParams({
      client_key: clientKey,
      client_secret: clientSecret,
      grant_type: 'refresh_token',
      refresh_token: refreshTokenActual,
    }),
  })
  const texto = await resp.text()
  if (!resp.ok) {
    throw new Error(`TikTok: no se pudo refrescar el token (${resp.status}): ${texto}`)
  }
  const data = JSON.parse(texto)
  if (data.error) {
    throw new Error(`TikTok: la API devolvió un error al refrescar: ${texto}`)
  }
  const expiresInSeconds = data.expires_in as number
  const venceEn = new Date(Date.now() + expiresInSeconds * 1000).toISOString()
  return {
    accessToken: data.access_token as string,
    refreshToken: data.refresh_token as string,
    venceEn,
  }
}
