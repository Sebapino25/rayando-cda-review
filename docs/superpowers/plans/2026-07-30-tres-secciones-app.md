# Tres secciones en la app + eliminar publicaciones — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pasar la app de revisión de 2 pestañas (Pendientes/Historial mezclado) a 3 (Pendientes / Por publicar / Publicados), y agregar un botón "Eliminar" que borra un clip (fila + Storage) desde "Por publicar" y "Publicados".

**Architecture:** Solo frontend (`app/src/App.jsx` + `app/src/components/HistoryCard.jsx`). El borrado del video de Storage al publicar de verdad ya existe (`supabase/functions/publicar-clip/index.ts:223-237`) — no se toca. `HistoryCard.jsx` ya condiciona el botón "Publicar en redes" a `!clip.publicado`, así que en la pestaña "Publicados" (donde todos los clips tienen `publicado=true`) ese botón ya no se mostraría sin cambios — solo hace falta ocultar "Deshacer" del mismo modo y agregar el botón nuevo.

**Tech Stack:** React + Vite, Supabase JS client (postgres + storage), sin backend propio.

## Global Constraints

- El botón "Eliminar" nunca toca YouTube — solo borra la fila de `rayando_cda.clips` y los archivos en Supabase Storage (`clips-video`/`portadas`) si existen. Borrado best-effort de Storage (nunca bloquea si falla), borrado de la fila si debe tener éxito (si falla, error visible, no se saca de la lista).
- "Deshacer" no debe mostrarse para clips con `publicado=true` (no aplica a algo ya publicado de verdad).
- Cualquier prueba manual usa el clip fixture `estado='prueba'` de `rayando_cda.clips` (ver protocolo en `app/README.md`) — nunca un clip real.
- No se toca `supabase/functions/publicar-clip/index.ts` (el borrado de Storage al publicar ya existe ahí).

---

### Task 1: Tercera pestaña "Publicados" + filtro `publicado=false` en "Por publicar"

**Files:**
- Modify: `app/src/App.jsx`

**Interfaces:**
- Produces: estado nuevo `publishedClips` (array), función `loadPublished()` (mismo patrón que `loadHistory`), tab id `'publicados'` (nuevo, junto a los existentes `'pendientes'`/`'historial'`). `handleDelete(id)` nueva, usada por ambas pestañas de historial.

- [ ] **Step 1: Filtrar `loadHistory` por `publicado=false` (pasa a ser "Por publicar")**

En `app/src/App.jsx`, dentro de `loadHistory` (línea 43-57), agregar el filtro:

```js
const loadHistory = useCallback(async () => {
  setLoading(true)
  setError('')
  const { data, error: fetchError } = await supabase
    .from('clips')
    .select('*')
    .in('estado', ['aprobado', 'correccion_video', 'rechazado'])
    .eq('publicado', false)
    .order('revisado_en', { ascending: false })
  if (fetchError) {
    setError(fetchError.message)
  } else {
    setHistoryClips(data ?? [])
  }
  setLoading(false)
}, [])
```

- [ ] **Step 2: Agregar `loadPublished` y el estado `publishedClips`**

Después de la declaración de `historyClips`/`loadHistory` (cerca de la línea 23 y 43), agregar:

```js
const [publishedClips, setPublishedClips] = useState([])
```

Y después de `loadHistory` (después de la línea 57):

```js
const loadPublished = useCallback(async () => {
  setLoading(true)
  setError('')
  const { data, error: fetchError } = await supabase
    .from('clips')
    .select('*')
    .eq('publicado', true)
    .order('publicado_en', { ascending: false })
  if (fetchError) {
    setError(fetchError.message)
  } else {
    setPublishedClips(data ?? [])
  }
  setLoading(false)
}, [])
```

- [ ] **Step 3: Enganchar la carga de la pestaña nueva en el `useEffect`**

Reemplazar (línea 59-63):

```js
  useEffect(() => {
    if (!reviewer) return
    if (tab === 'pendientes') loadPending()
    else loadHistory()
  }, [reviewer, tab, loadPending, loadHistory])
```

por:

```js
  useEffect(() => {
    if (!reviewer) return
    if (tab === 'pendientes') loadPending()
    else if (tab === 'historial') loadHistory()
    else loadPublished()
  }, [reviewer, tab, loadPending, loadHistory, loadPublished])
```

- [ ] **Step 4: Agregar `handleDelete`**

Después de `handlePublicar` (después de la línea 221), agregar:

```js
  async function handleDelete(id) {
    const clip = historyClips.find((c) => c.id === id) || publishedClips.find((c) => c.id === id)

    if (clip?.video_url) {
      const marker = '/object/public/clips-video/'
      const idx = clip.video_url.indexOf(marker)
      if (idx !== -1) {
        const path = clip.video_url.slice(idx + marker.length)
        try {
          await supabase.storage.from('clips-video').remove([path])
        } catch {
          // Best-effort, igual que el borrado de video al rechazar/publicar:
          // un archivo huérfano ocasional no debe bloquear el borrado de la fila.
        }
      }
    }

    if (clip?.portada_url) {
      const marker = '/object/public/portadas/'
      const idx = clip.portada_url.indexOf(marker)
      if (idx !== -1) {
        const path = clip.portada_url.slice(idx + marker.length)
        try {
          await supabase.storage.from('portadas').remove([path])
        } catch {
          // no-op, mismo criterio que arriba
        }
      }
    }

    const { error: deleteError } = await supabase.from('clips').delete().eq('id', id)
    if (deleteError) throw deleteError

    setHistoryClips((prev) => prev.filter((c) => c.id !== id))
    setPublishedClips((prev) => prev.filter((c) => c.id !== id))
  }
```

- [ ] **Step 5: Tercer botón de navegación**

Reemplazar el `<nav>` (línea 261-291) para pasar de `grid-cols-2` a `grid-cols-3` y agregar el botón "Publicados":

```jsx
        <nav className="max-w-2xl mx-auto w-full px-4 pb-3 grid grid-cols-3 gap-2">
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
            Por publicar
          </button>
          <button
            type="button"
            onClick={() => setTab('publicados')}
            className={`h-11 rounded-xl text-sm font-semibold flex items-center justify-center gap-1.5 cursor-pointer transition-colors ${
              tab === 'publicados' ? 'bg-white text-primary' : 'bg-white/10 text-white/85'
            }`}
          >
            <CheckCircle size={17} weight="bold" />
            Publicados
          </button>
        </nav>
```

Esto usa el ícono `CheckCircle`, que hoy no está importado en este archivo (sí lo usa `HistoryCard.jsx`, pero cada archivo importa el suyo). Agregar `CheckCircle` al import de `@phosphor-icons/react` en la línea 2:

```js
import { ClockCounterClockwise, ListChecks, ArrowsClockwise, SpinnerGap, Question, CheckCircle } from '@phosphor-icons/react'
```

- [ ] **Step 6: Renderizar la pestaña nueva en `<main>`**

Después del bloque que renderiza `tab === 'historial'` (después de la línea 349, antes del `</main>` de la línea 350), agregar:

```jsx
        {!loading && !error && tab === 'publicados' && publishedClips.length === 0 && (
          <div className="text-center py-16">
            <p className="text-base font-semibold text-foreground">Todavía no hay nada publicado</p>
            <p className="text-sm text-muted-foreground mt-1">
              Los clips publicados de verdad van a aparecer acá.
            </p>
          </div>
        )}

        {!loading && !error && tab === 'publicados' &&
          publishedClips.map((clip) => (
            <HistoryCard
              key={clip.id}
              clip={clip}
              onUndo={handleUndo}
              onCoverRemove={handleCoverRemove}
              onPublicar={handlePublicar}
              onDelete={handleDelete}
            />
          ))}
```

Y agregar `onDelete={handleDelete}` a la instancia de `HistoryCard` que ya existe para `tab === 'historial'` (línea 348):

```jsx
            <HistoryCard key={clip.id} clip={clip} onUndo={handleUndo} onCoverRemove={handleCoverRemove} onPublicar={handlePublicar} onDelete={handleDelete} />
```

- [ ] **Step 7: Reintentar también debe recargar la pestaña correcta**

El botón "Reintentar" (línea 302-314) hoy hace `tab === 'pendientes' ? loadPending : loadHistory` — con 3 pestañas, `loadHistory` sería incorrecto para `tab === 'publicados'`. Reemplazar (línea 307):

```jsx
              onClick={tab === 'pendientes' ? loadPending : tab === 'historial' ? loadHistory : loadPublished}
```

- [ ] **Step 8: Mensaje vacío de "Por publicar" (antes decía "Historial")**

El mensaje de lista vacía (línea 337-344) sigue siendo válido para "Por publicar" tal cual está ("Los clips aprobados o rechazados van a aparecer acá") — no requiere cambio de contenido, pero confirmá al probar que el texto sigue teniendo sentido ahora que los publicados ya no aparecen ahí.

- [ ] **Step 9: Verificación manual con el fixture de QA**

No hay test automatizado de la app (React + Vite sin suite configurada — ver `app/README.md`). Verificar a mano:

1. `cd app && npm run dev`
2. Con el clip fixture (`estado='prueba'`), seguí el protocolo de `app/README.md`: ponelo en `estado='pendiente'` primero.
3. Confirmá que aparece en "Pendientes".
4. Apruébalo (o mandalo a "correccion_video"/"rechazado") — confirmá que aparece en "Por publicar" (no en "Publicados").
5. Si el fixture tiene `video_url`, probá "Publicar en redes" (con el PIN real) — confirmá que después de publicar aparece en "Publicados" y ya no en "Por publicar" (Task 2 agrega el botón "Eliminar" que también hay que probar ahí).
6. Volvé a dejar el fixture en `estado='prueba'` al terminar.

- [ ] **Step 10: Commit**

```bash
git add app/src/App.jsx
git commit -m "Agregar pestaña Publicados y filtrar Por publicar por publicado=false"
```

---

### Task 2: Botón "Eliminar" en `HistoryCard.jsx` + ocultar "Deshacer" en clips publicados

**Files:**
- Modify: `app/src/components/HistoryCard.jsx`

**Interfaces:**
- Consumes: `onDelete(id)` (prop nueva, de Task 1) — debe lanzar si falla, igual que `onUndo`/`onCoverRemove`/`onPublicar`.

- [ ] **Step 1: Agregar el ícono y el prop `onDelete`**

En `app/src/components/HistoryCard.jsx`, agregar `Trash` a los íconos ya importados en la línea 2 — **ya está importado** (`Trash` ya se usa para "Quitar portada"), así que no hace falta tocar el import.

Cambiar la firma del componente (línea 39):

```jsx
export default function HistoryCard({ clip, onUndo, onCoverRemove, onPublicar, onDelete }) {
```

- [ ] **Step 2: Estado y handler de borrado**

Después de `const [publicando, setPublicando] = useState(false)` (línea 46), agregar:

```js
  const [deleting, setDeleting] = useState(false)
```

Después de `handlePublicar` (después de la línea 98), agregar:

```js
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
```

(Mismo patrón que `handleUndo`/`handleCoverRemove`: si falla, se limpia `deleting` y se muestra el error; si tiene éxito, el componente deja de existir porque el padre ya sacó el clip de la lista, así que no hace falta un `finally` que reponga `deleting`.)

- [ ] **Step 3: Ocultar "Deshacer" para clips ya publicados, agregar "Eliminar"**

Reemplazar el bloque final de acciones (línea 249-261):

```jsx
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
```

por:

```jsx
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
```

(El botón "Publicar en redes" que está justo arriba de este bloque, línea 232-242, no necesita cambios: ya está condicionado a `clip.estado === 'aprobado' && !clip.publicado`, así que en la pestaña "Publicados" — donde todo clip tiene `publicado=true` — ya no se muestra.)

- [ ] **Step 4: Verificación manual**

Ya cubierta por el Step 9 de la Task 1 (usa el mismo fixture y el mismo flujo de prueba). Verificar puntualmente acá:
- En "Por publicar", un clip rechazado/en-corrección/aprobado muestra "Eliminar" y "Deshacer" juntos.
- En "Publicados", el mismo clip ya no muestra "Deshacer" (solo "Quitar portada" si tiene portada, y "Eliminar").
- Confirmar el mensaje de `window.confirm`, y que cancelarlo no borra nada.
- Confirmar que "Eliminar" saca el clip de la lista sin recargar la página.

- [ ] **Step 5: Commit**

```bash
git add app/src/components/HistoryCard.jsx
git commit -m "Agregar botón Eliminar y ocultar Deshacer en clips publicados"
```
