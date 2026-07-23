import { useRef, useState } from 'react'
import {
  CaretDown,
  Check,
  DownloadSimple,
  FloppyDisk,
  Image as ImageIcon,
  Info,
  Trash,
  UploadSimple,
  Wrench,
  X,
  SpinnerGap,
} from '@phosphor-icons/react'
import { downloadUrl } from '../lib/downloadUrl'

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

export default function ClipCard({ clip, onSave, onApprove, onCorrection, onReject, onCoverUpload, onCoverRemove }) {
  const fileInputRef = useRef(null)
  const [coverUrl, setCoverUrl] = useState(clip.portada_url ?? '')
  const [uploadingCover, setUploadingCover] = useState(false)
  const [removingCover, setRemovingCover] = useState(false)
  const [coverError, setCoverError] = useState('')

  async function handleCoverFileChange(e) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    setUploadingCover(true)
    setCoverError('')
    try {
      const url = await onCoverUpload(clip.id, file)
      setCoverUrl(url)
    } catch (err) {
      setCoverError(err.message || 'No se pudo subir la portada. Probá de nuevo.')
    } finally {
      setUploadingCover(false)
    }
  }

  async function handleCoverRemoveClick() {
    if (!window.confirm('¿Quitar la portada actual? Vuelve a quedar en blanco hasta que alguien suba otra.')) return
    setRemovingCover(true)
    setCoverError('')
    try {
      await onCoverRemove(clip.id)
      setCoverUrl('')
    } catch (err) {
      setCoverError(err.message || 'No se pudo quitar la portada. Probá de nuevo.')
    } finally {
      setRemovingCover(false)
    }
  }

  const [fields, setFields] = useState({
    copy_instagram: clip.copy_instagram ?? '',
    copy_tiktok: clip.copy_tiktok ?? '',
    youtube_titulo: clip.youtube_titulo ?? '',
    youtube_descripcion: clip.youtube_descripcion ?? '',
    comentarios_video: clip.comentarios_video ?? '',
    transcripcion: clip.transcripcion ?? '',
  })
  const [transcriptOpen, setTranscriptOpen] = useState(false)
  const [rejecting, setRejecting] = useState(false)
  const [rejectNotes, setRejectNotes] = useState('')
  const [saving, setSaving] = useState(false)
  const [approving, setApproving] = useState(false)
  const [correcting, setCorrecting] = useState(false)
  const [rejectingBusy, setRejectingBusy] = useState(false)
  const [savedFlash, setSavedFlash] = useState(false)
  const [saveError, setSaveError] = useState('')
  const [actionError, setActionError] = useState('')
  const [correctionError, setCorrectionError] = useState(false)

  const busy = saving || approving || correcting || rejectingBusy

  function updateField(key, value) {
    setFields((prev) => ({ ...prev, [key]: value }))
    if (key === 'comentarios_video' && correctionError) setCorrectionError(false)
  }

  async function handleSave() {
    setSaving(true)
    setSaveError('')
    try {
      await onSave(clip.id, fields)
      setSavedFlash(true)
      setTimeout(() => setSavedFlash(false), 2000)
    } catch (err) {
      setSaveError(err.message || 'No se pudo guardar. Probá de nuevo.')
    } finally {
      setSaving(false)
    }
  }

  async function handleApprove() {
    setApproving(true)
    setActionError('')
    try {
      await onApprove(clip.id, fields)
    } catch (err) {
      setActionError(err.message || 'No se pudo aprobar. Probá de nuevo.')
      setApproving(false)
    }
  }

  async function handleCorrection() {
    if (!fields.comentarios_video || !fields.comentarios_video.trim()) {
      setCorrectionError(true)
      return
    }
    setCorrectionError(false)
    setCorrecting(true)
    setActionError('')
    try {
      await onCorrection(clip.id, fields)
    } catch (err) {
      setActionError(err.message || 'No se pudo marcar para corrección. Probá de nuevo.')
      setCorrecting(false)
    }
  }

  async function handleConfirmReject() {
    setRejectingBusy(true)
    setActionError('')
    try {
      await onReject(clip.id, fields, rejectNotes)
    } catch (err) {
      setActionError(err.message || 'No se pudo rechazar. Probá de nuevo.')
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
        <div className="flex items-center gap-3">
          <div className="shrink-0 w-16 aspect-[9/16] rounded-lg overflow-hidden bg-muted border border-border flex items-center justify-center">
            {coverUrl ? (
              <img src={coverUrl} alt="Portada" className="w-full h-full object-cover" />
            ) : (
              <ImageIcon size={20} className="text-muted-foreground" />
            )}
          </div>
          <div className="min-w-0 flex-1 flex flex-col gap-1">
            <span className="text-sm font-semibold text-foreground">Portada</span>
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploadingCover}
              className="w-fit flex items-center gap-1.5 text-sm font-semibold text-primary disabled:opacity-40 cursor-pointer"
            >
              {uploadingCover ? (
                <SpinnerGap size={16} className="animate-spin" />
              ) : (
                <UploadSimple size={16} weight="bold" />
              )}
              {coverUrl ? 'Reemplazar portada' : 'Subir portada propia'}
            </button>
            {coverUrl && (
              <a
                href={downloadUrl(coverUrl, `portada-${clip.id}.jpg`)}
                className="w-fit flex items-center gap-1.5 text-sm font-semibold text-muted-foreground cursor-pointer"
              >
                <DownloadSimple size={16} weight="bold" />
                Descargar portada
              </a>
            )}
            {coverUrl && (
              <button
                type="button"
                onClick={handleCoverRemoveClick}
                disabled={removingCover}
                className="w-fit flex items-center gap-1.5 text-sm font-semibold text-destructive disabled:opacity-40 cursor-pointer"
              >
                {removingCover ? (
                  <SpinnerGap size={16} className="animate-spin" />
                ) : (
                  <Trash size={16} weight="bold" />
                )}
                Quitar portada
              </button>
            )}
            <input
              ref={fileInputRef}
              type="file"
              accept="image/png,image/jpeg,image/webp"
              className="hidden"
              onChange={handleCoverFileChange}
            />
            {coverError && (
              <p className="text-xs text-destructive font-medium" role="alert">
                {coverError}
              </p>
            )}
          </div>
        </div>

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
          <div className="px-3.5 pb-3.5 flex flex-col gap-2">
            <textarea
              rows={4}
              value={fields.transcripcion}
              onChange={(e) => updateField('transcripcion', e.target.value)}
              className="w-full px-3.5 py-3 rounded-xl border border-border bg-background text-sm leading-relaxed text-foreground focus:outline-none focus:ring-2 focus:ring-ring resize-none"
            />
            <p className="flex items-start gap-1.5 text-xs text-warning">
              <Info size={14} className="shrink-0 mt-0.5" />
              Corregir acá no cambia el subtítulo del video ya generado — queda anotado para reprocesar.
            </p>
          </div>
        </details>

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

        {saveError && (
          <p className="text-sm text-destructive font-medium" role="alert">
            {saveError}
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
        <p className="text-xs text-muted-foreground -mt-2.5 text-center">
          Guarda tus ediciones de texto sin decidir todavía si se aprueba.
        </p>

        <div className="h-px bg-border" />

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
            Usá este campo solo si el video en sí (corte, formato, audio) necesita trabajo técnico. Si ya corregiste el copy o la transcripción arriba, no hace falta anotarlo acá — con "Guardar cambios" alcanza. Estos pedidos no se ejecutan automáticamente: quedan anotados para que se procesen a mano después.
          </p>
        </div>

        {actionError && (
          <p className="text-sm text-destructive font-medium" role="alert">
            {actionError}
          </p>
        )}

        {!rejecting ? (
          <div className="flex flex-col gap-3">
            <p className="text-xs font-semibold text-muted-foreground">¿Qué corresponde acá?</p>

            <div className="flex flex-col gap-1.5">
              <button
                type="button"
                onClick={handleApprove}
                disabled={busy}
                className="w-full h-14 rounded-xl bg-accent text-accent-foreground font-semibold text-[15px] flex items-center justify-center gap-2 disabled:opacity-40 active:scale-[0.98] transition-transform cursor-pointer"
              >
                {approving ? (
                  <SpinnerGap size={18} className="animate-spin" />
                ) : (
                  <Check size={20} weight="bold" />
                )}
                Aprobar
              </button>
              <p className="text-xs text-muted-foreground px-1">
                El video y el copy están listos, tal cual, para publicarse.
              </p>
            </div>

            <div className="flex flex-col gap-1.5">
              <button
                type="button"
                onClick={handleCorrection}
                disabled={busy}
                className="w-full h-14 rounded-xl bg-warning text-warning-foreground font-semibold text-[15px] flex items-center justify-center gap-2 disabled:opacity-40 active:scale-[0.98] transition-transform cursor-pointer"
              >
                {correcting ? (
                  <SpinnerGap size={18} className="animate-spin" />
                ) : (
                  <Wrench size={20} weight="bold" />
                )}
                Corrección técnica de video
              </button>
              <p className="text-xs text-muted-foreground px-1">
                Usalo solo si el corte, formato o audio del video en sí necesita trabajo técnico — no para avisar que ya corregiste el copy o la transcripción arriba (eso se guarda solo con "Guardar cambios").
              </p>
              {correctionError && (
                <p className="text-xs text-destructive font-medium px-1" role="alert">
                  Contá qué necesita el video en "Comentarios sobre el video" antes de continuar.
                </p>
              )}
            </div>

            <div className="flex flex-col gap-1.5">
              <button
                type="button"
                onClick={() => setRejecting(true)}
                disabled={busy}
                className="w-full h-14 rounded-xl bg-destructive text-destructive-foreground font-semibold text-[15px] flex items-center justify-center gap-2 disabled:opacity-40 active:scale-[0.98] transition-transform cursor-pointer"
              >
                <X size={20} weight="bold" />
                Rechazar
              </button>
              <p className="text-xs text-muted-foreground px-1">
                Este momento no se va a publicar.
              </p>
            </div>
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
