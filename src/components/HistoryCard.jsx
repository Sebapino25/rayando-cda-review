import { useState } from 'react'
import { CheckCircle, Wrench, XCircle, NoteBlank, ArrowSquareOut, ArrowUUpLeft, SpinnerGap } from '@phosphor-icons/react'

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
  correccion_video: { label: 'Corrección de video', Icon: Wrench, className: 'bg-warning-bg text-warning' },
  rechazado: { label: 'Rechazado', Icon: XCircle, className: 'bg-destructive/10 text-destructive' },
}

export default function HistoryCard({ clip, onUndo }) {
  const stateMeta = STATE_META[clip.estado] ?? STATE_META.rechazado
  const hasPendingComment = Boolean(clip.comentarios_video && clip.comentarios_video.trim())
  const [undoing, setUndoing] = useState(false)
  const [errorMsg, setErrorMsg] = useState('')

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

  return (
    <article className="bg-surface rounded-2xl border border-border shadow-sm overflow-hidden">
      <div className="flex gap-3 p-4">
        <a
          href={`https://www.youtube.com/watch?v=${clip.youtube_video_id}`}
          target="_blank"
          rel="noreferrer"
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
      </div>

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
