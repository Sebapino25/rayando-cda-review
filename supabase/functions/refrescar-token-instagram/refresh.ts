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

// El refresh puede devolver 200 con un token "zombie": Meta invalidó la
// sesión de fondo (OAuthException 190) pero el endpoint de refresh igual
// contesta bien. Este chequeo lo caza pegándole a /me con el token nuevo.
export async function validarTokenInstagram(
  accessTokenNuevo: string,
  fetchImpl: typeof fetch = fetch,
): Promise<void> {
  const url = `https://graph.instagram.com/me?fields=id&access_token=${accessTokenNuevo}`
  const resp = await fetchImpl(url)
  if (resp.ok) return

  const texto = await resp.text()
  const codigo = (() => {
    try {
      return JSON.parse(texto)?.error?.code
    } catch {
      return undefined
    }
  })()

  if (codigo === 190) {
    throw new Error(
      `Instagram: el token nuevo sigue muerto (OAuthException 190). Meta invalidó la sesión; el refresco automático no lo puede arreglar.`,
    )
  }
  throw new Error(`Instagram: no se pudo validar el token nuevo con GET /me (${resp.status}): ${texto}`)
}
