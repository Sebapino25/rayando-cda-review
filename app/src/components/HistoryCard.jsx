import { useState } from 'react'
import { CheckCircle, Wrench, XCircle, NoteBlank, ArrowSquareOut, ArrowUUpLeft, SpinnerGap, CaretDown, DownloadSimple, Trash } from '@phosphor-icons/react'
import { downloadUrl } from '../lib/downloadUrl'

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

export default function HistoryCard({ clip, onUndo, onCoverRemove }) {
  const stateMeta = STATE_META[clip.estado] ?? STATE_META.rechazado
  const hasPendingComment = Boolean(clip.comentarios_video && clip.comentarios_video.trim())
  const [undoing, setUndoing] = useState(false)
  const [errorMsg, setErrorMsg] = useState('')
  const [expanded, setExpanded] = useState(false)
  const [removingCover, setRemovingCover] = useState(false)

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

  return (
    <article className="bg-surface rounded-2xl border border-border shadow-sm overflow-hidden">
      <details open={expanded} onToggle={(e) => setExpanded(e.target.open)}>
        <summary className="flex gap-3 p-4 cursor-pointer select-none list-none">
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
          <div className="aspect-video bg-black">
            <iframe
              className="w-full h-full"
              src={`https://www.youtube.com/embed/${clip.youtube_video_id}`}
              title={clip.youtube_titulo || 'Clip'}
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
              allowFullScreen
            />
          </div>
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
        </div>
      )}

      <div className="border-t border-border px-4 py-3 flex flex-col gap-2">
        {errorMsg && (
          <p className="text-sm text-destructive font-medium" role="alert">
            {errorMsg}
          </p>
        )}
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
      </div>
    </article>
  )
}
