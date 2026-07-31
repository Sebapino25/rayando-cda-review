# Media kit vivo (subsistema 4, parte A) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Una página web con marca propia (`mediakit/`) que muestra en vivo los números de Instagram, TikTok y YouTube de Rayando el CDA (vía Windsor.ai), con narrativa que responde directo a las objeciones "pocos seguidores" y "muy de nicho", y un botón para exportarla a PDF.

**Architecture:** Una Edge Function nueva (`actualizar-stats-mediakit`) corre una vez al día vía `pg_cron`, trae datos de los 3 connectors ya conectados en Windsor.ai (`instagram`, `tiktok_organic`, `youtube`) y los guarda en una tabla nueva de una sola fila (`rayando_cda.media_kit_stats`, mismo patrón que `instagram_token`). Una página estática sin build tool (`mediakit/public/`) lee esa tabla vía la API REST de Supabase (anon key, solo lectura) y se despliega junto a `app/` en el mismo GitHub Pages.

**Tech Stack:** Deno/TypeScript (Edge Function, mismo runtime que el resto de `supabase/functions/`), HTML/CSS/JS plano sin build (frontend), Supabase (Postgres + `pg_cron`/`pg_net` + Edge Functions), Windsor.ai (fuente de datos de las 3 plataformas).

## Corrección post-Task-3 (bug real encontrado en producción)

Verificando en vivo tras el deploy de la Task 3, `ig_vistas_30d` guardó
133.408 — muy por debajo de lo que muestra el panel real de Instagram
(2.496.214 en 30 días, confirmado por el usuario mirando Instagram
Insights directo). Causa raíz, confirmada probando la API real de
Windsor.ai a mano: `fetchWindsorConnector('instagram', ['views',
'reach_1d', 'total_interactions'], 'last_30d', ...)` mezclaba en una sola
consulta campos de dos "tablas" internas distintas de Windsor.ai
(`views`/`total_interactions` viven en `user_insights_day_total_value`,
`reach_1d` vive en `user_insights_day`) — eso rompe el auto-agregado de
Windsor.ai y en vez de devolver una fila con el total del período,
devuelve 31 filas (una por día, más una fila suelta solo con
`reach_1d`), y el código tomaba `data[0]`, que resultó ser el día más
antiguo del rango, no el total.

**Fix verificado a mano contra la API real** (ver Task 2 actualizada
abajo): separar `reach_1d` en su propia consulta arregla el
auto-agregado — `views`+`total_interactions` juntos SÍ vienen bien
agregados en una sola fila cuando no se mezcla con `reach_1d`. De paso se
encontró que TikTok usaba el campo equivocado (`video_views_count`, a
nivel de video individual, devolvía 2.183) en vez de `video_views` (a
nivel de cuenta, devuelve 74.822 — coincide con lo que el usuario ve en
TikTok Studio). YouTube no tenía este problema (ya devolvía el valor
correcto, aunque de forma un poco rara — 56 filas idénticas en vez de
una sola, sin afectar el resultado).

Las Tasks 2 y 3 originales de abajo quedan como registro histórico de lo
que se construyó primero; el contenido real a implementar es el de esta
sección de corrección, que reemplaza el cuerpo de `fetchInstagramStats`/
`fetchTiktokStats` en `windsor.ts`.

### `fetchInstagramStats` corregido

```typescript
export async function fetchInstagramStats(apiKey: string, fetchImpl: typeof fetch = fetch): Promise<InstagramStats> {
  const [seguidoresFila, vistasFila, interaccionesFila, alcanceFila] = await Promise.all([
    fetchWindsorConnector('instagram', ['followers_count'], null, apiKey, fetchImpl),
    fetchWindsorConnector('instagram', ['views'], 'last_30d', apiKey, fetchImpl),
    fetchWindsorConnector('instagram', ['total_interactions'], 'last_90d', apiKey, fetchImpl),
    fetchWindsorConnector('instagram', ['reach_1d'], 'last_90d', apiKey, fetchImpl),
  ])
  return {
    seguidores: Number(seguidoresFila.followers_count),
    vistas30d: Number(vistasFila.views),
    alcance90d: Number(alcanceFila.reach_1d),
    interacciones90d: Number(interaccionesFila.total_interactions),
  }
}
```

(4 llamadas en vez de 2: `views` es de 30 días, `total_interactions` y
`reach_1d` son de 90 días — mismos períodos que ya usaba el media kit
estático — y cada una va sola porque combinarlas con una tabla distinta
rompe el agregado, como se explicó arriba.)

### `fetchTiktokStats` corregido

```typescript
export async function fetchTiktokStats(apiKey: string, fetchImpl: typeof fetch = fetch): Promise<TiktokStats> {
  const fila = await fetchWindsorConnector(
    'tiktok_organic',
    ['total_followers_count', 'total_likes', 'video_views'],
    'last_30d',
    apiKey,
    fetchImpl,
  )
  return {
    seguidores: Number(fila.total_followers_count),
    likes: Number(fila.total_likes),
    videoTopVistas: Number(fila.video_views),
  }
}
```

(Cambia `video_views_count` → `video_views`, y pasa a representar
"vistas de video de la cuenta en 30 días" en vez de "vistas del video
más visto" — ese segundo dato requeriría una consulta separada a nivel
de video individual que no vale la pena para este proyecto. El campo
`TiktokStats.videoTopVistas` y el id HTML `#stat-tiktok-video-top` se
mantienen sin cambio de nombre para no tocar más archivos de los
necesarios, pero la Task 5 más abajo debe rotular el texto como "Vistas
de video (30 días)", no "Video más visto".)

`fetchYoutubeStats` necesita un cambio también, descubierto al armar la
cifra hero combinada (ver más abajo): combinar `subscriber_count`/
`view_count` (tabla `Data - Channel`) con `views` con `date_preset`
(tabla `Video`) tiene el mismo problema de mezcla de tablas — probado a
mano, la combinación devuelve filas rotas, pero `views` sola con
`date_preset='last_30d'` da un valor limpio (24.896, coincide con lo que
el usuario ve en YouTube Studio: ~25,5k). Se agrega como campo nuevo
`vistas30d`, en una llamada separada:

```typescript
export interface YoutubeStats {
  suscriptores: number
  vistasHistoricas: number
  vistas30d: number
}

export async function fetchYoutubeStats(apiKey: string, fetchImpl: typeof fetch = fetch): Promise<YoutubeStats> {
  const [canalFila, vistas30dFila] = await Promise.all([
    fetchWindsorConnector('youtube', ['subscriber_count', 'view_count'], null, apiKey, fetchImpl),
    fetchWindsorConnector('youtube', ['views'], 'last_30d', apiKey, fetchImpl),
  ])
  return {
    suscriptores: Number(canalFila.subscriber_count),
    vistasHistoricas: Number(canalFila.view_count),
    vistas30d: Number(vistas30dFila.views),
  }
}
```

### Cambios que esto arrastra en el resto del plan

- **Task 1 (tabla, ya completada)**: agregar una columna nueva,
  `yt_vistas_30d numeric`, vía `alter table rayando_cda.media_kit_stats
  add column if not exists yt_vistas_30d numeric;` (idempotente, se puede
  correr contra la tabla ya creada sin romper nada).
- **Task 3 (Edge Function, ya completada)**: el bloque de YouTube en
  `index.ts` pasa a incluir `yt_vistas_30d: yt.vistas30d,` junto a los
  campos que ya guardaba, y hay que volver a desplegar la función con el
  `windsor.ts` corregido.
- **Task 5/Task 6 (página, todavía no implementadas)**: la cifra hero se
  arma sumando las 3 plataformas: `ig_vistas_30d + tiktok_video_top_vistas
  + yt_vistas_30d` (con esta corrección, TikTok ya guarda vistas de video
  de 30 días a nivel de cuenta, no el video más visto — ver más arriba).
  El label del hero ya se actualizó a "visualizaciones mensuales —
  Instagram + TikTok + YouTube, número en vivo" y en `app.js` el cálculo
  pasa a ser:
  ```javascript
  const heroTotal = (stats.ig_vistas_30d ?? 0) + (stats.tiktok_video_top_vistas ?? 0) + (stats.yt_vistas_30d ?? 0)
  setText('stat-hero-vistas', fmt.format(heroTotal))
  ```

## Global Constraints

- La API key de Windsor.ai ya está cargada como secreto `WINDSOR_API_KEY` en el proyecto de Supabase (confirmado por el usuario) — nunca se escribe en código ni en git.
- Cada plataforma (Instagram/TikTok/YouTube) se trae de forma independiente: si una falla, las otras dos igual se guardan. Nunca todo-o-nada.
- La página nunca debe verse rota o vacía frente a una marca: si `media_kit_stats` no tiene fila, usa valores por defecto embebidos en el HTML (los números actuales del media kit estático).
- No se toca el pitch deck ni el PDF/PPTX actuales — siguen existiendo tal cual.
- No se cambian precios ni planes de auspicio en esta pieza.
- Paleta de marca (hex, ya validada en el media kit/pitch deck existentes): navy `#0A2A6B`, navy oscuro `#071A45`, azul eléctrico `#2E6BE0`, rojo `#D2232A`, dorado `#F2B807`, papel `#EDE9DC`, tinta `#14161C`.

---

### Task 1: Tabla `rayando_cda.media_kit_stats`

**Files:**
- Create: `mediakit/supabase_migration_media_kit_stats.sql`

**Interfaces:**
- Produces: tabla `rayando_cda.media_kit_stats` con fila única (`id boolean primary key default true`, mismo patrón que `instagram_token`), columnas de datos por plataforma más un timestamp de éxito **por plataforma** (no uno solo compartido — así la Edge Function puede saber cuál de las 3 lleva más de 3 días sin actualizarse, que es lo que pide el manejo de errores de la spec).

- [ ] **Step 1: Escribir la migración**

Crear `mediakit/supabase_migration_media_kit_stats.sql`:

```sql
-- Rayando el CDA: tabla de una fila con los números en vivo del media kit
-- (Instagram, TikTok, YouTube vía Windsor.ai). Correr en el SQL Editor de
-- Supabase. Idempotente: se puede correr de nuevo sin romper nada.

create table if not exists rayando_cda.media_kit_stats (
    id boolean primary key default true,
    -- Instagram
    ig_seguidores numeric,
    ig_vistas_30d numeric,
    ig_alcance_90d numeric,
    ig_interacciones_90d numeric,
    ig_actualizado_en timestamptz,
    -- TikTok
    tiktok_seguidores numeric,
    tiktok_likes numeric,
    tiktok_video_top_vistas numeric,
    tiktok_actualizado_en timestamptz,
    -- YouTube
    yt_suscriptores numeric,
    yt_vistas_historicas numeric,
    yt_actualizado_en timestamptz,
    -- Manual (no es una métrica de ninguna API)
    programas_emitidos integer,
    constraint media_kit_stats_fila_unica check (id)
);

grant all on table rayando_cda.media_kit_stats to service_role;
grant select on table rayando_cda.media_kit_stats to anon;

alter table rayando_cda.media_kit_stats enable row level security;

drop policy if exists media_kit_stats_anon_select on rayando_cda.media_kit_stats;
create policy media_kit_stats_anon_select on rayando_cda.media_kit_stats
    for select
    to anon
    using (true);
-- Sin policy de insert/update/delete para anon a propósito: la página del
-- media kit es de solo lectura, únicamente la Edge Function (service_role,
-- que hace bypass de RLS) escribe acá. programas_emitidos se edita a mano
-- por el usuario directo en Supabase Studio (usa la conexión de owner del
-- proyecto, no la anon key, así que RLS no lo bloquea).

-- Fila inicial con los números actuales del media kit estático (07/2026),
-- para que la página nunca arranque vacía antes de la primera corrida del
-- cron. La Edge Function los sobreescribe con datos reales en su primera
-- corrida.
insert into rayando_cda.media_kit_stats (
    id, ig_seguidores, ig_vistas_30d, ig_alcance_90d, ig_interacciones_90d,
    tiktok_seguidores, tiktok_likes, tiktok_video_top_vistas,
    yt_suscriptores, yt_vistas_historicas, programas_emitidos
) values (
    true, 13516, 3000000, 548000, 586000,
    4455, 101000, 232000,
    null, 1400000, 70
) on conflict (id) do nothing;
```

- [ ] **Step 2: Correr la migración**

Ejecutar el contenido de `mediakit/supabase_migration_media_kit_stats.sql` en el SQL Editor de Supabase del proyecto `qfxfwfcdgqcbmdspjvtk`.

Run (verificación): `select * from rayando_cda.media_kit_stats;`
Expected: una fila con `id = true` y los valores por defecto de arriba.

- [ ] **Step 3: Commit**

```bash
git add mediakit/supabase_migration_media_kit_stats.sql
git commit -m "Agregar tabla rayando_cda.media_kit_stats para el media kit vivo"
```

---

### Task 2: Cliente de Windsor.ai (`windsor.ts`)

**Files:**
- Create: `supabase/functions/actualizar-stats-mediakit/windsor.ts`
- Create: `supabase/functions/actualizar-stats-mediakit/windsor_test.ts`

**Interfaces:**
- Produces:
  - `WindsorError` (clase de excepción)
  - `fetchWindsorConnector(connector: string, fields: string[], datePreset: string | null, apiKey: string, fetchImpl?: typeof fetch): Promise<Record<string, unknown>>` — llama a `https://connectors.windsor.ai/{connector}`, devuelve la primera fila de `data` (siempre viene como un array de una fila para estos queries de cuenta completa). Lanza `WindsorError` si la respuesta no es 200 o no tiene `data`.
  - `fetchInstagramStats(apiKey, fetchImpl?): Promise<{seguidores: number, vistas30d: number, alcance90d: number, interacciones90d: number}>`
  - `fetchTiktokStats(apiKey, fetchImpl?): Promise<{seguidores: number, likes: number, videoTopVistas: number}>`
  - `fetchYoutubeStats(apiKey, fetchImpl?): Promise<{suscriptores: number, vistasHistoricas: number}>`

- [ ] **Step 1: Escribir el test (falla porque el módulo no existe)**

Crear `supabase/functions/actualizar-stats-mediakit/windsor_test.ts`:

```typescript
import { assertEquals, assertRejects, assertStringIncludes } from 'https://deno.land/std@0.224.0/assert/mod.ts'
import {
  fetchWindsorConnector,
  fetchInstagramStats,
  fetchTiktokStats,
  fetchYoutubeStats,
  WindsorError,
} from './windsor.ts'

function fakeFetchOk(body: unknown) {
  return async (url: string | URL) => {
    return new Response(JSON.stringify(body), { status: 200 })
  }
}

Deno.test('fetchWindsorConnector arma la URL con connector, fields y api_key', async () => {
  let urlCapturada: string | undefined
  const fakeFetch = async (url: string | URL) => {
    urlCapturada = url.toString()
    return new Response(JSON.stringify({ data: [{ followers_count: 100 }] }), { status: 200 })
  }
  await fetchWindsorConnector('instagram', ['followers_count'], null, 'mi-api-key', fakeFetch as typeof fetch)
  assertStringIncludes(urlCapturada!, 'connectors.windsor.ai/instagram')
  assertStringIncludes(urlCapturada!, 'api_key=mi-api-key')
  assertStringIncludes(urlCapturada!, 'fields=followers_count')
})

Deno.test('fetchWindsorConnector agrega date_preset cuando se pasa', async () => {
  let urlCapturada: string | undefined
  const fakeFetch = async (url: string | URL) => {
    urlCapturada = url.toString()
    return new Response(JSON.stringify({ data: [{ views: 1 }] }), { status: 200 })
  }
  await fetchWindsorConnector('instagram', ['views'], 'last_30d', 'k', fakeFetch as typeof fetch)
  assertStringIncludes(urlCapturada!, 'date_preset=last_30d')
})

Deno.test('fetchWindsorConnector lanza WindsorError si la respuesta no es 200', async () => {
  const fakeFetch = async () => new Response('unauthorized', { status: 401 })
  await assertRejects(
    () => fetchWindsorConnector('instagram', ['followers_count'], null, 'k', fakeFetch as typeof fetch),
    WindsorError,
  )
})

Deno.test('fetchWindsorConnector lanza WindsorError si data viene vacío', async () => {
  const fakeFetch = fakeFetchOk({ data: [] })
  await assertRejects(
    () => fetchWindsorConnector('instagram', ['followers_count'], null, 'k', fakeFetch as typeof fetch),
    WindsorError,
  )
})

Deno.test('fetchInstagramStats mapea los campos correctos', async () => {
  const fakeFetch = fakeFetchOk({
    data: [{ followers_count: 13677, views: 3200000, reach_1d: 560000, total_interactions: 590000 }],
  })
  const stats = await fetchInstagramStats('k', fakeFetch as typeof fetch)
  assertEquals(stats, { seguidores: 13677, vistas30d: 3200000, alcance90d: 560000, interacciones90d: 590000 })
})

Deno.test('fetchTiktokStats mapea los campos correctos', async () => {
  const fakeFetch = fakeFetchOk({
    data: [{ total_followers_count: 4600, total_likes: 105000, video_views_count: 240000 }],
  })
  const stats = await fetchTiktokStats('k', fakeFetch as typeof fetch)
  assertEquals(stats, { seguidores: 4600, likes: 105000, videoTopVistas: 240000 })
})

Deno.test('fetchYoutubeStats mapea los campos correctos', async () => {
  const fakeFetch = fakeFetchOk({ data: [{ subscriber_count: 210, view_count: 1450000 }] })
  const stats = await fetchYoutubeStats('k', fakeFetch as typeof fetch)
  assertEquals(stats, { suscriptores: 210, vistasHistoricas: 1450000 })
})
```

- [ ] **Step 2: Correr el test y confirmar que falla**

Run: `cd supabase/functions/actualizar-stats-mediakit && deno test windsor_test.ts`
Expected: `error: Module not found "./windsor.ts"`

- [ ] **Step 3: Implementar `windsor.ts`**

```typescript
// Cliente de la API de Windsor.ai (https://connectors.windsor.ai) — trae
// los números de Instagram, TikTok y YouTube de Rayando el CDA desde los
// 3 connectors ya conectados en la cuenta de Windsor.ai del usuario
// (nombres exactos: "instagram", "tiktok_organic", "youtube").
//
// Cada connector se llama por separado y falla por separado — si uno cae,
// los otros dos igual deben poder guardarse (ver index.ts).

const WINDSOR_BASE = 'https://connectors.windsor.ai'

export class WindsorError extends Error {}

export async function fetchWindsorConnector(
  connector: string,
  fields: string[],
  datePreset: string | null,
  apiKey: string,
  fetchImpl: typeof fetch = fetch,
): Promise<Record<string, unknown>> {
  const params = new URLSearchParams({ api_key: apiKey, fields: fields.join(',') })
  if (datePreset) params.set('date_preset', datePreset)
  const url = `${WINDSOR_BASE}/${connector}?${params.toString()}`

  const resp = await fetchImpl(url)
  if (!resp.ok) {
    throw new WindsorError(`Windsor.ai (${connector}) devolvió ${resp.status}: ${await resp.text()}`)
  }
  const body = await resp.json()
  const fila = body?.data?.[0]
  if (!fila) {
    throw new WindsorError(`Windsor.ai (${connector}) no devolvió datos (respuesta: ${JSON.stringify(body)})`)
  }
  return fila
}

export interface InstagramStats {
  seguidores: number
  vistas30d: number
  alcance90d: number
  interacciones90d: number
}

export async function fetchInstagramStats(apiKey: string, fetchImpl: typeof fetch = fetch): Promise<InstagramStats> {
  const [seguidoresFila, vistasFila] = await Promise.all([
    fetchWindsorConnector('instagram', ['followers_count'], null, apiKey, fetchImpl),
    fetchWindsorConnector(
      'instagram',
      ['views', 'reach_1d', 'total_interactions'],
      'last_30d',
      apiKey,
      fetchImpl,
    ),
  ])
  return {
    seguidores: Number(seguidoresFila.followers_count),
    vistas30d: Number(vistasFila.views),
    alcance90d: Number(vistasFila.reach_1d),
    interacciones90d: Number(vistasFila.total_interactions),
  }
}

export interface TiktokStats {
  seguidores: number
  likes: number
  videoTopVistas: number
}

export async function fetchTiktokStats(apiKey: string, fetchImpl: typeof fetch = fetch): Promise<TiktokStats> {
  const fila = await fetchWindsorConnector(
    'tiktok_organic',
    ['total_followers_count', 'total_likes', 'video_views_count'],
    null,
    apiKey,
    fetchImpl,
  )
  return {
    seguidores: Number(fila.total_followers_count),
    likes: Number(fila.total_likes),
    videoTopVistas: Number(fila.video_views_count),
  }
}

export interface YoutubeStats {
  suscriptores: number
  vistasHistoricas: number
}

export async function fetchYoutubeStats(apiKey: string, fetchImpl: typeof fetch = fetch): Promise<YoutubeStats> {
  const fila = await fetchWindsorConnector(
    'youtube',
    ['subscriber_count', 'view_count'],
    null,
    apiKey,
    fetchImpl,
  )
  return {
    suscriptores: Number(fila.subscriber_count),
    vistasHistoricas: Number(fila.view_count),
  }
}
```

Nota sobre `fetchInstagramStats`: pide `followers_count` sin `date_preset`
(es un valor "hoy", como documenta el field de Windsor.ai) separado de
`views`/`reach_1d`/`total_interactions` con `date_preset=last_30d` — mezclar
un campo sin ventana de tiempo con campos que sí la tienen en la misma
consulta puede agregar mal los resultados, así que van en dos llamadas.

- [ ] **Step 4: Correr el test y confirmar que pasa**

Run: `cd supabase/functions/actualizar-stats-mediakit && deno test windsor_test.ts`
Expected: 7 tests, todos `ok`.

- [ ] **Step 5: Commit**

```bash
git add supabase/functions/actualizar-stats-mediakit/windsor.ts supabase/functions/actualizar-stats-mediakit/windsor_test.ts
git commit -m "Agregar cliente de Windsor.ai para el media kit vivo"
```

---

### Task 3: Edge Function orquestadora (`actualizar-stats-mediakit`)

**Files:**
- Create: `supabase/functions/actualizar-stats-mediakit/index.ts`

**Interfaces:**
- Consumes: `windsor.ts` (Task 2), `_shared/supabaseAdmin.ts::getSupabaseAdmin()`, `_shared/email.ts::enviarAlerta()`.
- Produces: endpoint HTTP de la Edge Function (invocado por el cron en la Task 4).

- [ ] **Step 1: Implementar `index.ts`**

```typescript
import { getSupabaseAdmin } from '../_shared/supabaseAdmin.ts'
import { enviarAlerta } from '../_shared/email.ts'
import { fetchInstagramStats, fetchTiktokStats, fetchYoutubeStats, WindsorError } from './windsor.ts'

const DIAS_ANTES_DE_ALERTAR = 3

Deno.serve(async (_req: Request) => {
  const apiKey = Deno.env.get('WINDSOR_API_KEY')
  if (!apiKey) {
    await enviarAlerta(
      'Rayando el CDA: falta WINDSOR_API_KEY',
      'La Edge Function actualizar-stats-mediakit no tiene el secreto WINDSOR_API_KEY configurado. Cargarlo en Project Settings > Edge Functions > Secrets.',
    )
    return new Response(JSON.stringify({ error: 'Falta WINDSOR_API_KEY' }), { status: 500 })
  }

  const supabase = getSupabaseAdmin()
  const ahora = new Date().toISOString()
  const actualizacion: Record<string, unknown> = {}
  const fallas: string[] = []

  try {
    const ig = await fetchInstagramStats(apiKey)
    Object.assign(actualizacion, {
      ig_seguidores: ig.seguidores,
      ig_vistas_30d: ig.vistas30d,
      ig_alcance_90d: ig.alcance90d,
      ig_interacciones_90d: ig.interacciones90d,
      ig_actualizado_en: ahora,
    })
  } catch (e) {
    fallas.push(`Instagram: ${e instanceof WindsorError ? e.message : String(e)}`)
  }

  try {
    const tiktok = await fetchTiktokStats(apiKey)
    Object.assign(actualizacion, {
      tiktok_seguidores: tiktok.seguidores,
      tiktok_likes: tiktok.likes,
      tiktok_video_top_vistas: tiktok.videoTopVistas,
      tiktok_actualizado_en: ahora,
    })
  } catch (e) {
    fallas.push(`TikTok: ${e instanceof WindsorError ? e.message : String(e)}`)
  }

  try {
    const yt = await fetchYoutubeStats(apiKey)
    Object.assign(actualizacion, {
      yt_suscriptores: yt.suscriptores,
      yt_vistas_historicas: yt.vistasHistoricas,
      yt_actualizado_en: ahora,
    })
  } catch (e) {
    fallas.push(`YouTube: ${e instanceof WindsorError ? e.message : String(e)}`)
  }

  if (Object.keys(actualizacion).length > 0) {
    const { error: updateError } = await supabase
      .from('media_kit_stats')
      .update(actualizacion)
      .eq('id', true)
    if (updateError) {
      fallas.push(`Guardar en Supabase: ${updateError.message}`)
    }
  }

  if (fallas.length > 0) {
    await alertarSiCorresponde(supabase, fallas, apiKey)
  }

  return new Response(
    JSON.stringify({ ok: fallas.length === 0, actualizados: Object.keys(actualizacion), fallas }),
    { status: fallas.length === 0 ? 200 : 207 },
  )
})

// Solo manda mail si alguna plataforma lleva más de DIAS_ANTES_DE_ALERTAR
// sin actualizarse — evita mandar un mail cada 5 minutos por una falla de
// un día que se puede resolver sola en la próxima corrida.
async function alertarSiCorresponde(
  supabase: ReturnType<typeof getSupabaseAdmin>,
  fallas: string[],
  apiKey: string,
): Promise<void> {
  const { data: fila } = await supabase
    .from('media_kit_stats')
    .select('ig_actualizado_en, tiktok_actualizado_en, yt_actualizado_en')
    .eq('id', true)
    .maybeSingle()

  const limite = Date.now() - DIAS_ANTES_DE_ALERTAR * 24 * 60 * 60 * 1000
  const timestamps = [fila?.ig_actualizado_en, fila?.tiktok_actualizado_en, fila?.yt_actualizado_en]
  const hayAlgunaVencida = timestamps.some((t) => !t || new Date(t as string).getTime() < limite)
  if (!hayAlgunaVencida) return

  const pistaWindsorTrial = apiKey
    ? '\n\nSi las 3 plataformas fallan con error de autenticación, revisar si venció el trial de Windsor.ai y pasarlo a plan pago.'
    : ''
  await enviarAlerta(
    'Rayando el CDA: el media kit vivo lleva días sin actualizarse',
    `${fallas.join('\n')}${pistaWindsorTrial}`,
  )
}
```

- [ ] **Step 2: Deploy**

```powershell
supabase functions deploy actualizar-stats-mediakit --project-ref qfxfwfcdgqcbmdspjvtk
```

- [ ] **Step 3: Verificación manual (invocación directa, sin esperar al cron)**

```powershell
curl -X POST "https://qfxfwfcdgqcbmdspjvtk.supabase.co/functions/v1/actualizar-stats-mediakit" `
  -H "Authorization: Bearer <SERVICE_ROLE_KEY>"
```

Expected: `{"ok":true,"actualizados":["ig_seguidores",...],"fallas":[]}`. Confirmar en el SQL Editor:
`select * from rayando_cda.media_kit_stats;` — los campos de IG/TikTok/YouTube ya no son los valores por defecto de la Task 1.

- [ ] **Step 4: Commit**

```bash
git add supabase/functions/actualizar-stats-mediakit/index.ts
git commit -m "Agregar Edge Function actualizar-stats-mediakit"
```

---

### Task 4: Cron diario

**Files:** Ninguno (se programa en el SQL Editor, mismo criterio que `refrescar-token-instagram` — no vive en una migración versionada).

- [ ] **Step 1: Programar el cron**

En el SQL Editor de Supabase:

```sql
select cron.schedule(
  'actualizar-stats-mediakit-diario',
  '0 8 * * *', -- todos los días a las 8:00 UTC
  $$
  select net.http_post(
    url := 'https://qfxfwfcdgqcbmdspjvtk.supabase.co/functions/v1/actualizar-stats-mediakit',
    headers := jsonb_build_object('Authorization', 'Bearer <SERVICE_ROLE_KEY>')
  );
  $$
);
```

(`pg_cron`/`pg_net` ya están habilitados en este proyecto desde el subsistema 1 — no hace falta `create extension`.)

- [ ] **Step 2: Verificación**

Run: `select * from cron.job where jobname = 'actualizar-stats-mediakit-diario';`
Expected: una fila con el schedule `0 8 * * *`.

No hace falta commit — este paso no genera cambios de archivo en el repo.

---

### Task 5: Página estática — estructura, diseño y contenido (`mediakit/public/`)

**Files:**
- Create: `mediakit/public/index.html`
- Create: `mediakit/public/styles.css`

**Interfaces:**
- Produces: elementos con `id` específicos que `app.js` (Task 6) va a rellenar con datos en vivo: `#stat-hero-vistas` (Instagram, 30 días — cifra hero), `#stat-ig-seguidores`, `#stat-ig-vistas`, `#stat-ig-interacciones`, `#stat-tiktok-seguidores`, `#stat-tiktok-likes`, `#stat-tiktok-video-top`, `#stat-yt-suscriptores`, `#stat-yt-vistas-card`, `#stat-programas`, `#stat-multiplicador`, `#btn-descargar-pdf`. Cubre las 7 secciones de la spec: hero, quiénes somos, plataformas, "no vendemos seguidores", "no es nicho", propuesta/planes, botón PDF.

- [ ] **Step 1: Crear `mediakit/public/styles.css`**

```css
:root {
  --navy: #0A2A6B;
  --navy-dark: #071A45;
  --electric: #2E6BE0;
  --red: #D2232A;
  --gold: #F2B807;
  --paper: #EDE9DC;
  --ink: #14161C;
  --font-display: "Arial Black", "Arial Narrow", system-ui, sans-serif;
  --font-body: "Inter", "Helvetica Neue", system-ui, sans-serif;
  --font-mono: "IBM Plex Mono", ui-monospace, Consolas, monospace;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--paper);
  color: var(--ink);
  font-family: var(--font-body);
  line-height: 1.55;
}
.wrap { max-width: 880px; margin: 0 auto; padding: 0 20px 80px; }

header.hero {
  background: linear-gradient(160deg, var(--navy) 0%, var(--navy-dark) 100%);
  color: #fff;
  padding: 48px 20px 40px;
  border-bottom: 4px solid var(--gold);
}
header.hero .wrap { padding-bottom: 0; }
header.hero h1 {
  font-family: var(--font-display);
  font-size: clamp(32px, 6vw, 52px);
  margin: 8px 0 4px;
  letter-spacing: -0.01em;
}
header.hero p.subtitle { color: #C7D4F0; font-size: 15px; max-width: 60ch; margin: 0 0 20px; }
.hero-stat-big {
  font-family: var(--font-mono);
  font-weight: 700;
  color: var(--gold);
  font-size: clamp(40px, 8vw, 64px);
  line-height: 1;
}
.hero-stat-big .label { display: block; font-family: var(--font-body); font-size: 13px; color: #B7C6EA; font-weight: 400; margin-top: 6px; text-transform: uppercase; letter-spacing: 0.05em; }

#btn-descargar-pdf {
  position: fixed;
  top: 16px;
  right: 16px;
  z-index: 20;
  background: var(--gold);
  color: var(--navy-dark);
  border: none;
  border-radius: 999px;
  padding: 10px 18px;
  font-weight: 700;
  font-size: 14px;
  cursor: pointer;
  box-shadow: 0 2px 10px rgba(0,0,0,0.25);
}

section { padding: 44px 0; }
h2 {
  font-family: var(--font-display);
  color: var(--navy);
  font-size: 26px;
  border-bottom: 3px solid var(--navy);
  padding-bottom: 10px;
  margin: 0 0 20px;
}
p { max-width: 68ch; }

.platform-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin: 18px 0; }
@media (max-width: 640px) { .platform-grid { grid-template-columns: 1fr; } }
.platform-card {
  background: #fff;
  border: 1px solid #DDD6C2;
  border-radius: 10px;
  padding: 18px;
}
.platform-card h3 { margin: 0 0 12px; font-size: 15px; text-transform: uppercase; letter-spacing: 0.04em; }
.platform-card .metric { font-family: var(--font-mono); font-weight: 700; font-size: 24px; color: var(--navy); }
.platform-card .metric-label { font-size: 12px; color: #6B6653; margin-bottom: 10px; }

.callout {
  background: var(--navy);
  color: #fff;
  border-radius: 12px;
  padding: 26px 28px;
  margin: 20px 0;
}
.callout .big-number { font-family: var(--font-mono); font-weight: 700; color: var(--gold); font-size: 40px; }
.callout blockquote { border-left: 3px solid var(--gold); margin: 16px 0 0; padding-left: 16px; font-style: italic; color: #E5ECFB; }

.stat-compare { display: flex; gap: 16px; flex-wrap: wrap; margin: 18px 0; }
.stat-compare .box { flex: 1 1 200px; background: #fff; border: 1px solid #DDD6C2; border-radius: 10px; padding: 16px; }
.stat-compare .box .n { font-family: var(--font-mono); font-weight: 700; font-size: 28px; color: var(--red); }
.stat-compare .box .l { font-size: 12.5px; color: #6B6653; }

footer { text-align: center; padding: 30px 20px; font-size: 13px; color: #6B6653; }

@media print {
  #btn-descargar-pdf { display: none; }
  body { background: #fff; }
}
```

- [ ] **Step 2: Crear `mediakit/public/index.html`**

```html
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Rayando el CDA — Media Kit</title>
  <link rel="stylesheet" href="styles.css" />
</head>
<body>
  <button id="btn-descargar-pdf" type="button">Descargar PDF</button>

  <header class="hero">
    <div class="wrap">
      <h1>RAYANDO EL CDA</h1>
      <p class="subtitle">Programa de Universidad de Chile · EN VIVO cada lunes 23:00 por YouTube. Opinión con postura, entrevistas con protagonistas y humor de hinchada.</p>
      <div class="hero-stat-big">
        <span id="stat-hero-vistas">—</span>
        <span class="label">visualizaciones mensuales — Instagram + TikTok + YouTube, número en vivo</span>
      </div>
    </div>
  </header>

  <div class="wrap">

    <section id="quienes-somos">
      <h2>Quiénes somos</h2>
      <p>Rayando el CDA es un medio de hinchas de Universidad de Chile con más de 70 programas en vivo emitidos y comunidad activa en tres plataformas. Cada semana producimos un programa de más de una hora y, a partir de él, más de 20 piezas de contenido corto.</p>
      <p>El equipo combina conducción periodística, edición profesional y un sistema propio de producción con revisión editorial pieza por pieza — para que cada contenido, y cada marca que lo acompaña, se vea impecable.</p>
    </section>

    <section id="plataformas">
      <h2>Nuestras plataformas</h2>
      <p>Números en vivo, actualizados todos los días.</p>
      <div class="platform-grid">
        <div class="platform-card">
          <h3>Instagram · @rayandoelcda</h3>
          <div class="metric-label">Seguidores</div>
          <div class="metric" id="stat-ig-seguidores">—</div>
          <div class="metric-label" style="margin-top:10px;">Vistas (30 días)</div>
          <div class="metric" id="stat-ig-vistas">—</div>
          <div class="metric-label" style="margin-top:10px;">Interacciones (90 días)</div>
          <div class="metric" id="stat-ig-interacciones">—</div>
        </div>
        <div class="platform-card">
          <h3>TikTok · @rayando.el.cda</h3>
          <div class="metric-label">Seguidores</div>
          <div class="metric" id="stat-tiktok-seguidores">—</div>
          <div class="metric-label" style="margin-top:10px;">Me gusta acumulados</div>
          <div class="metric" id="stat-tiktok-likes">—</div>
          <div class="metric-label" style="margin-top:10px;">Vistas de video (30 días)</div>
          <div class="metric" id="stat-tiktok-video-top">—</div>
        </div>
        <div class="platform-card">
          <h3>YouTube · Rayando el CDA</h3>
          <div class="metric-label">Suscriptores</div>
          <div class="metric" id="stat-yt-suscriptores">—</div>
          <div class="metric-label" style="margin-top:10px;">Vistas históricas</div>
          <div class="metric" id="stat-yt-vistas-card">—</div>
          <div class="metric-label" style="margin-top:10px;">Programas en vivo emitidos</div>
          <div class="metric" id="stat-programas">—</div>
        </div>
      </div>
    </section>

    <section id="no-vendemos-seguidores">
      <h2>No vendemos seguidores. Vendemos contenido que funciona.</h2>
      <p>Nuestros seguidores en redes son un número chico a propósito: no compramos audiencia, la ganamos publicación por publicación. Lo que importa es el alcance real — y ahí la relación es clara:</p>
      <div class="callout">
        <div class="big-number"><span id="stat-multiplicador">—</span>×</div>
        <p style="margin:6px 0 0;color:#E5ECFB;">más vistas mensuales en Instagram que seguidores tenemos — contenido que el algoritmo empuja a gente nueva todo el tiempo, no una base cautiva que ya nos sigue.</p>
        <blockquote>"Cristián, parte del equipo, ya logró publicaciones con más de 5.000.000 de vistas trabajando en otro medio. Esa capacidad de generar contenido que explota está ahora enfocada 100% en Rayando el CDA."</blockquote>
      </div>
    </section>

    <section id="no-es-nicho">
      <h2>La hinchada de la U no es un nicho. Es una de las dos más grandes de Chile.</h2>
      <p>Entre el 18% y el 21% de los chilenos se declara hincha de Universidad de Chile (encuestas Cadem / La Cosa Nostra) — y en la temporada 2024, la U convocó más público real a los estadios que Colo-Colo: no es la hinchada que más dice ser fanática en una encuesta, es la que más se mueve.</p>
      <div class="stat-compare">
        <div class="box">
          <div class="n">549.000</div>
          <div class="l">espectadores de la U en 2024 (Estadio Seguro)</div>
        </div>
        <div class="box">
          <div class="n">405.000</div>
          <div class="l">espectadores de Colo-Colo en 2024</div>
        </div>
      </div>
      <p>Auspiciar a una hinchada específica no es una apuesta rara: <strong>12 de los 16 clubes de Primera División de Chile ya tienen una casa de apuestas como sponsor exclusivo de su categoría</strong>. Es la forma estándar en la que las marcas deportivas ya invierten en Chile — acá, a una fracción del costo de un sponsor de camiseta.</p>
    </section>

    <section id="propuesta">
      <h2>Planes mensuales</h2>
      <div class="platform-grid">
        <div class="platform-card">
          <h3>Entrada General · Presencia</h3>
          <div class="metric">$500.000</div>
          <div class="metric-label">mensual + IVA</div>
          <p style="font-size:13.5px;">Logo en los +20 clips del mes (IG · TikTok · YouTube), logo en todas las portadas, informe mensual de resultados.</p>
        </div>
        <div class="platform-card">
          <h3>Entrada Tribuna · Marca Aliada</h3>
          <div class="metric">$1.000.000</div>
          <div class="metric-label">mensual + IVA</div>
          <p style="font-size:13.5px;">Todo lo del plan Presencia + 2 menciones leídas al mes en el programa en vivo + 1 historia y 1 reel promocional mensual.</p>
        </div>
        <div class="platform-card" style="border-color:var(--gold);border-width:2px;">
          <h3>Palco · Auspiciador Principal</h3>
          <div class="metric">$1.500.000</div>
          <div class="metric-label">mensual + IVA</div>
          <p style="font-size:13.5px;">Todo lo del plan Marca Aliada + mención leída en CADA programa + 1 clip "Presentado por su marca" + producto en pantalla + exclusividad de rubro.</p>
        </div>
      </div>
      <p style="font-size:13px;color:#6B6653;">También disponible: contratos anuales con placement permanente (cotización a medida) · afiliados a comisión · descuento por contrato de 3+ meses.</p>
    </section>

  </div>

  <footer>
    Sebastián Pino · Director · seba@rayandoelcda.com · +56 9 7389 4323 · @rayandoelcda
  </footer>

  <script src="app.js"></script>
</body>
</html>
```

- [ ] **Step 3: Verificación manual**

Abrir `mediakit/public/index.html` directo en el navegador (sin servidor). Expected: la página carga, todos los `—` placeholder se ven en su lugar (todavía no hay JS conectado — eso es la Task 6), diseño coherente con la paleta de marca, responsive en una ventana angosta.

- [ ] **Step 4: Commit**

```bash
git add mediakit/public/index.html mediakit/public/styles.css
git commit -m "Agregar estructura, diseño y contenido de mediakit/public/"
```

---

### Task 6: `app.js` — datos en vivo + exportar a PDF

**Files:**
- Create: `mediakit/public/app.js`

**Interfaces:**
- Consumes: elementos con los `id` definidos en la Task 5, tabla `rayando_cda.media_kit_stats` vía REST de Supabase.

- [ ] **Step 1: Implementar `app.js`**

```javascript
// Media kit vivo: lee rayando_cda.media_kit_stats vía la API REST de
// Supabase (PostgREST) con la anon key — de solo lectura, protegido por
// la policy media_kit_stats_anon_select (ver mediakit/supabase_migration_media_kit_stats.sql).
// Sin build tool: la anon key es pública por diseño (Supabase la protege
// con RLS, no con secreto), así que va hardcodeada acá, igual de expuesta
// que en cualquier bundle de frontend.

const SUPABASE_URL = 'https://qfxfwfcdgqcbmdspjvtk.supabase.co'
const SUPABASE_ANON_KEY = 'REEMPLAZAR_CON_LA_ANON_KEY_REAL_DEL_PROYECTO'

const fmt = new Intl.NumberFormat('es-CL')

function setText(id, value) {
  const el = document.getElementById(id)
  if (el) el.textContent = value
}

async function cargarStats() {
  try {
    const resp = await fetch(
      `${SUPABASE_URL}/rest/v1/media_kit_stats?select=*&id=eq.true`,
      { headers: { apikey: SUPABASE_ANON_KEY, Authorization: `Bearer ${SUPABASE_ANON_KEY}` } },
    )
    if (!resp.ok) throw new Error(`Supabase REST devolvió ${resp.status}`)
    const filas = await resp.json()
    const stats = filas[0]
    if (!stats) return // sin fila todavía: quedan los defaults del HTML

    const heroTotal = (stats.ig_vistas_30d ?? 0) + (stats.tiktok_video_top_vistas ?? 0) + (stats.yt_vistas_30d ?? 0)
    setText('stat-hero-vistas', fmt.format(heroTotal))

    setText('stat-ig-seguidores', fmt.format(stats.ig_seguidores))
    setText('stat-ig-vistas', fmt.format(stats.ig_vistas_30d))
    setText('stat-ig-interacciones', fmt.format(stats.ig_interacciones_90d))

    setText('stat-tiktok-seguidores', fmt.format(stats.tiktok_seguidores))
    setText('stat-tiktok-likes', fmt.format(stats.tiktok_likes))
    setText('stat-tiktok-video-top', fmt.format(stats.tiktok_video_top_vistas))

    setText('stat-yt-suscriptores', fmt.format(stats.yt_suscriptores))
    setText('stat-yt-vistas-card', fmt.format(stats.yt_vistas_historicas))
    setText('stat-programas', fmt.format(stats.programas_emitidos))

    if (stats.ig_seguidores > 0) {
      const multiplicador = stats.ig_vistas_30d / stats.ig_seguidores
      setText('stat-multiplicador', multiplicador.toFixed(1))
    }
  } catch (err) {
    // Falla de red o de Supabase: la página se queda con los valores por
    // defecto del HTML (Task 5) — nunca se muestra un error a la marca
    // que está mirando la página.
    console.error('No se pudieron cargar los números en vivo:', err)
  }
}

document.getElementById('btn-descargar-pdf').addEventListener('click', () => {
  window.print()
})

cargarStats()
```

- [ ] **Step 2: Reemplazar la anon key con la real**

Buscar la anon key real del proyecto (Supabase Dashboard → Project Settings → API → `anon` `public` key, la misma que ya usa `app/.env` como `VITE_SUPABASE_ANON_KEY`) y reemplazar `REEMPLAZAR_CON_LA_ANON_KEY_REAL_DEL_PROYECTO` en `mediakit/public/app.js`.

- [ ] **Step 3: Verificación manual**

Servir `mediakit/public/` con un servidor estático simple (para evitar problemas de CORS/fetch con `file://`):

```powershell
cd mediakit/public
python -m http.server 8000
```

Abrir `http://localhost:8000/` en el navegador. Expected: los números ya no muestran `—`, coinciden con lo que devuelve `select * from rayando_cda.media_kit_stats;` en Supabase. Click en "Descargar PDF" abre el diálogo de impresión del navegador con el botón oculto (por la regla `@media print`).

- [ ] **Step 4: Commit**

```bash
git add mediakit/public/app.js
git commit -m "Conectar mediakit/public a los datos en vivo + exportar a PDF"
```

---

### Task 7: Deploy en GitHub Pages

**Files:**
- Modify: `.github/workflows/deploy.yml`
- Create: `mediakit/README.md`

**Interfaces:** Ninguna — solo configuración de CI/deploy.

- [ ] **Step 1: Modificar el workflow**

En `.github/workflows/deploy.yml`, agregar `mediakit/public/**` a los paths que disparan el deploy, y copiar `mediakit/public/` dentro del `dist` de la app antes de subir el artifact:

```yaml
name: Deploy to GitHub Pages

on:
  push:
    branches: [main]
    paths:
      - 'app/**'
      - 'mediakit/public/**'
      - '.github/workflows/deploy.yml'
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: true

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
          cache-dependency-path: app/package-lock.json

      - working-directory: app
        run: npm ci

      - working-directory: app
        run: npm run build
        env:
          VITE_SUPABASE_URL: ${{ secrets.VITE_SUPABASE_URL }}
          VITE_SUPABASE_ANON_KEY: ${{ secrets.VITE_SUPABASE_ANON_KEY }}

      - name: Copiar el media kit vivo al mismo sitio, en /mediakit/
        run: |
          mkdir -p app/dist/mediakit
          cp -r mediakit/public/* app/dist/mediakit/

      - uses: actions/upload-pages-artifact@v3
        with:
          path: app/dist

  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - id: deployment
        uses: actions/deploy-pages@v4
```

(Se sacó el `defaults.run.working-directory: app` global porque el step nuevo de copia corre desde la raíz del repo — cada step de Node ahora especifica `working-directory: app` explícito.)

- [ ] **Step 2: Documentar en `mediakit/README.md`**

```markdown
# Media kit vivo

Página en `https://sebapino25.github.io/rayando-cda-review/mediakit/` —
reemplaza al PDF estático como la pieza que se manda en el primer correo a
una marca. Los números de Instagram, TikTok y YouTube se actualizan solos
todos los días vía Windsor.ai; `programas_emitidos` se edita a mano en
Supabase Studio cuando cambie.

## Estructura

- `public/` — el sitio que se despliega (HTML/CSS/JS plano, sin build).
- `supabase_migration_media_kit_stats.sql` — migración de la tabla
  `rayando_cda.media_kit_stats` (correr una sola vez en el SQL Editor).

## Cómo se actualizan los números

La Edge Function `actualizar-stats-mediakit` corre todos los días a las
8:00 UTC (`pg_cron`, programado a mano en el SQL Editor — ver el plan de
implementación para el `cron.schedule` exacto), trae datos de los 3
connectors de Windsor.ai ya conectados (`instagram`, `tiktok_organic`,
`youtube`) y los guarda en `media_kit_stats`.

**Requiere** el secreto `WINDSOR_API_KEY` cargado en Project Settings >
Edge Functions > Secrets, y una cuenta de Windsor.ai activa (hoy en
trial — pasar a plan pago antes de que venza, o los 3 números dejan de
actualizarse).

## Actualizar `programas_emitidos` a mano

En el SQL Editor de Supabase:

```sql
update rayando_cda.media_kit_stats set programas_emitidos = <número> where id = true;
```
```

- [ ] **Step 3: Verificación manual**

Después de mergear a `main`, revisar que el workflow "Deploy to GitHub Pages" corra y termine en verde (`gh run list --workflow=deploy.yml --limit 1` o la pestaña Actions de GitHub). Abrir `https://sebapino25.github.io/rayando-cda-review/mediakit/` y confirmar que carga con los números reales.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/deploy.yml mediakit/README.md
git commit -m "Desplegar mediakit/public/ junto a app/ en GitHub Pages"
```
