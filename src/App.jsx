import { useEffect, useState, useCallback } from 'react'
import { ClockCounterClockwise, ListChecks, ArrowsClockwise, SpinnerGap, Question } from '@phosphor-icons/react'
import { supabase } from './lib/supabaseClient'
import { ORDER_COLUMN } from './lib/constants'
import { getReviewerName, setReviewerName } from './lib/reviewer'
import ReviewerGate from './components/ReviewerGate'
import ClipCard from './components/ClipCard'
import HistoryCard from './components/HistoryCard'

const EDITABLE_FIELDS = [
  'copy_instagram',
  'copy_tiktok',
  'youtube_titulo',
  'youtube_descripcion',
  'comentarios_video',
]

function App() {
  const [reviewer, setReviewer] = useState(() => getReviewerName())
  const [tab, setTab] = useState('pendientes')
  const [pendingClips, setPendingClips] = useState([])
  const [historyClips, setHistoryClips] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const loadPending = useCallback(async () => {
    setLoading(true)
    setError('')
    const { data, error: fetchError } = await supabase
      .from('clips')
      .select('*')
      .eq('estado', 'pendiente')
      .order(ORDER_COLUMN, { ascending: false })
    if (fetchError) {
      setError(fetchError.message)
    } else {
      setPendingClips(data ?? [])
    }
    setLoading(false)
  }, [])

  const loadHistory = useCallback(async () => {
    setLoading(true)
    setError('')
    const { data, error: fetchError } = await supabase
      .from('clips')
      .select('*')
      .in('estado', ['aprobado', 'rechazado'])
      .order('revisado_en', { ascending: false })
    if (fetchError) {
      setError(fetchError.message)
    } else {
      setHistoryClips(data ?? [])
    }
    setLoading(false)
  }, [])

  useEffect(() => {
    if (!reviewer) return
    if (tab === 'pendientes') loadPending()
    else loadHistory()
  }, [reviewer, tab, loadPending, loadHistory])

  function handleReviewerSubmit(name) {
    setReviewerName(name)
    setReviewer(name)
  }

  function handleChangeReviewer() {
    const next = window.prompt('¿Quién va a revisar?', reviewer)
    if (next && next.trim()) {
      setReviewerName(next.trim())
      setReviewer(next.trim())
    }
  }

  async function handleSave(id, fields) {
    const payload = {}
    for (const key of EDITABLE_FIELDS) payload[key] = fields[key]
    const { error: updateError } = await supabase.from('clips').update(payload).eq('id', id)
    if (updateError) throw updateError
    setPendingClips((prev) => prev.map((c) => (c.id === id ? { ...c, ...payload } : c)))
  }

  async function handleApprove(id, fields) {
    const payload = {}
    for (const key of EDITABLE_FIELDS) payload[key] = fields[key]
    payload.estado = 'aprobado'
    payload.revisado_por = reviewer
    payload.revisado_en = new Date().toISOString()
    const { error: updateError } = await supabase.from('clips').update(payload).eq('id', id)
    if (updateError) throw updateError
    setPendingClips((prev) => prev.filter((c) => c.id !== id))
  }

  async function handleReject(id, fields, notasRevision) {
    const payload = {}
    for (const key of EDITABLE_FIELDS) payload[key] = fields[key]
    payload.estado = 'rechazado'
    payload.revisado_por = reviewer
    payload.revisado_en = new Date().toISOString()
    payload.notas_revision = notasRevision || null
    const { error: updateError } = await supabase.from('clips').update(payload).eq('id', id)
    if (updateError) throw updateError
    setPendingClips((prev) => prev.filter((c) => c.id !== id))
  }

  async function handleUndo(id) {
    const payload = {
      estado: 'pendiente',
      revisado_por: null,
      revisado_en: null,
      notas_revision: null,
    }
    const { error: updateError } = await supabase.from('clips').update(payload).eq('id', id)
    if (updateError) throw updateError
    setHistoryClips((prev) => prev.filter((c) => c.id !== id))
    loadPending()
  }

  if (!reviewer) {
    return <ReviewerGate onSubmit={handleReviewerSubmit} />
  }

  return (
    <div className="min-h-dvh flex flex-col">
      <header className="pt-safe sticky top-0 z-20 bg-primary text-primary-foreground shadow-md">
        <div className="max-w-2xl mx-auto w-full px-4 pt-4 pb-3 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2.5 min-w-0">
            <img
              src={`${import.meta.env.BASE_URL}logo.png`}
              alt=""
              className="w-9 h-9 shrink-0 rounded-xl object-cover"
            />
            <div className="min-w-0">
              <h1 className="text-[15px] font-bold leading-tight truncate">Rayando el CDA</h1>
              <p className="text-xs text-white/70 leading-tight">Cola de revisión</p>
            </div>
            <a
              href={`${import.meta.env.BASE_URL}guia.html`}
              target="_blank"
              rel="noreferrer"
              title="Cómo usar esto"
              className="shrink-0 w-8 h-8 rounded-full bg-white/10 hover:bg-white/15 flex items-center justify-center"
            >
              <Question size={16} weight="bold" />
            </a>
          </div>
          <button
            type="button"
            onClick={handleChangeReviewer}
            className="shrink-0 text-xs font-semibold bg-white/10 hover:bg-white/15 rounded-full px-3 py-2 cursor-pointer max-w-[9rem] truncate"
            title="Cambiar revisor"
          >
            {reviewer}
          </button>
        </div>

        <nav className="max-w-2xl mx-auto w-full px-4 pb-3 grid grid-cols-2 gap-2">
          <button
            type="button"
            onClick={() => setTab('pendientes')}
            className={`h-11 rounded-xl text-sm font-semibold flex items-center justify-center gap-1.5 cursor-pointer transition-colors ${
              tab === 'pendientes' ? 'bg-white text-primary' : 'bg-white/10 text-white/85'
            }`}
          >
            <ListChecks size={17} weight="bold" />
            Pendientes
            {pendingClips.length > 0 && (
              <span
                className={`ml-0.5 rounded-full text-[11px] font-bold px-1.5 min-w-[1.25rem] text-center ${
                  tab === 'pendientes' ? 'bg-primary text-white' : 'bg-white/20 text-white'
                }`}
              >
                {pendingClips.length}
              </span>
            )}
          </button>
          <button
            type="button"
            onClick={() => setTab('historial')}
            className={`h-11 rounded-xl text-sm font-semibold flex items-center justify-center gap-1.5 cursor-pointer transition-colors ${
              tab === 'historial' ? 'bg-white text-primary' : 'bg-white/10 text-white/85'
            }`}
          >
            <ClockCounterClockwise size={17} weight="bold" />
            Historial
          </button>
        </nav>
      </header>

      <main className="flex-1 max-w-2xl mx-auto w-full px-4 py-5 flex flex-col gap-4 pb-safe">
        {loading && (
          <div className="flex items-center justify-center gap-2 text-muted-foreground py-16">
            <SpinnerGap size={20} className="animate-spin" />
            Cargando...
          </div>
        )}

        {!loading && error && (
          <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-4 flex flex-col gap-3 items-start">
            <p className="text-sm text-destructive">{error}</p>
            <button
              type="button"
              onClick={tab === 'pendientes' ? loadPending : loadHistory}
              className="text-sm font-semibold text-primary flex items-center gap-1.5 cursor-pointer"
            >
              <ArrowsClockwise size={16} weight="bold" />
              Reintentar
            </button>
          </div>
        )}

        {!loading && !error && tab === 'pendientes' && pendingClips.length === 0 && (
          <div className="text-center py-16">
            <p className="text-base font-semibold text-foreground">No hay clips pendientes</p>
            <p className="text-sm text-muted-foreground mt-1">Todo revisado por ahora.</p>
          </div>
        )}

        {!loading && !error && tab === 'pendientes' &&
          pendingClips.map((clip) => (
            <ClipCard
              key={clip.id}
              clip={clip}
              onSave={handleSave}
              onApprove={handleApprove}
              onReject={handleReject}
            />
          ))}

        {!loading && !error && tab === 'historial' && historyClips.length === 0 && (
          <div className="text-center py-16">
            <p className="text-base font-semibold text-foreground">Todavía no hay historial</p>
            <p className="text-sm text-muted-foreground mt-1">
              Los clips aprobados o rechazados van a aparecer acá.
            </p>
          </div>
        )}

        {!loading && !error && tab === 'historial' &&
          historyClips.map((clip) => (
            <HistoryCard key={clip.id} clip={clip} onUndo={handleUndo} />
          ))}
      </main>
    </div>
  )
}

export default App
