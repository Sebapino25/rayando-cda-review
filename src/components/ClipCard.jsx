import { useState } from 'react'
import {
  CaretDown,
  Check,
  FloppyDisk,
  Info,
  X,
  SpinnerGap,
} from '@phosphor-icons/react'

const dateFormatter = new Intl.DateTimeFormat('es-AR', {
  day: '2-digit',
  month: '2-digit',
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

function Field({ label, value, onChange, multiline, rows = 3 }) {
  const Component = multiline ? 'textarea' : 'input'
  return (
    <label className="block">
      <span className="block text-sm font-semibold text-foreground mb-1.5">{label}</span>
      <Component
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value)}
        rows={multiline ? rows : undefined}
        className="w-full px-3.5 py-3 rounded-xl border border-border bg-background text-[15px] leading-snug text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring resize-none"
      />
    </label>
  )
}

export default function ClipCard({ clip, onSave, onApprove, onReject }) {
  const [fields, setFields] = useState({
    copy_instagram: clip.copy_instagram ?? '',
    copy_tiktok: clip.copy_tiktok ?? '',
    youtube_titulo: clip.youtube_titulo ?? '',
    youtube_descripcion: clip.youtube_descripcion ?? '',
    comentarios_video: clip.comentarios_video ?? '',
  })
  const [transcriptOpen, setTranscriptOpen] = useState(false)
  const [rejecting, setRejecting] = useState(false)
  const [rejectNotes, setRejectNotes] = useState('')
  const [saving, setSaving] = useState(false)
  const [approving, setApproving] = useState(false)
  const [rejectingBusy, setRejectingBusy] = useState(false)
  const [savedFlash, setSavedFlash] = useState(false)
  const [errorMsg, setErrorMsg] = useState('')

  const busy = saving || approving || rejectingBusy

  function updateField(key, value) {
    setFields((prev) => ({ ...prev, [key]: value }))
  }

  async function handleSave() {
    setSaving(true)
    setErrorMsg('')
    try {
      await onSave(clip.id, fields)
      setSavedFlash(true)
      setTimeout(() => setSavedFlash(false), 2000)
    } catch (err) {
      setErrorMsg(err.message || 'No se pudo guardar. Probá de nuevo.')
    } finally {
      setSaving(false)
    }
  }

  async function handleApprove() {
    setApproving(true)
    setErrorMsg('')
    try {
      await onApprove(clip.id, fields)
    } catch (err) {
      setErrorMsg(err.message || 'No se pudo aprobar. Probá de nuevo.')
      setApproving(false)
    }
  }

  async function handleConfirmReject() {
    setRejectingBusy(true)
    setErrorMsg('')
    try {
      await onReject(clip.id, fields, rejectNotes)
    } catch (err) {
      setErrorMsg(err.message || 'No se pudo rechazar. Probá de nuevo.')
      setRejectingBusy(false)
    }
  }

  return (
    <article className="bg-surface rounded-2xl border border-border shadow-sm overflow-hidden">
      <div className="aspect-video bg-black">
        <iframe
          className="w-full h-full"
          src={`https://www.youtube.com/embed/${clip.youtube_video_id}`}
          title={clip.youtube_titulo || 'Clip'}
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
          allowFullScreen
        />
      </div>

      <div className="p-4 sm:p-5 flex flex-col gap-4">
        {clip.created_at && (
          <p className="text-xs text-muted-foreground -mb-1">
            Elegido el {formatDate(clip.created_at)}
          </p>
        )}

        {clip.razon && (
          <div className="rounded-xl bg-muted px-3.5 py-3 text-[15px] leading-snug text-foreground">
            <span className="block text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1">
              Por qué se eligió este momento
            </span>
            {clip.razon}
          </div>
        )}

        {clip.transcripcion && (
          <details
            open={transcriptOpen}
            onToggle={(e) => setTranscriptOpen(e.target.open)}
            className="rounded-xl border border-border overflow-hidden"
          >
            <summary
              className="flex items-center justify-between gap-2 px-3.5 py-3 text-sm font-semibold text-foreground cursor-pointer select-none list-none"
            >
              Transcripción del fragmento
              <CaretDown
                size={18}
                className={`text-muted-foreground transition-transform ${transcriptOpen ? 'rotate-180' : ''}`}
              />
            </summary>
            <p className="px-3.5 pb-3.5 text-sm leading-relaxed text-muted-foreground whitespace-pre-wrap">
              {clip.transcripcion}
            </p>
          </details>
        )}

        <div className="flex flex-col gap-3.5">
          <Field
            label="Copy Instagram"
            value={fields.copy_instagram}
            onChange={(v) => updateField('copy_instagram', v)}
            multiline
          />
          <Field
            label="Copy TikTok"
            value={fields.copy_tiktok}
            onChange={(v) => updateField('copy_tiktok', v)}
            multiline
          />
          <Field
            label="Título de YouTube"
            value={fields.youtube_titulo}
            onChange={(v) => updateField('youtube_titulo', v)}
          />
          <Field
            label="Descripción de YouTube"
            value={fields.youtube_descripcion}
            onChange={(v) => updateField('youtube_descripcion', v)}
            multiline
          />
        </div>

        <div className="rounded-xl border border-warning-bg bg-warning-bg/60 px-3.5 py-3">
          <label className="block">
            <span className="flex items-start gap-1.5 text-sm font-semibold text-foreground mb-1.5">
              Comentarios sobre el video (opcional)
            </span>
            <textarea
              rows={2}
              value={fields.comentarios_video}
              onChange={(e) => updateField('comentarios_video', e.target.value)}
              placeholder='Ej: "extender 5 segundos al final", "agregar el logo de tal marca"'
              className="w-full px-3.5 py-3 rounded-xl border border-border bg-surface text-[15px] leading-snug text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring resize-none"
            />
          </label>
          <p className="flex items-start gap-1.5 text-xs text-warning mt-2">
            <Info size={15} className="shrink-0 mt-0.5" />
            Estos pedidos no se ejecutan automáticamente: quedan anotados para que se procesen a mano después.
          </p>
        </div>

        {errorMsg && (
          <p className="text-sm text-destructive font-medium" role="alert">
            {errorMsg}
          </p>
        )}

        {savedFlash && (
          <p className="flex items-center gap-1.5 text-sm text-accent font-medium">
            <Check size={16} weight="bold" /> Cambios guardados
          </p>
        )}

        <button
          type="button"
          onClick={handleSave}
          disabled={busy}
          className="w-full min-h-[3.25rem] rounded-xl border-2 border-primary text-primary font-semibold text-[15px] flex items-center justify-center gap-2 disabled:opacity-40 active:scale-[0.98] transition-transform cursor-pointer"
        >
          {saving ? (
            <SpinnerGap size={18} className="animate-spin" />
          ) : (
            <FloppyDisk size={18} weight="bold" />
          )}
          Guardar cambios
        </button>

        {!rejecting ? (
          <div className="grid grid-cols-2 gap-3">
            <button
              type="button"
              onClick={handleApprove}
              disabled={busy}
              className="h-14 rounded-xl bg-accent text-accent-foreground font-semibold text-[15px] flex items-center justify-center gap-2 disabled:opacity-40 active:scale-[0.98] transition-transform cursor-pointer"
            >
              {approving ? (
                <SpinnerGap size={18} className="animate-spin" />
              ) : (
                <Check size={20} weight="bold" />
              )}
              Aprobar
            </button>
            <button
              type="button"
              onClick={() => setRejecting(true)}
              disabled={busy}
              className="h-14 rounded-xl bg-destructive text-destructive-foreground font-semibold text-[15px] flex items-center justify-center gap-2 disabled:opacity-40 active:scale-[0.98] transition-transform cursor-pointer"
            >
              <X size={20} weight="bold" />
              Rechazar
            </button>
          </div>
        ) : (
          <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-3.5 flex flex-col gap-3">
            <label className="block">
              <span className="block text-sm font-semibold text-foreground mb-1.5">
                Notas de por qué se rechaza (opcional)
              </span>
              <textarea
                rows={2}
                autoFocus
                value={rejectNotes}
                onChange={(e) => setRejectNotes(e.target.value)}
                className="w-full px-3.5 py-3 rounded-xl border border-border bg-surface text-[15px] leading-snug text-foreground focus:outline-none focus:ring-2 focus:ring-ring resize-none"
              />
            </label>
            <div className="grid grid-cols-2 gap-3">
              <button
                type="button"
                onClick={() => {
                  setRejecting(false)
                  setRejectNotes('')
                }}
                disabled={busy}
                className="h-14 rounded-xl border-2 border-border text-foreground font-semibold text-[15px] disabled:opacity-40 active:scale-[0.98] transition-transform cursor-pointer"
              >
                Cancelar
              </button>
              <button
                type="button"
                onClick={handleConfirmReject}
                disabled={busy}
                className="h-14 rounded-xl bg-destructive text-destructive-foreground font-semibold text-[15px] flex items-center justify-center gap-2 disabled:opacity-40 active:scale-[0.98] transition-transform cursor-pointer"
              >
                {rejectingBusy ? (
                  <SpinnerGap size={18} className="animate-spin" />
                ) : (
                  <X size={18} weight="bold" />
                )}
                Confirmar rechazo
              </button>
            </div>
          </div>
        )}
      </div>
    </article>
  )
}
