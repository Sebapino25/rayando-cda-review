import { useEffect, useRef, useState } from 'react'
import { CheckCircle, SpinnerGap, XCircle } from '@phosphor-icons/react'
import { supabase } from '../lib/supabaseClient'

const POLL_MS = 5000
// TikTok puede tardar varios minutos en terminar de procesar (ver
// TikTokPublishPanel.jsx) — 10 minutos de polling da margen real sin dejar
// la pestaña pegada consultando para siempre si algo quedó colgado.
const POLL_MAX_MS = 10 * 60 * 1000
const ESTADOS_FINALES = new Set(['PUBLISH_COMPLETE', 'FAILED'])

/**
 * Punto 5.e de las Content Sharing Guidelines de TikTok: hay que monitorear
 * el estado real del post (vía publish/status/fetch) en vez de asumir éxito
 * apenas termina la subida. Este badge hace polling mientras el clip está
 * "publicado" y muestra el resultado real cuando TikTok lo confirma.
 */
export default function TikTokStatusBadge({ publishId }) {
  const [status, setStatus] = useState(null) // { status, fail_reason } | 'error' | null (cargando)
  const startedAtRef = useRef(Date.now())

  useEffect(() => {
    if (!publishId) return
    let cancelado = false
    let timeoutId

    function reintentarSiHayTiempo() {
      if (!cancelado && Date.now() - startedAtRef.current < POLL_MAX_MS) {
        timeoutId = setTimeout(consultar, POLL_MS)
      }
    }

    async function consultar() {
      try {
        const { data, error } = await supabase.functions.invoke('publicar-clip', {
          body: { action: 'tiktok_publish_status', publish_id: publishId },
        })
        if (cancelado) return
        if (error || data?.ok === false) {
          // Puede ser transitorio (red, token vencido un instante) — se
          // muestra el error pero se sigue reintentando, no se abandona.
          setStatus('error')
          reintentarSiHayTiempo()
          return
        }
        setStatus({ status: data.status, failReason: data.fail_reason })
        if (!ESTADOS_FINALES.has(data.status)) {
          reintentarSiHayTiempo()
        }
      } catch {
        if (cancelado) return
        setStatus('error')
        reintentarSiHayTiempo()
      }
    }
    consultar()

    return () => {
      cancelado = true
      clearTimeout(timeoutId)
    }
  }, [publishId])

  if (!publishId || status === null) {
    return (
      <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <SpinnerGap size={13} className="animate-spin" /> TikTok: procesando…
      </span>
    )
  }
  if (status === 'error' || status.status === 'FAILED') {
    return (
      <span className="flex items-center gap-1.5 text-xs text-destructive">
        <XCircle size={13} weight="fill" />
        TikTok: {status === 'error' ? 'no se pudo consultar el estado' : `falló (${status.failReason || 'sin detalle'})`}
      </span>
    )
  }
  if (status.status === 'PUBLISH_COMPLETE') {
    return (
      <span className="flex items-center gap-1.5 text-xs text-accent">
        <CheckCircle size={13} weight="fill" /> TikTok: publicado
      </span>
    )
  }
  return (
    <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
      <SpinnerGap size={13} className="animate-spin" /> TikTok: procesando…
    </span>
  )
}
