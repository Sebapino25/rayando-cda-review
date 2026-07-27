// Envía un email de alerta vía Resend. Usa el sender de sandbox
// (onboarding@resend.dev) — funciona sin verificar dominio propio, pero
// solo puede mandar al email asociado a la cuenta de Resend (suficiente
// acá: ALERT_EMAIL_TO es el email del dueño del proyecto).
export async function enviarAlerta(
  asunto: string,
  cuerpo: string,
  fetchImpl: typeof fetch = fetch,
): Promise<void> {
  const apiKey = Deno.env.get('RESEND_API_KEY')
  const destino = Deno.env.get('ALERT_EMAIL_TO')
  if (!apiKey || !destino) {
    console.error('Falta RESEND_API_KEY o ALERT_EMAIL_TO, no se pudo enviar la alerta:', asunto, cuerpo)
    return
  }
  const resp = await fetchImpl('https://api.resend.com/emails', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      from: 'Rayando el CDA <onboarding@resend.dev>',
      to: [destino],
      subject: asunto,
      text: cuerpo,
    }),
  })
  if (!resp.ok) {
    console.error(`Resend devolvió ${resp.status} al enviar "${asunto}": ${await resp.text()}`)
  }
}
