import { useState } from 'react'
import { CheckCircle, Wrench, XCircle, NoteBlank, ArrowSquareOut, ArrowUUpLeft, SpinnerGap, CaretDown, DownloadSimple, Trash, Info } from '@phosphor-icons/react'
import { downloadUrl } from '../lib/downloadUrl'
import TikTokPublishPanel from './TikTokPublishPanel'

const dateFormatter = new Intl.DateTimeFormat('es-AR', {
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
})

function formatDate(value) {
  if (!value) return ''
  try {
    return dateFormatter.format(new Date(value))
  } catch {
    return ''
  }
}

const STATE_META = {
  aprobado: { label: 'Aprobado', Icon: CheckCircle, className: 'bg-accent/10 text-accent' },
  correccion_video: { label: 'Corrección técnica de video', Icon: Wrench, className: 'bg-warning-bg text-warning' },
  rechazado: { label: 'Rechazado', Icon: XCircle, className: 'bg-destructive/10 text-destructive' },
}

function ReadOnlyField({ label, value }) {
  return (
    <div>
      <span className="block text-sm font-semibold text-foreground mb-1.5">{label}</span>
      <p className="w-full px-3.5 py-3 rounded-xl border border-border bg-muted text-[15px] leading-snug text-foreground whitespace-pre-wrap">
        {value && value.trim() ? value : <span className="text-muted-foreground">—</span>}
      </p>
    </div>
  )
}

export default function HistoryCard({ clip, onUndo, onCoverRemove, onPublicar, onDelete }) {
  const stateMeta = STATE_META[clip.estado] ?? STATE_META.rechazado
  const hasPendingComment = Boolean(clip.comentarios_video && clip.comentarios_video.trim())
  // Misma señal que ClipCard: si transcripcion todavía no coincide con
  // transcripcion_original, reprocesar_subtitulos.py (disparado cada 5 min
  // por auto_procesar.ps1) todavía no quemó la corrección sobre el video —
  // publicar ahora saldría con el subtítulo viejo.
  const transcripcionPendiente =
    (clip.transcripcion ?? '').trim() !== (clip.transcripcion_original ?? '').trim()
  const [undoing, setUndoing] = useState(false)
  const [errorMsg, setErrorMsg] = useState('')
  const [expanded, setExpanded] = useState(false)
  const [removingCover, setRemovingCover] = useState(false)
  const [publicando, setPublicando] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [publishOpen, setPublishOpen] = useState(false)
  const [pin, setPin] = useState('')
  const [tiktokPayload, setTiktokPayload] = useState(null)
  const [tiktokValido, setTiktokValido] = useState(true)

  async function handleUndo() {
    const confirmed = window.confirm('¿Seguro que quieres deshacer esta revisión?')
    if (!confirmed) return
    setUndoing(true)
    setErrorMsg('')
    try {
      await onUndo(clip.id)
    } catch (err) {
      setErrorMsg(err.message || 'No se pudo deshacer. Probá de nuevo.')
      setUndoing(false)
    }
  }

  async function handleCoverRemove() {
    if (!window.confirm('¿Quitar la portada actual? Vuelve a quedar en blanco hasta que alguien suba otra.')) return
    setRemovingCover(true)
    setErrorMsg('')
    try {
      await onCoverRemove(clip.id)
    } catch (err) {
      setErrorMsg(err.message || 'No se pudo quitar la portada. Probá de nuevo.')
    } finally {
      setRemovingCover(false)
    }
  }

  function cancelarPublicar() {
    setPublishOpen(false)
    setPin('')
  }

  async function confirmarPublicar() {
    if (transcripcionPendiente || !pin || !tiktokValido) return
    setPublicando(true)
    setErrorMsg('')
    try {
      await onPublicar(clip.id, { pin, tiktok: tiktokPayload })
      // Si sale bien, el clip pasa a publicado y la tarjeta se re-renderiza sola.
    } catch (err) {
      setErrorMsg(err.message || 'No se pudo publicar. Probá de nuevo.')
    } finally {
      setPublicando(false)
    }
  }

  async function handleDelete() {
    const confirmed = window.confirm(
      '¿Eliminar este clip? Se borra el registro y el video/portada guardados acá — esto no se puede deshacer, y no borra nada en YouTube.'
    )
    if (!confirmed) return
    setDeleting(true)
    setErrorMsg('')
    try {
      await onDelete(clip.id)
    } catch (err) {
      setErrorMsg(err.message || 'No se pudo eliminar. Probá de nuevo.')
      setDeleting(false)
    }
  }

  return (
    <article className="bg-surface rounded-2xl border border-border shadow-sm overflow-hidden">
      <details open={expanded} onToggle={(e) => setExpanded(e.target.open)}>
        <summary className="flex gap-3 p-4 cursor-pointer select-none list-none">
          {!clip.publicado && (
            <a
              href={`https://www.youtube.com/watch?v=${clip.youtube_video_id}`}
              target="_blank"
              rel="noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="relative shrink-0 w-28 sm:w-32 aspect-video rounded-lg overflow-hidden bg-muted"
            >
              <img
                src={`https://img.youtube.com/vi/${clip.youtube_video_id}/hqdefault.jpg`}
                alt=""
                className="w-full h-full object-cover"
                loading="lazy"
              />
              <ArrowSquareOut
                size={16}
                weight="bold"
                className="absolute bottom-1 right-1 text-white drop-shadow"
              />
            </a>
          )}

          {clip.portada_url && (
            <a
              href={downloadUrl(clip.portada_url, `portada-${clip.id}.jpg`)}
              onClick={(e) => e.stopPropagation()}
              title="Descargar portada"
              className="shrink-0 self-start w-8 h-8 rounded-full bg-muted flex items-center justify-center text-muted-foreground"
            >
              <DownloadSimple size={15} weight="bold" />
            </a>
          )}

          <div className="min-w-0 flex-1 flex flex-col gap-1.5">
            <span
              className={`inline-flex w-fit items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold ${stateMeta.className}`}
            >
              <stateMeta.Icon size={14} weight="fill" />
              {stateMeta.label}
            </span>
            <p className="text-[15px] font-semibold text-foreground truncate">
              {clip.youtube_titulo || 'Sin título'}
            </p>
            <p className="text-xs text-muted-foreground">
              {clip.revisado_por ? `${clip.revisado_por} · ` : ''}
              {formatDate(clip.revisado_en)}
            </p>
          </div>

          <CaretDown
            size={20}
            className={`shrink-0 self-center text-muted-foreground transition-transform ${expanded ? 'rotate-180' : ''}`}
          />
        </summary>

        <div className="border-t border-border">
          {!clip.publicado && (
            <div className="aspect-video bg-black">
              <iframe
                className="w-full h-full"
                src={`https://www.youtube.com/embed/${clip.youtube_video_id}`}
                title={clip.youtube_titulo || 'Clip'}
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowFullScreen
              />
            </div>
          )}
          <div className="p-4 flex flex-col gap-3.5">
            {clip.portada_url && (
              <div className="flex items-center gap-3">
                <div className="shrink-0 w-16 aspect-[9/16] rounded-lg overflow-hidden bg-muted border border-border">
                  <img src={clip.portada_url} alt="Portada" className="w-full h-full object-cover" />
                </div>
                <div className="flex flex-col gap-1.5 items-start">
                  <a
                    href={downloadUrl(clip.portada_url, `portada-${clip.id}.jpg`)}
                    className="flex items-center gap-1.5 text-sm font-semibold text-primary"
                  >
                    <DownloadSimple size={16} weight="bold" />
                    Descargar portada
                  </a>
                  <button
                    type="button"
                    onClick={handleCoverRemove}
                    disabled={removingCover}
                    className="flex items-center gap-1.5 text-sm font-semibold text-destructive disabled:opacity-40 cursor-pointer"
                  >
                    {removingCover ? (
                      <SpinnerGap size={16} className="animate-spin" />
                    ) : (
                      <Trash size={16} weight="bold" />
                    )}
                    Quitar portada
                  </button>
                </div>
              </div>
            )}
            <ReadOnlyField label="Copy Instagram" value={clip.copy_instagram} />
            <ReadOnlyField label="Copy TikTok" value={clip.copy_tiktok} />
            <ReadOnlyField label="Título de YouTube" value={clip.youtube_titulo} />
            <ReadOnlyField label="Descripción de YouTube" value={clip.youtube_descripcion} />
            <ReadOnlyField label="Transcripción" value={clip.transcripcion} />
          </div>
        </div>
      </details>

      {(clip.notas_revision || hasPendingComment) && (
        <div className="border-t border-border px-4 py-3 flex flex-col gap-2">
          {clip.notas_revision && (
            <p className="text-sm text-foreground">
              <span className="font-semibold">Notas de rechazo: </span>
              {clip.notas_revision}
            </p>
          )}
          {hasPendingComment && (
            <p className="flex items-start gap-1.5 text-sm text-warning bg-warning-bg/60 rounded-lg px-3 py-2">
              <NoteBlank size={16} className="shrink-0 mt-0.5" />
              <span>
                <span className="font-semibold">Pendiente de procesar: </span>
                {clip.comentarios_video}
              </span>
            </p>
          )}
          {transcripcionPendiente && (
            <p className="flex items-start gap-1.5 text-sm text-warning bg-warning-bg/60 rounded-lg px-3 py-2">
              <NoteBlank size={16} className="shrink-0 mt-0.5" />
              <span>
                <span className="font-semibold">Corrección de subtítulo pendiente: </span>
                el video todavía no se reprocesó con la transcripción corregida (se aplica solo, cada 5 min). No se puede publicar hasta que eso termine.
              </span>
            </p>
          )}
        </div>
      )}

      <div className="border-t border-border px-4 py-3 flex flex-col gap-2">
        {errorMsg && (
          <p className="text-sm text-destructive font-medium" role="alert">
            {errorMsg}
          </p>
        )}
        {clip.estado === 'aprobado' && clip.video_url && (
          <a
            href={downloadUrl(clip.video_url, `clip-${clip.id}.mp4`)}
            className="self-start flex items-center gap-1.5 text-sm font-semibold text-muted-foreground"
          >
            <DownloadSimple size={15} weight="bold" />
            Descargar clip (para subir a TikTok a mano)
          </a>
        )}
        {clip.estado === 'aprobado' && !clip.publicado && !publishOpen && (
          <button
            type="button"
            onClick={() => setPublishOpen(true)}
            disabled={publicando || transcripcionPendiente}
            title={transcripcionPendiente ? 'Hay una corrección de subtítulo sin aplicar al video todavía' : undefined}
            className="self-start flex items-center gap-1.5 text-sm font-semibold text-primary disabled:opacity-40 cursor-pointer"
          >
            <CheckCircle size={15} weight="bold" />
            Publicar en redes
          </button>
        )}
        {clip.estado === 'aprobado' && !clip.publicado && publishOpen && (
          <div className="rounded-xl border border-primary/30 bg-primary/5 p-3.5 flex flex-col gap-3">
            <p className="text-sm font-semibold text-foreground">Publicar en redes</p>
            <div className="text-[13px] text-muted-foreground leading-snug flex flex-col gap-0.5">
              <span><span className="font-medium text-foreground">YouTube:</span> {clip.youtube_titulo || '(sin título)'}</span>
              <span><span className="font-medium text-foreground">Instagram:</span> {clip.copy_instagram ? `${clip.copy_instagram.slice(0, 80)}${clip.copy_instagram.length > 80 ? '…' : ''}` : '(sin copy)'}</span>
            </div>
            <p className="flex items-start gap-1.5 text-xs text-warning">
              <Info size={14} className="shrink-0 mt-0.5" />
              Pasa el video a público en YouTube y publica el Reel en Instagram. No se puede deshacer.
            </p>

            <TikTokPublishPanel
              clip={clip}
              onChange={setTiktokPayload}
              onValidityChange={setTiktokValido}
            />

            <label className="block">
              <span className="block text-sm font-semibold text-foreground mb-1.5">PIN para publicar</span>
              <input
                type="password"
                inputMode="numeric"
                autoComplete="off"
                value={pin}
                onChange={(e) => setPin(e.target.value)}
                className="w-full h-12 px-3.5 rounded-xl border border-border bg-background text-[15px] text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </label>

            <div className="grid grid-cols-2 gap-3">
              <button
                type="button"
                onClick={cancelarPublicar}
                disabled={publicando}
                className="h-12 rounded-xl border-2 border-border text-foreground font-semibold text-sm disabled:opacity-40 active:scale-[0.98] transition-transform cursor-pointer"
              >
                Cancelar
              </button>
              <button
                type="button"
                onClick={confirmarPublicar}
                disabled={publicando || transcripcionPendiente || !pin || !tiktokValido}
                className="h-12 rounded-xl bg-primary text-primary-foreground font-semibold text-sm flex items-center justify-center gap-2 disabled:opacity-40 active:scale-[0.98] transition-transform cursor-pointer"
              >
                {publicando ? <SpinnerGap size={16} className="animate-spin" /> : <CheckCircle size={16} weight="bold" />}
                Publicar
              </button>
            </div>
          </div>
        )}
        {clip.publicado && (
          <span className="self-start flex items-center gap-1.5 text-sm font-semibold text-accent">
            <CheckCircle size={15} weight="fill" />
            Publicado
          </span>
        )}
        {!clip.publicado && (
          <button
            type="button"
            onClick={handleUndo}
            disabled={undoing}
            className="self-start flex items-center gap-1.5 text-sm font-semibold text-muted-foreground disabled:opacity-40 cursor-pointer"
          >
            {undoing ? (
              <SpinnerGap size={15} className="animate-spin" />
            ) : (
              <ArrowUUpLeft size={15} weight="bold" />
            )}
            Deshacer
          </button>
        )}
        <button
          type="button"
          onClick={handleDelete}
          disabled={deleting}
          className="self-start flex items-center gap-1.5 text-sm font-semibold text-destructive disabled:opacity-40 cursor-pointer"
        >
          {deleting ? (
            <SpinnerGap size={15} className="animate-spin" />
          ) : (
            <Trash size={15} weight="bold" />
          )}
          Eliminar
        </button>
      </div>
    </article>
  )
}
