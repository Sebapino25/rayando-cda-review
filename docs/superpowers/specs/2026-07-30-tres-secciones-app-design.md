# Tres secciones en la app de revisión + eliminar publicaciones

Fecha: 2026-07-30
Estado: aprobado por el usuario, listo para plan de implementación

## Contexto

La app de revisión (`app/`) hoy tiene 2 pestañas: "Pendientes"
(`estado='pendiente'`) e "Historial" (`estado` en `aprobado` /
`correccion_video` / `rechazado`, todo mezclado, sin distinguir si ya se
publicó de verdad o no). No hay forma de borrar un clip rechazado ni uno
ya archivado — `HistoryCard.jsx` no tiene ningún botón de eliminar.

El usuario había discutido con anterioridad (en una conversación sin
registro accesible en este proyecto) agregar una tercera sección para
tener un historial real de lo publicado, más un botón de borrado. Este
spec reconstruye ese diseño desde cero, confirmado con el usuario en esta
sesión (no se asumió ningún detalle no confirmado).

## Objetivo

Separar "lo que todavía necesita acción" de "lo que ya es historia", y
poder limpiar registros que no sirven más (rechazados, o entradas viejas
del archivo) sin tener que hacerlo a mano en el dashboard de Supabase.

## Alcance

- 3 pestañas en vez de 2: **Pendientes** (sin cambios) → **Por publicar**
  → **Publicados**.
- Botón "Eliminar" en clips de "Por publicar" y "Publicados".

**Corrección tras releer el código real:** el borrado de `vertical.mp4` de
Storage al publicar (`publicado=true`) **ya está implementado** —
`supabase/functions/publicar-clip/index.ts:223-237` ya lo hace,
best-effort, en el mismo paso. No es un no-objetivo nuevo, es trabajo que
ya existía y no se había verificado al escribir la primera versión de
este spec. No hace falta ninguna tarea para esto.

## No-objetivos

- No se borra la portada al archivar (se mantiene, es liviana y útil de
  referencia).
- No se borra ni se intenta borrar el video de YouTube (no listado o
  público) — sigue siendo manual, igual que hoy.
- No se agrega un link directo al post real de Instagram (el
  `instagram_media_id` no alcanza para armar la URL pública sin una
  llamada extra a la API de Instagram) — queda para una mejora futura si
  hace falta.
- No se implementa "despublicar" (deshacer una publicación real) — el
  botón "Deshacer" que existe hoy (vuelve el clip a `pendiente`) no
  aplica a clips ya publicados.

## Diseño

### 1. Las 3 pestañas

- **Pendientes** (`estado='pendiente'`): sin cambios, es la cola de
  revisión de siempre.
- **Por publicar** (`estado` en `aprobado`/`correccion_video`/`rechazado`
  Y `publicado=false`): mismo contenido que el "Historial" de hoy, menos
  lo que ya se publicó (eso se mueve a la pestaña siguiente). Rechazados y
  clips en corrección de video pendiente aparecen acá mezclados con los
  aprobados, distinguidos por el badge de estado que ya existe
  (`STATE_META` en `HistoryCard.jsx`).
- **Publicados** (`publicado=true`): la sección nueva de respaldo. **Es un
  registro, no un reproductor**: el usuario piensa borrar el video real de
  YouTube una vez publicado, así que esta pestaña no puede depender de que
  siga existiendo. Mismo tipo de card que "Por publicar", pero sin la
  miniatura/link a YouTube ni el `<iframe>` embebido (ambos ocultos si
  `clip.publicado`), sin "Publicar en redes" (ya está publicado) ni
  "Deshacer" (no aplica a algo ya publicado de verdad) — queda: badge de
  estado, título, quién y cuándo revisó, la portada (se mantiene, es
  liviana), los copys/transcripción de solo lectura, "Quitar portada" y
  "Eliminar".

Query de cada pestaña (mismo patrón que `loadPending`/`loadHistory` hoy en
`App.jsx`):

```js
// Por publicar
supabase.from('clips').select('*')
  .in('estado', ['aprobado', 'correccion_video', 'rechazado'])
  .eq('publicado', false)
  .order('revisado_en', { ascending: false })

// Publicados
supabase.from('clips').select('*')
  .eq('publicado', true)
  .order('publicado_en', { ascending: false })
```

### 2. Botón "Eliminar"

Nuevo botón en `HistoryCard.jsx`, visible en "Por publicar" y
"Publicados" (no en "Pendientes"). Con confirmación (`window.confirm`,
mismo patrón que "Deshacer"/"Quitar portada"). Al confirmar:

1. Borra el archivo en `clips-video` si `video_url` existe (best-effort,
   mismo patrón que `handleReject`).
2. Borra el archivo en `portadas` si `portada_url` existe (best-effort,
   mismo patrón que `handleCoverRemove`).
3. Borra la fila de `rayando_cda.clips` (`supabase.from('clips').delete().eq('id', id)`).
4. Saca el clip de la lista en memoria (sin necesidad de recargar).

No toca YouTube. Si el clip ya está publicado en Instagram/YouTube
público, la publicación real en esas plataformas queda intacta — esto
solo borra el registro interno del sistema de revisión.

### 3. Errores

Mismo criterio que ya usa el resto de la app: el borrado de Storage es
best-effort (si falla, se ignora — un archivo huérfano ocasional no es
grave); el borrado de la fila de Supabase sí debe tener éxito para que la
UI la saque de la lista, y si falla se muestra el mismo tipo de mensaje
de error que ya usan "Deshacer"/"Quitar portada"/"Publicar en redes".

## Testing

No hay tests automatizados de la app hoy (React + Vite, sin suite de
tests configurada) — se verifica manualmente contra el clip fixture
`estado='prueba'` (ver protocolo en `app/README.md`), probando: que
aparece en la pestaña correcta según su `estado`/`publicado`, que
"Eliminar" borra fila + Storage y desaparece de la lista, y que
"Publicados" no muestra "Publicar en redes" ni "Deshacer".
