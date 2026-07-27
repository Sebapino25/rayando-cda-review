import { assertEquals } from 'https://deno.land/std@0.224.0/assert/mod.ts'
import { enviarAlerta } from './email.ts'

Deno.test('enviarAlerta no lanza si faltan las env vars, solo loguea', async () => {
  Deno.env.delete('RESEND_API_KEY')
  Deno.env.delete('ALERT_EMAIL_TO')
  let llamadoFetch = false
  const fakeFetch = async () => {
    llamadoFetch = true
    return new Response('{}', { status: 200 })
  }
  await enviarAlerta('asunto', 'cuerpo', fakeFetch as typeof fetch)
  assertEquals(llamadoFetch, false)
})

Deno.test('enviarAlerta manda el POST correcto a Resend', async () => {
  Deno.env.set('RESEND_API_KEY', 'clave-test')
  Deno.env.set('ALERT_EMAIL_TO', 'destino@ejemplo.com')
  let capturado: { url: string; body: string } | undefined
  const fakeFetch = async (url: string | URL, init?: RequestInit) => {
    capturado = { url: url.toString(), body: init?.body as string }
    return new Response('{}', { status: 200 })
  }
  await enviarAlerta('Asunto de prueba', 'Cuerpo de prueba', fakeFetch as typeof fetch)
  assertEquals(capturado?.url, 'https://api.resend.com/emails')
  const body = JSON.parse(capturado!.body)
  assertEquals(body.to, ['destino@ejemplo.com'])
  assertEquals(body.subject, 'Asunto de prueba')
  Deno.env.delete('RESEND_API_KEY')
  Deno.env.delete('ALERT_EMAIL_TO')
})
