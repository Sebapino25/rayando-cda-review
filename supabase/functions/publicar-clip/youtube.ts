export interface YoutubeCredenciales {
  clientId: string
  clientSecret: string
  refreshToken: string
}

export async function obtenerAccessTokenYoutube(
  creds: YoutubeCredenciales,
  fetchImpl: typeof fetch = fetch,
): Promise<string> {
  const resp = await fetchImpl('https://oauth2.googleapis.com/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      client_id: creds.clientId,
      client_secret: creds.clientSecret,
      refresh_token: creds.refreshToken,
      grant_type: 'refresh_token',
    }).toString(),
  })
  if (!resp.ok) {
    throw new Error(`YouTube: no se pudo refrescar el access token (${resp.status}): ${await resp.text()}`)
  }
  const data = await resp.json()
  return data.access_token as string
}

// La API de YouTube exige mandar snippet/status completos en el update: si
// se manda solo title/description, categoryId puede resetearse. Por eso se
// lee el recurso actual primero y se pisan solo los campos que corresponden.
export async function publicarYoutube(
  videoId: string,
  titulo: string,
  descripcion: string,
  accessToken: string,
  fetchImpl: typeof fetch = fetch,
): Promise<void> {
  const getResp = await fetchImpl(
    `https://www.googleapis.com/youtube/v3/videos?part=snippet,status&id=${videoId}`,
    { headers: { Authorization: `Bearer ${accessToken}` } },
  )
  if (!getResp.ok) {
    throw new Error(`YouTube: no se pudo leer el video ${videoId} (${getResp.status}): ${await getResp.text()}`)
  }
  const getData = await getResp.json()
  const item = getData.items?.[0]
  if (!item) {
    throw new Error(`YouTube: no se encontró el video ${videoId} (¿ID inválido o de otro canal?)`)
  }

  const snippet = { ...item.snippet, title: titulo, description: descripcion }
  const status = { ...item.status, privacyStatus: 'public' }

  const putResp = await fetchImpl('https://www.googleapis.com/youtube/v3/videos?part=snippet,status', {
    method: 'PUT',
    headers: {
      Authorization: `Bearer ${accessToken}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ id: videoId, snippet, status }),
  })
  if (!putResp.ok) {
    throw new Error(`YouTube: no se pudo publicar el video ${videoId} (${putResp.status}): ${await putResp.text()}`)
  }
}
