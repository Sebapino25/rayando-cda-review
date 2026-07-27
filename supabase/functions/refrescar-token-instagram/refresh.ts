export interface TokenRefrescado {
  accessToken: string
  venceEn: string
}

// Documentado en pipeline/.env.example: el token de Instagram se refresca
// sin interacción humana vía este GET, mientras no haya vencido del todo.
export async function refrescarTokenInstagram(
  accessTokenActual: string,
  fetchImpl: typeof fetch = fetch,
): Promise<TokenRefrescado> {
  const url = `https://graph.instagram.com/refresh_access_token?grant_type=ig_refresh_token&access_token=${accessTokenActual}`
  const resp = await fetchImpl(url)
  if (!resp.ok) {
    throw new Error(`Instagram: no se pudo refrescar el token (${resp.status}): ${await resp.text()}`)
  }
  const data = await resp.json()
  const expiresInSeconds = data.expires_in as number
  const venceEn = new Date(Date.now() + expiresInSeconds * 1000).toISOString()
  return { accessToken: data.access_token as string, venceEn }
}
