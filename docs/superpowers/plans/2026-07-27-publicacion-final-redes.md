# Publicación final desde la app — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un botón "Publicar en redes" en la pestaña Historial de la app, protegido por PIN, que dispara la publicación real de un clip aprobado (YouTube público + Instagram Reels, TikTok apagado hasta que se apruebe la app), sin depender de la PC local del dueño del proyecto.

**Architecture:** Supabase Edge Function (`publicar-clip`, Deno/TypeScript) invocada desde React vía `supabase.functions.invoke()`. El pipeline Python sube el video a Supabase Storage al cortar el clip (no al publicar), así la Edge Function no necesita acceso al disco local. Una segunda Edge Function programada (`refrescar-token-instagram`) mantiene vivo el token de Instagram sin intervención humana.

**Tech Stack:** Python 3.12 (pipeline, sin cambios de stack), Deno/TypeScript (Supabase Edge Functions, runtime propio de Supabase), React 19 + Vite (app existente), Supabase (Postgres + Storage + Edge Functions + `pg_cron`/`pg_net`), Resend (email de alertas).

Spec de referencia: `docs/superpowers/specs/2026-07-27-publicacion-final-redes-design.md`

## Global Constraints

- Todo el código/comentarios/mensajes de usuario van en español, consistente con el resto del repo.
- `app/` no tiene framework de testing (no hay `vitest`/`jest` en `package.json`) — no se introduce uno nuevo solo para este botón; la verificación de UI es manual, siguiendo la convención ya establecida en este proyecto (ver `CAMBIOS.md`, todo se verificó manualmente hasta ahora).
- `pipeline/` no usa `pytest` — las tareas Python se verifican con scripts/comandos manuales ad hoc, mismo patrón que ya usan `publicar_automatico.py`/`reprocesar_subtitulos.py` (dry-run por defecto, `--apply` para ejecutar de verdad, `--clip-id` para probar un solo clip).
- Las Edge Functions en Deno SÍ llevan tests automatizados con `Deno.test` (viene incluido en el runtime, no suma dependencias) para lógica pura o que acepta un `fetch` inyectado — no se mockea la librería de Supabase, esa parte se verifica de forma manual/integración contra el clip fixture (`estado='prueba'`).
- Nunca se corre nada de prueba contra filas reales de `rayando_cda.clips` — siempre contra la fila fixture `estado='prueba'` documentada en `app/README.md`, revirtiendo su estado al terminar.
- `rayando_cda.instagram_token` y `rayando_cda.pin_intentos` tienen RLS activo sin policies para `anon`/`authenticated` — nunca deben ser legibles desde el navegador.
- El proyecto de Supabase es compartido con otro uso (ver `README.md` raíz) — cualquier cambio de schema contra el proyecto real (no solo el archivo `.sql`) se confirma explícitamente con el usuario antes de aplicarse.

---

## Task 1: Migración de base de datos

**Files:**
- Modify: `pipeline/supabase_migration_clips.sql`

**Interfaces:**
- Produces: columnas `rayando_cda.clips.video_url` (text), `rayando_cda.clips.publicando_en` (timestamptz), `rayando_cda.clips.portada_url` (text, ya existía en la tabla real, se documenta acá), `rayando_cda.clips.instagram_media_id` (text, ídem); tablas `rayando_cda.instagram_token` (fila única) y `rayando_cda.pin_intentos`. Todas las tareas siguientes dependen de estos nombres exactos.

- [ ] **Step 1: Agregar las columnas y tablas nuevas al final de `pipeline/supabase_migration_clips.sql`**

Agregar antes de la sección final de "Paso manual obligatorio" (después de la línea `alter table rayando_cda.clips enable row level security;`):

```sql
-- --- Publicación final desde la app (ver docs/superpowers/specs/2026-07-27-publicacion-final-redes-design.md) ---
alter table rayando_cda.clips add column if not exists video_url text;
alter table rayando_cda.clips add column if not exists publicando_en timestamptz;

-- Corrección de drift: estas dos ya existen en la tabla real (las usa
-- publicar.py/publicar_automatico.py/la app) pero no estaban documentadas
-- en este archivo — se agregaron en algún momento fuera de este script.
alter table rayando_cda.clips add column if not exists portada_url text;
alter table rayando_cda.clips add column if not exists instagram_media_id text;

-- Token de Instagram vigente, refrescado automáticamente por la Edge
-- Function refrescar-token-instagram (cron semanal). Fila única forzada
-- por el check constraint sobre "id".
create table if not exists rayando_cda.instagram_token (
    id boolean primary key default true,
    access_token text not null,
    vence_en timestamptz,
    actualizado_en timestamptz not null default now(),
    constraint instagram_token_fila_unica check (id)
);

-- Intentos fallidos de PIN contra publicar-clip (rate limiting de un
-- endpoint público). Solo se insertan filas en intentos fallidos.
create table if not exists rayando_cda.pin_intentos (
    id bigint generated always as identity primary key,
    creado_en timestamptz not null default now()
);

grant all on table rayando_cda.instagram_token to service_role;
grant all on table rayando_cda.pin_intentos to service_role;

alter table rayando_cda.instagram_token enable row level security;
alter table rayando_cda.pin_intentos enable row level security;
-- Sin policies para anon/authenticated a propósito: instagram_token tiene
-- el access token vigente de Instagram, pin_intentos es el contador de
-- seguridad del PIN. Solo service_role (Edge Functions) las toca — nunca
-- deben quedar expuestas al schema "Exposed" que usa la app con la anon key.
```

- [ ] **Step 2: Verificar que el archivo sigue siendo válido SQL idempotente**

Leer el archivo completo y confirmar que cada `create table`/`alter table` usa `if not exists`/`add column if not exists`, siguiendo el mismo estilo que el resto del archivo.

- [ ] **Step 3: Confirmar con el usuario antes de aplicar contra el proyecto real de Supabase**

Este es un proyecto compartido con otro uso (ver Global Constraints). Preguntar explícitamente antes de ejecutar la migración contra la base real — no asumir luz verde por haber aprobado la spec.

- [ ] **Step 4: Aplicar la migración**

Una vez confirmado: correr el contenido de `pipeline/supabase_migration_clips.sql` completo en el SQL Editor del proyecto de Supabase (o vía la tool de Supabase MCP `apply_migration` si está disponible en el entorno de ejecución). Es idempotente, no rompe nada si se corre de nuevo.

- [ ] **Step 5: Verificar en el dashboard de Supabase**

Table Editor → schema `rayando_cda` → confirmar que `clips` tiene las columnas `video_url`, `publicando_en`, `portada_url`, `instagram_media_id`, y que existen las tablas `instagram_token` y `pin_intentos`.

- [ ] **Step 6: Commit**

```bash
git add pipeline/supabase_migration_clips.sql
git commit -m "Agregar columnas/tablas de publicación final a la migración de Supabase"
```

---

## Task 2: `pipeline/publicar.py` — subir vertical.mp4 a Storage y guardar `video_url`

**Files:**
- Modify: `pipeline/publicar.py:174-298`

**Interfaces:**
- Consumes: `config.SUPABASE_CLIPS_VIDEO_BUCKET` (ya existe en `config.py`), `get_supabase_client()` (ya existe en este archivo).
- Produces: `subir_video_storage(video_path: Path, storage_path: str) -> str` — nueva función pública que Task 3 va a importar desde `pipeline.publicar`. `publicar_clip(...)` ahora incluye `"video_url"` en el payload insertado y en `resumen.txt`.

- [ ] **Step 1: Agregar `subir_video_storage` después de `subir_portada_storage` (línea 190)**

```python
def subir_video_storage(video_path: Path, storage_path: str) -> str:
    """Sube el vertical.mp4 final al bucket público clips-video de Supabase
    Storage y devuelve su URL pública. A diferencia de la portada, esto NO
    es opcional: sin video_url la publicación final (Edge Function
    publicar-clip) no tiene forma de acceder al archivo — una falla acá se
    propaga, no hay fallback silencioso como en subir_portada_storage."""
    supabase = get_supabase_client()
    data = video_path.read_bytes()
    supabase.storage.from_(config.SUPABASE_CLIPS_VIDEO_BUCKET).upload(
        storage_path, data, {"content-type": "video/mp4", "upsert": "true"}
    )
    return supabase.storage.from_(config.SUPABASE_CLIPS_VIDEO_BUCKET).get_public_url(storage_path)
```

- [ ] **Step 2: Verificación rápida de conectividad (sin correr el pipeline completo)**

Con `.env` completo (`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`), desde `pipeline/`:

```powershell
python -c "from pathlib import Path; import publicar; p = Path('verificacion_storage.mp4'); p.write_bytes(b'contenido de prueba'); url = publicar.subir_video_storage(p, 'test/verificacion-storage.mp4'); print(url); p.unlink()"
```

Expected: imprime una URL que empieza con la URL del proyecto de Supabase y termina en `clips-video/test/verificacion-storage.mp4`, sin traceback. Después, borrar `test/verificacion-storage.mp4` a mano desde el Storage del dashboard de Supabase (es solo un archivo de verificación, no un clip real).

- [ ] **Step 3: Llamar a `subir_video_storage` dentro de `publicar_clip`, después de subir la portada (después de la línea que imprime `f"  Portada: {portada_url}"`, antes de armar `payload`)**

```python
    print("  Subiendo vertical.mp4 a Supabase Storage...")
    video_storage_path = f"{program_date}/{nombre_clip}.mp4"
    video_url = subir_video_storage(video_path, video_storage_path)
    print(f"  Video URL: {video_url}")
```

- [ ] **Step 4: Agregar `video_url` al payload y a `resumen.txt`**

En el diccionario `payload` (dentro de `publicar_clip`), agregar la clave:

```python
        "video_url": video_url,
```

En el string `resumen`, agregar una línea (después de la línea de `Portada:`):

```python
        f"Video URL: {video_url}\n"
```

- [ ] **Step 5: Verificación end-to-end mínima**

Cortar un clip de prueba real con `cortar_clip.py` contra cualquier grabación ya transcrita que tengas a mano, y confirmar en consola que aparece la línea `Video URL: https://...` y que el `resumen.txt` generado la incluye. Confirmar en el dashboard de Supabase (Table Editor → `rayando_cda.clips`) que la fila insertada tiene `video_url` no nulo.

- [ ] **Step 6: Commit**

```bash
git add pipeline/publicar.py
git commit -m "Subir vertical.mp4 a Supabase Storage al cortar el clip, no al publicar"
```

---

## Task 3: `pipeline/publicar_automatico.py` — usar `video_url` con fallback local

**Files:**
- Modify: `pipeline/publicar_automatico.py:89-98,151-176`

**Interfaces:**
- Consumes: `publicar.subir_video_storage` (Task 2), `reprocesar_subtitulos.encontrar_carpetas_candidatas` (ya existe).
- Produces: `publicar_reel(row, carpeta)` sigue con la misma firma, pero ahora usa `row["video_url"]` cuando está presente en vez de siempre re-subir desde el disco local.

Nota de contexto: desde este subsistema, `publicar_automatico.py` deja de ser el camino principal de publicación (eso pasa a ser la Edge Function `publicar-clip`, Task 9) y queda como fallback manual documentado — útil si la Edge Function falla y hace falta forzar algo a mano desde la PC local.

- [ ] **Step 1: Eliminar la función `subir_video_storage` local (líneas 89-98) y reemplazar por un import**

En los imports del archivo (cerca de la línea 42-43), agregar:

```python
import publicar
```

(si `publicar` ya está importado, no duplicar el import). Eliminar por completo la definición de `subir_video_storage` que hoy vive en este archivo (líneas 89-98) — a partir de ahora se usa `publicar.subir_video_storage`.

- [ ] **Step 2: Actualizar `publicar_reel` para usar `row.get("video_url")` primero**

Reemplazar el cuerpo de `publicar_reel` (líneas 151-176) por:

```python
def publicar_reel(row: dict, carpeta: Path | None) -> str:
    """Publica el Reel de Instagram. Usa row['video_url'] (subido por
    publicar.py al cortar el clip) si está presente — es el camino esperado
    para clips nuevos. Si falta (clips de antes de este subsistema), cae al
    comportamiento viejo: sube vertical.mp4 desde la carpeta local
    encontrada por correlación de contenido."""
    video_url = row.get("video_url")
    if not video_url:
        if carpeta is None:
            raise RuntimeError("No hay video_url en la fila y no se encontró carpeta local para subir el video a mano.")
        vertical_path = carpeta / "vertical.mp4"
        if not vertical_path.exists():
            raise RuntimeError(f"No existe {vertical_path}")
        storage_path = f"{row.get('semana')}/{carpeta.name}.mp4"
        print(f"    video_url ausente en la fila, subiendo {vertical_path.name} a Storage ({config.SUPABASE_CLIPS_VIDEO_BUCKET}/{storage_path})...")
        video_url = publicar.subir_video_storage(vertical_path, storage_path)
        print(f"    Video URL: {video_url}")

    caption = row.get("copy_instagram") or ""
    cover_url = row.get("portada_url")
    print("    Creando contenedor de media (REELS)...")
    creation_id = crear_contenedor_reel(video_url, caption, cover_url)
    print(f"    creation_id: {creation_id}")

    print(f"    Esperando a que el contenedor esté listo (timeout {config.INSTAGRAM_CONTAINER_TIMEOUT_S}s)...")
    esperar_contenedor_listo(creation_id, config.INSTAGRAM_CONTAINER_TIMEOUT_S)

    print("    Publicando...")
    media_id = publicar_contenedor(creation_id)
    print(f"    media_id: {media_id}")
    return media_id
```

- [ ] **Step 3: Actualizar el llamador para pasar `carpeta` como opcional**

En `procesar_fila`, donde hoy dice (dentro del bloque `if config.AUTO_PUBLICAR_INSTAGRAM:` → `else:` de apply real):

```python
            print("  Instagram: buscando carpeta local...")
            carpetas = reprocesar_subtitulos.encontrar_carpetas_candidatas(row)
            if len(carpetas) != 1:
```

Cambiar la condición para que solo sea obligatoria la carpeta si falta `video_url`:

```python
            carpeta = None
            if not row.get("video_url"):
                print("  Instagram: video_url ausente, buscando carpeta local...")
                carpetas = reprocesar_subtitulos.encontrar_carpetas_candidatas(row)
                if len(carpetas) != 1:
                    mensaje = (
                        f"No se encontró una única carpeta local (encontradas: {len(carpetas)}) "
                        "cuyo subtitulos.srt calce EXACTO con transcripcion_original, y la fila no tiene video_url."
                    )
                    print(f"    ERROR: {mensaje}")
                    publicar.registrar_error(nombre_clip, f"Instagram: {mensaje}")
                    exitos["instagram"] = False
                    carpeta = "saltar"  # marcador para no caer al try de abajo
                else:
                    carpeta = carpetas[0]
                    print(f"    Carpeta local: {carpeta}")

            if carpeta != "saltar":
                try:
                    media_id = publicar_reel(row, carpeta)
                    publicar.actualizar_clip_supabase(clip_id, {"instagram_media_id": media_id})
                    print(f"    OK. instagram_media_id guardado: {media_id}")
                    exitos["instagram"] = True
                except Exception as e:
                    mensaje = f"Instagram: {e}"
                    print(f"    ERROR: {mensaje}")
                    publicar.registrar_error(nombre_clip, mensaje)
                    exitos["instagram"] = False
```

- [ ] **Step 4: Actualizar la columna que se pide a Supabase para incluir `video_url`**

En `buscar_pendientes`, la variable `columnas` ya lista los campos que se seleccionan — agregar `video_url`:

```python
    columnas = (
        "id,estado,publicado,semana,youtube_video_id,titulo,youtube_titulo,"
        "youtube_descripcion,copy_instagram,portada_url,instagram_media_id,"
        "transcripcion_original,video_url"
    )
```

- [ ] **Step 5: Actualizar el docstring del módulo (líneas 1-28) para reflejar el nuevo rol de fallback**

Reemplazar el párrafo inicial por:

```python
"""Publicación final (pública) de clips ya aprobados — FALLBACK MANUAL.

Desde el subsistema de publicación final desde la app (ver
docs/superpowers/specs/2026-07-27-publicacion-final-redes-design.md), el
camino principal es el botón "Publicar en redes" de la app (Historial),
que dispara la Edge Function `publicar-clip`. Este script queda como
respaldo manual, para forzar una publicación desde la PC local si la Edge
Function falla o no está disponible.

Pasa el video de YouTube de "no listado" a "público" (con el título/
descripción ya revisados por el equipo) y publica el Reel en Instagram
(@rayandoelcda). Usa row['video_url'] (subido por publicar.py al cortar el
clip) cuando está presente; si falta (clips de antes de este subsistema),
sube el video desde la carpeta local encontrada por correlación de
contenido.
"""
```

- [ ] **Step 6: Verificación manual con dry-run**

```powershell
python publicar_automatico.py --clip-id <id-del-clip-fixture-de-prueba>
```

Expected: corre sin traceback, imprime `[DRY-RUN]`, y si el flag `AUTO_PUBLICAR_INSTAGRAM` está en `True` en `config.py`, el log muestra "video_url ausente..." o el uso directo de `video_url` según corresponda al fixture usado. No debe intentar publicar nada real (sigue sin `--apply`).

- [ ] **Step 7: Commit**

```bash
git add pipeline/publicar_automatico.py
git commit -m "publicar_automatico.py: usar video_url si está presente, mantener como fallback manual"
```

---

## Task 4: Scaffolding de Supabase Edge Functions + helpers compartidos

**Files:**
- Create: `supabase/functions/_shared/supabaseAdmin.ts`
- Create: `supabase/functions/_shared/email.ts`
- Create: `supabase/functions/_shared/email_test.ts`
- Create: `supabase/functions/deno.json`

**Interfaces:**
- Produces: `getSupabaseAdmin(): SupabaseClient` — usado por Tasks 9 y 10. `enviarAlerta(asunto: string, cuerpo: string, fetchImpl?: typeof fetch): Promise<void>` — usado por Tasks 9 y 10.

- [ ] **Step 1: Crear `supabase/functions/deno.json`**

```json
{
  "imports": {
    "@supabase/supabase-js": "https://esm.sh/@supabase/supabase-js@2"
  }
}
```

- [ ] **Step 2: Crear `supabase/functions/_shared/supabaseAdmin.ts`**

```typescript
import { createClient, SupabaseClient } from '@supabase/supabase-js'

// SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY los inyecta Supabase
// automáticamente en toda Edge Function — no hace falta configurarlos
// como secretos custom.
export function getSupabaseAdmin(): SupabaseClient {
  const url = Deno.env.get('SUPABASE_URL')
  const key = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')
  if (!url || !key) {
    throw new Error('Faltan SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY en el entorno de la función')
  }
  return createClient(url, key, { db: { schema: 'rayando_cda' } })
}
```

- [ ] **Step 3: Crear `supabase/functions/_shared/email.ts`**

```typescript
// Envía un email de alerta vía Resend. Usa el sender de sandbox
// (onboarding@resend.dev) — funciona sin verificar dominio propio, pero
// solo puede mandar al email asociado a la cuenta de Resend (suficiente
// acá: ALERT_EMAIL_TO es el email del dueño del proyecto).
export async function enviarAlerta(
  asunto: string,
  cuerpo: string,
  fetchImpl: typeof fetch = fetch,
): Promise<void> {
  const apiKey = Deno.env.get('RESEND_API_KEY')
  const destino = Deno.env.get('ALERT_EMAIL_TO')
  if (!apiKey || !destino) {
    console.error('Falta RESEND_API_KEY o ALERT_EMAIL_TO, no se pudo enviar la alerta:', asunto, cuerpo)
    return
  }
  const resp = await fetchImpl('https://api.resend.com/emails', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      from: 'Rayando el CDA <onboarding@resend.dev>',
      to: [destino],
      subject: asunto,
      text: cuerpo,
    }),
  })
  if (!resp.ok) {
    console.error(`Resend devolvió ${resp.status} al enviar "${asunto}": ${await resp.text()}`)
  }
}
```

- [ ] **Step 4: Escribir el test de `email.ts`**

Crear `supabase/functions/_shared/email_test.ts`:

```typescript
import { assertEquals } from 'https://deno.land/std@0.224.0/assert/mod.ts'
import { enviarAlerta } from './email.ts'

Deno.test('enviarAlerta no lanza si faltan las env vars, solo loguea', async () => {
  Deno.env.delete('RESEND_API_KEY')
  Deno.env.delete('ALERT_EMAIL_TO')
  let llamadoFetch = false
  const fakeFetch = async () => {
    llamadoFetch = true
    return new Response('{}', { status: 200 })
  }
  await enviarAlerta('asunto', 'cuerpo', fakeFetch as typeof fetch)
  assertEquals(llamadoFetch, false)
})

Deno.test('enviarAlerta manda el POST correcto a Resend', async () => {
  Deno.env.set('RESEND_API_KEY', 'clave-test')
  Deno.env.set('ALERT_EMAIL_TO', 'destino@ejemplo.com')
  let capturado: { url: string; body: string } | undefined
  const fakeFetch = async (url: string | URL, init?: RequestInit) => {
    capturado = { url: url.toString(), body: init?.body as string }
    return new Response('{}', { status: 200 })
  }
  await enviarAlerta('Asunto de prueba', 'Cuerpo de prueba', fakeFetch as typeof fetch)
  assertEquals(capturado?.url, 'https://api.resend.com/emails')
  const body = JSON.parse(capturado!.body)
  assertEquals(body.to, ['destino@ejemplo.com'])
  assertEquals(body.subject, 'Asunto de prueba')
  Deno.env.delete('RESEND_API_KEY')
  Deno.env.delete('ALERT_EMAIL_TO')
})
```

- [ ] **Step 5: Correr los tests**

Requiere Deno instalado (`winget install DenoLand.Deno` si no está). Desde `supabase/functions/`:

```powershell
deno test _shared/email_test.ts --allow-env
```

Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add supabase/functions/deno.json supabase/functions/_shared/
git commit -m "Scaffolding de Supabase Edge Functions: cliente admin y helper de email de alerta"
```

---

## Task 5: Módulo de PIN + rate limit (`publicar-clip/pin.ts`)

**Files:**
- Create: `supabase/functions/publicar-clip/pin.ts`
- Create: `supabase/functions/publicar-clip/pin_test.ts`

**Interfaces:**
- Produces: `MAX_INTENTOS_PIN` (const, `= 5`), `excedeLimite(intentosRecientes: number): boolean` — usado por Task 9's `index.ts`.

- [ ] **Step 1: Escribir el test primero**

Crear `supabase/functions/publicar-clip/pin_test.ts`:

```typescript
import { assertEquals } from 'https://deno.land/std@0.224.0/assert/mod.ts'
import { excedeLimite, MAX_INTENTOS_PIN } from './pin.ts'

Deno.test('excedeLimite es false por debajo del máximo', () => {
  assertEquals(excedeLimite(MAX_INTENTOS_PIN - 1), false)
})

Deno.test('excedeLimite es true en el máximo exacto', () => {
  assertEquals(excedeLimite(MAX_INTENTOS_PIN), true)
})

Deno.test('excedeLimite es true por encima del máximo', () => {
  assertEquals(excedeLimite(MAX_INTENTOS_PIN + 3), true)
})

Deno.test('excedeLimite es false con cero intentos', () => {
  assertEquals(excedeLimite(0), false)
})
```

- [ ] **Step 2: Correr el test y confirmar que falla (el archivo `pin.ts` todavía no existe)**

```powershell
deno test publicar-clip/pin_test.ts
```

Expected: FAIL, "Module not found" o similar.

- [ ] **Step 3: Crear `supabase/functions/publicar-clip/pin.ts`**

```typescript
export const MAX_INTENTOS_PIN = 5
export const VENTANA_MINUTOS_PIN = 10

export function excedeLimite(intentosRecientes: number): boolean {
  return intentosRecientes >= MAX_INTENTOS_PIN
}
```

- [ ] **Step 4: Correr el test de nuevo**

```powershell
deno test publicar-clip/pin_test.ts
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add supabase/functions/publicar-clip/pin.ts supabase/functions/publicar-clip/pin_test.ts
git commit -m "Módulo de rate-limit de PIN para publicar-clip"
```

---

## Task 6: Módulo YouTube (`publicar-clip/youtube.ts`)

**Files:**
- Create: `supabase/functions/publicar-clip/youtube.ts`
- Create: `supabase/functions/publicar-clip/youtube_test.ts`

**Interfaces:**
- Consumes: nada de tasks anteriores.
- Produces: `YoutubeCredenciales` (interface), `obtenerAccessTokenYoutube(creds, fetchImpl?): Promise<string>`, `publicarYoutube(videoId, titulo, descripcion, accessToken, fetchImpl?): Promise<void>` — ambos usados por Task 9's `index.ts`.

- [ ] **Step 1: Escribir los tests primero**

Crear `supabase/functions/publicar-clip/youtube_test.ts`:

```typescript
import { assertEquals, assertStringIncludes } from 'https://deno.land/std@0.224.0/assert/mod.ts'
import { obtenerAccessTokenYoutube, publicarYoutube } from './youtube.ts'

Deno.test('obtenerAccessTokenYoutube arma el POST de refresh y devuelve el access_token', async () => {
  let capturado: { url: string; body: string } | undefined
  const fakeFetch = async (url: string | URL, init?: RequestInit) => {
    capturado = { url: url.toString(), body: init?.body as string }
    return new Response(JSON.stringify({ access_token: 'token-123' }), { status: 200 })
  }
  const token = await obtenerAccessTokenYoutube(
    { clientId: 'id-test', clientSecret: 'secret-test', refreshToken: 'refresh-test' },
    fakeFetch as typeof fetch,
  )
  assertEquals(token, 'token-123')
  assertEquals(capturado?.url, 'https://oauth2.googleapis.com/token')
  assertStringIncludes(capturado!.body, 'grant_type=refresh_token')
  assertStringIncludes(capturado!.body, 'refresh_test')
})

Deno.test('obtenerAccessTokenYoutube lanza error si el refresh falla', async () => {
  const fakeFetch = async () => new Response('token revocado', { status: 400 })
  let lanzo = false
  try {
    await obtenerAccessTokenYoutube(
      { clientId: 'id', clientSecret: 'secret', refreshToken: 'refresh' },
      fakeFetch as typeof fetch,
    )
  } catch {
    lanzo = true
  }
  assertEquals(lanzo, true)
})

Deno.test('publicarYoutube lee el video, pisa título/descripción/privacyStatus y usa PUT', async () => {
  const llamadas: { url: string; method?: string; body?: string }[] = []
  const fakeFetch = async (url: string | URL, init?: RequestInit) => {
    llamadas.push({ url: url.toString(), method: init?.method, body: init?.body as string })
    if (llamadas.length === 1) {
      return new Response(
        JSON.stringify({
          items: [{ snippet: { title: 'viejo', categoryId: '17' }, status: { privacyStatus: 'unlisted' } }],
        }),
        { status: 200 },
      )
    }
    return new Response('{}', { status: 200 })
  }
  await publicarYoutube('vid1', 'Nuevo título', 'Nueva descripción', 'token-abc', fakeFetch as typeof fetch)

  assertEquals(llamadas.length, 2)
  assertEquals(llamadas[1].method, 'PUT')
  const body = JSON.parse(llamadas[1].body!)
  assertEquals(body.snippet.title, 'Nuevo título')
  assertEquals(body.snippet.description, 'Nueva descripción')
  assertEquals(body.snippet.categoryId, '17') // se preserva lo que no se pisa
  assertEquals(body.status.privacyStatus, 'public')
})

Deno.test('publicarYoutube lanza error si el video no existe', async () => {
  const fakeFetch = async () => new Response(JSON.stringify({ items: [] }), { status: 200 })
  let lanzo = false
  try {
    await publicarYoutube('vid-inexistente', 't', 'd', 'token', fakeFetch as typeof fetch)
  } catch {
    lanzo = true
  }
  assertEquals(lanzo, true)
})
```

- [ ] **Step 2: Correr los tests y confirmar que fallan**

```powershell
deno test publicar-clip/youtube_test.ts
```

Expected: FAIL, módulo `youtube.ts` no existe.

- [ ] **Step 3: Crear `supabase/functions/publicar-clip/youtube.ts`**

```typescript
export interface YoutubeCredenciales {
  clientId: string
  clientSecret: string
  refreshToken: string
}

export async function obtenerAccessTokenYoutube(
  creds: YoutubeCredenciales,
  fetchImpl: typeof fetch = fetch,
): Promise<string> {
  const resp = await fetchImpl('https://oauth2.googleapis.com/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      client_id: creds.clientId,
      client_secret: creds.clientSecret,
      refresh_token: creds.refreshToken,
      grant_type: 'refresh_token',
    }),
  })
  if (!resp.ok) {
    throw new Error(`YouTube: no se pudo refrescar el access token (${resp.status}): ${await resp.text()}`)
  }
  const data = await resp.json()
  return data.access_token as string
}

// La API de YouTube exige mandar snippet/status completos en el update: si
// se manda solo title/description, categoryId puede resetearse. Por eso se
// lee el recurso actual primero y se pisan solo los campos que corresponden.
export async function publicarYoutube(
  videoId: string,
  titulo: string,
  descripcion: string,
  accessToken: string,
  fetchImpl: typeof fetch = fetch,
): Promise<void> {
  const getResp = await fetchImpl(
    `https://www.googleapis.com/youtube/v3/videos?part=snippet,status&id=${videoId}`,
    { headers: { Authorization: `Bearer ${accessToken}` } },
  )
  if (!getResp.ok) {
    throw new Error(`YouTube: no se pudo leer el video ${videoId} (${getResp.status}): ${await getResp.text()}`)
  }
  const getData = await getResp.json()
  const item = getData.items?.[0]
  if (!item) {
    throw new Error(`YouTube: no se encontró el video ${videoId} (¿ID inválido o de otro canal?)`)
  }

  const snippet = { ...item.snippet, title: titulo, description: descripcion }
  const status = { ...item.status, privacyStatus: 'public' }

  const putResp = await fetchImpl('https://www.googleapis.com/youtube/v3/videos?part=snippet,status', {
    method: 'PUT',
    headers: {
      Authorization: `Bearer ${accessToken}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ id: videoId, snippet, status }),
  })
  if (!putResp.ok) {
    throw new Error(`YouTube: no se pudo publicar el video ${videoId} (${putResp.status}): ${await putResp.text()}`)
  }
}
```

- [ ] **Step 4: Correr los tests de nuevo**

```powershell
deno test publicar-clip/youtube_test.ts
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add supabase/functions/publicar-clip/youtube.ts supabase/functions/publicar-clip/youtube_test.ts
git commit -m "Módulo de publicación a YouTube (privacyStatus público) para publicar-clip"
```

---

## Task 7: Módulo Instagram (`publicar-clip/instagram.ts`)

**Files:**
- Create: `supabase/functions/publicar-clip/instagram.ts`
- Create: `supabase/functions/publicar-clip/instagram_test.ts`

**Interfaces:**
- Produces: `InstagramConfig` (interface), `publicarReel(videoUrl, caption, coverUrl, config, fetchImpl?, sleepMs?): Promise<string>` (devuelve `media_id`) — usado por Task 9's `index.ts`.

Puerto directo de la lógica ya probada en `pipeline/publicar_automatico.py` (`crear_contenedor_reel`/`esperar_contenedor_listo`/`publicar_contenedor`), a TypeScript.

- [ ] **Step 1: Escribir los tests primero**

Crear `supabase/functions/publicar-clip/instagram_test.ts`:

```typescript
import { assertEquals, assertStringIncludes } from 'https://deno.land/std@0.224.0/assert/mod.ts'
import { publicarReel } from './instagram.ts'

const CONFIG_TEST = { igUserId: 'ig-user-1', accessToken: 'token-ig', containerTimeoutMs: 5000 }
const sinEsperar = async (_ms: number) => {}

Deno.test('publicarReel crea contenedor, espera FINISHED y publica', async () => {
  const llamadas: string[] = []
  const fakeFetch = async (url: string | URL) => {
    const u = url.toString()
    llamadas.push(u)
    if (u.includes('/media_publish')) {
      return new Response(JSON.stringify({ id: 'media-final-1' }), { status: 200 })
    }
    if (u.includes('/ig-user-1/media')) {
      return new Response(JSON.stringify({ id: 'creation-1' }), { status: 200 })
    }
    if (u.includes('status_code')) {
      return new Response(JSON.stringify({ status_code: 'FINISHED' }), { status: 200 })
    }
    throw new Error(`URL no esperada en el test: ${u}`)
  }
  const mediaId = await publicarReel(
    'https://storage.ejemplo.com/clip.mp4',
    'Copy de prueba',
    'https://storage.ejemplo.com/portada.jpg',
    CONFIG_TEST,
    fakeFetch as typeof fetch,
    sinEsperar,
  )
  assertEquals(mediaId, 'media-final-1')
  assertEquals(llamadas.some((u) => u.includes('creation-1')), true)
})

Deno.test('publicarReel reintenta mientras el status_code es IN_PROGRESS y corta en FINISHED', async () => {
  let consultas = 0
  const fakeFetch = async (url: string | URL) => {
    const u = url.toString()
    if (u.includes('/media_publish')) return new Response(JSON.stringify({ id: 'm1' }), { status: 200 })
    if (u.includes('/ig-user-1/media')) return new Response(JSON.stringify({ id: 'c1' }), { status: 200 })
    if (u.includes('status_code')) {
      consultas++
      const status = consultas < 3 ? 'IN_PROGRESS' : 'FINISHED'
      return new Response(JSON.stringify({ status_code: status }), { status: 200 })
    }
    throw new Error(`URL no esperada: ${u}`)
  }
  await publicarReel('url', 'caption', null, CONFIG_TEST, fakeFetch as typeof fetch, sinEsperar)
  assertEquals(consultas, 3)
})

Deno.test('publicarReel lanza error si el contenedor devuelve ERROR', async () => {
  const fakeFetch = async (url: string | URL) => {
    const u = url.toString()
    if (u.includes('/ig-user-1/media')) return new Response(JSON.stringify({ id: 'c1' }), { status: 200 })
    if (u.includes('status_code')) return new Response(JSON.stringify({ status_code: 'ERROR' }), { status: 200 })
    throw new Error(`URL no esperada: ${u}`)
  }
  let lanzo = false
  try {
    await publicarReel('url', 'caption', null, CONFIG_TEST, fakeFetch as typeof fetch, sinEsperar)
  } catch (e) {
    lanzo = true
    assertStringIncludes((e as Error).message, 'ERROR')
  }
  assertEquals(lanzo, true)
})

Deno.test('publicarReel manda cover_url solo si viene definida', async () => {
  let bodyCapturado: string | undefined
  const fakeFetch = async (url: string | URL, init?: RequestInit) => {
    const u = url.toString()
    if (u.includes('/ig-user-1/media')) {
      bodyCapturado = init?.body?.toString()
      return new Response(JSON.stringify({ id: 'c1' }), { status: 200 })
    }
    if (u.includes('status_code')) return new Response(JSON.stringify({ status_code: 'FINISHED' }), { status: 200 })
    if (u.includes('/media_publish')) return new Response(JSON.stringify({ id: 'm1' }), { status: 200 })
    throw new Error(`URL no esperada: ${u}`)
  }
  await publicarReel('url-video', 'caption', null, CONFIG_TEST, fakeFetch as typeof fetch, sinEsperar)
  assertEquals(bodyCapturado?.includes('cover_url'), false)
})
```

- [ ] **Step 2: Correr los tests y confirmar que fallan**

```powershell
deno test publicar-clip/instagram_test.ts
```

Expected: FAIL, módulo `instagram.ts` no existe.

- [ ] **Step 3: Crear `supabase/functions/publicar-clip/instagram.ts`**

```typescript
const GRAPH_API_BASE = 'https://graph.instagram.com'

export interface InstagramConfig {
  igUserId: string
  accessToken: string
  containerTimeoutMs: number
}

export async function crearContenedorReel(
  videoUrl: string,
  caption: string,
  coverUrl: string | null,
  config: InstagramConfig,
  fetchImpl: typeof fetch = fetch,
): Promise<string> {
  const params = new URLSearchParams({
    media_type: 'REELS',
    video_url: videoUrl,
    caption,
    access_token: config.accessToken,
  })
  if (coverUrl) params.set('cover_url', coverUrl)

  const resp = await fetchImpl(`${GRAPH_API_BASE}/${config.igUserId}/media`, {
    method: 'POST',
    body: params,
  })
  if (!resp.ok) {
    throw new Error(`Instagram: error al crear el contenedor de media (${resp.status}): ${await resp.text()}`)
  }
  const data = await resp.json()
  return data.id as string
}

// A diferencia de una foto, un contenedor de Reel no queda FINISHED al
// toque: Instagram tiene que procesar el video primero.
export async function esperarContenedorListo(
  creationId: string,
  config: InstagramConfig,
  fetchImpl: typeof fetch = fetch,
  sleepMs: (ms: number) => Promise<void> = (ms) => new Promise((r) => setTimeout(r, ms)),
): Promise<void> {
  const inicio = Date.now()
  while (Date.now() - inicio < config.containerTimeoutMs) {
    const resp = await fetchImpl(
      `${GRAPH_API_BASE}/${creationId}?fields=status_code&access_token=${config.accessToken}`,
    )
    if (!resp.ok) {
      throw new Error(`Instagram: error consultando el contenedor (${resp.status}): ${await resp.text()}`)
    }
    const data = await resp.json()
    if (data.status_code === 'FINISHED') return
    if (data.status_code === 'ERROR') {
      throw new Error(`Instagram: el contenedor de media falló: ${JSON.stringify(data)}`)
    }
    await sleepMs(3000)
  }
  throw new Error(`Instagram: el contenedor ${creationId} no llegó a FINISHED en ${config.containerTimeoutMs}ms`)
}

export async function publicarContenedor(
  creationId: string,
  config: InstagramConfig,
  fetchImpl: typeof fetch = fetch,
): Promise<string> {
  const resp = await fetchImpl(`${GRAPH_API_BASE}/${config.igUserId}/media_publish`, {
    method: 'POST',
    body: new URLSearchParams({ creation_id: creationId, access_token: config.accessToken }),
  })
  if (!resp.ok) {
    throw new Error(`Instagram: error al publicar (${resp.status}): ${await resp.text()}`)
  }
  const data = await resp.json()
  return data.id as string
}

export async function publicarReel(
  videoUrl: string,
  caption: string,
  coverUrl: string | null,
  config: InstagramConfig,
  fetchImpl: typeof fetch = fetch,
  sleepMs?: (ms: number) => Promise<void>,
): Promise<string> {
  const creationId = await crearContenedorReel(videoUrl, caption, coverUrl, config, fetchImpl)
  await esperarContenedorListo(creationId, config, fetchImpl, sleepMs)
  return await publicarContenedor(creationId, config, fetchImpl)
}
```

- [ ] **Step 4: Correr los tests de nuevo**

```powershell
deno test publicar-clip/instagram_test.ts
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add supabase/functions/publicar-clip/instagram.ts supabase/functions/publicar-clip/instagram_test.ts
git commit -m "Módulo de publicación de Reels a Instagram para publicar-clip (puerto de publicar_automatico.py)"
```

---

## Task 8: Módulo TikTok (`publicar-clip/tiktok.ts`, flag apagado)

**Files:**
- Create: `supabase/functions/publicar-clip/tiktok.ts`
- Create: `supabase/functions/publicar-clip/tiktok_test.ts`

**Interfaces:**
- Produces: `TikTokConfig` (interface), `publicarTiktok(videoUrl, caption, config, fetchImpl?): Promise<string>` — usado por Task 9's `index.ts`, pero solo se llama si `PUBLICAR_TIKTOK === 'true'`.

Recordatorio de la spec: esto se construye contra la documentación pública de la Content Posting API v2 sin poder probarlo en producción (la app de TikTok Developers no está aprobada). Es probable que necesite ajuste cuando se active de verdad.

- [ ] **Step 1: Escribir los tests primero**

Crear `supabase/functions/publicar-clip/tiktok_test.ts`:

```typescript
import { assertEquals } from 'https://deno.land/std@0.224.0/assert/mod.ts'
import { publicarTiktok } from './tiktok.ts'

Deno.test('publicarTiktok arma el request PULL_FROM_URL correcto', async () => {
  let capturado: { url: string; body: string; headers: Record<string, string> } | undefined
  const fakeFetch = async (url: string | URL, init?: RequestInit) => {
    capturado = {
      url: url.toString(),
      body: init?.body as string,
      headers: init?.headers as Record<string, string>,
    }
    return new Response(JSON.stringify({ data: { publish_id: 'pub-1' }, error: { code: 'ok' } }), { status: 200 })
  }
  const publishId = await publicarTiktok(
    'https://storage.ejemplo.com/clip.mp4',
    'Copy de prueba',
    { accessToken: 'token-tt' },
    fakeFetch as typeof fetch,
  )
  assertEquals(publishId, 'pub-1')
  assertEquals(capturado?.url, 'https://open.tiktokapis.com/v2/post/publish/video/init/')
  const body = JSON.parse(capturado!.body)
  assertEquals(body.source_info.source, 'PULL_FROM_URL')
  assertEquals(body.source_info.video_url, 'https://storage.ejemplo.com/clip.mp4')
})

Deno.test('publicarTiktok lanza error si la respuesta HTTP no es 200', async () => {
  const fakeFetch = async () => new Response('error', { status: 401 })
  let lanzo = false
  try {
    await publicarTiktok('url', 'caption', { accessToken: 'token' }, fakeFetch as typeof fetch)
  } catch {
    lanzo = true
  }
  assertEquals(lanzo, true)
})

Deno.test('publicarTiktok lanza error si la API responde con error.code distinto de ok', async () => {
  const fakeFetch = async () =>
    new Response(JSON.stringify({ error: { code: 'access_token_invalid', message: 'x' } }), { status: 200 })
  let lanzo = false
  try {
    await publicarTiktok('url', 'caption', { accessToken: 'token' }, fakeFetch as typeof fetch)
  } catch {
    lanzo = true
  }
  assertEquals(lanzo, true)
})
```

- [ ] **Step 2: Correr los tests y confirmar que fallan**

```powershell
deno test publicar-clip/tiktok_test.ts
```

Expected: FAIL, módulo `tiktok.ts` no existe.

- [ ] **Step 3: Crear `supabase/functions/publicar-clip/tiktok.ts`**

```typescript
const TIKTOK_API_BASE = 'https://open.tiktokapis.com/v2'

export interface TikTokConfig {
  accessToken: string
}

// NOTA: sin verificar contra la API real — la app de TikTok Developers no
// estaba aprobada al momento de escribir esto (ver spec, "Expectativa
// honesta sobre TikTok"). Implementado contra la documentación pública de
// la Content Posting API v2 (init con source PULL_FROM_URL). Solo se llama
// desde index.ts si PUBLICAR_TIKTOK=true.
export async function publicarTiktok(
  videoUrl: string,
  caption: string,
  config: TikTokConfig,
  fetchImpl: typeof fetch = fetch,
): Promise<string> {
  const resp = await fetchImpl(`${TIKTOK_API_BASE}/post/publish/video/init/`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${config.accessToken}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      post_info: {
        title: caption,
        privacy_level: 'PUBLIC_TO_EVERYONE',
      },
      source_info: {
        source: 'PULL_FROM_URL',
        video_url: videoUrl,
      },
    }),
  })
  if (!resp.ok) {
    throw new Error(`TikTok: error al iniciar la publicación (${resp.status}): ${await resp.text()}`)
  }
  const data = await resp.json()
  if (data.error && data.error.code && data.error.code !== 'ok') {
    throw new Error(`TikTok: la API devolvió un error: ${JSON.stringify(data.error)}`)
  }
  return data.data?.publish_id as string
}
```

- [ ] **Step 4: Correr los tests de nuevo**

```powershell
deno test publicar-clip/tiktok_test.ts
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add supabase/functions/publicar-clip/tiktok.ts supabase/functions/publicar-clip/tiktok_test.ts
git commit -m "Módulo de publicación a TikTok para publicar-clip (construido, flag apagado hasta aprobación de la app)"
```

---

## Task 9: Orquestador `publicar-clip/index.ts` + deploy + secretos + dry-run

**Files:**
- Create: `supabase/functions/publicar-clip/index.ts`

**Interfaces:**
- Consumes: `getSupabaseAdmin` (Task 4), `enviarAlerta` (Task 4), `excedeLimite` (Task 5), `obtenerAccessTokenYoutube`/`publicarYoutube` (Task 6), `publicarReel` (Task 7), `publicarTiktok` (Task 8).
- Produces: endpoint HTTP `POST /functions/v1/publicar-clip` con body `{ clip_id: string, pin: string, dry_run?: boolean }`.

- [ ] **Step 1: Crear `supabase/functions/publicar-clip/index.ts`**

```typescript
import { getSupabaseAdmin } from '../_shared/supabaseAdmin.ts'
import { enviarAlerta } from '../_shared/email.ts'
import { excedeLimite } from './pin.ts'
import { obtenerAccessTokenYoutube, publicarYoutube } from './youtube.ts'
import { publicarReel } from './instagram.ts'
import { publicarTiktok } from './tiktok.ts'

const CLAIM_EXPIRA_MINUTOS = 10
const RATE_LIMIT_VENTANA_MINUTOS = 10

Deno.serve(async (req: Request) => {
  if (req.method !== 'POST') {
    return new Response(JSON.stringify({ error: 'Método no permitido' }), { status: 405 })
  }

  let body: { clip_id?: string; pin?: string; dry_run?: boolean }
  try {
    body = await req.json()
  } catch {
    return new Response(JSON.stringify({ error: 'Body inválido, se espera JSON' }), { status: 400 })
  }

  const { clip_id: clipId, pin, dry_run: dryRun = false } = body
  if (!clipId || !pin) {
    return new Response(JSON.stringify({ error: 'Faltan clip_id y/o pin' }), { status: 400 })
  }

  const supabase = getSupabaseAdmin()

  // --- Rate limit de intentos fallidos de PIN ---
  const desde = new Date(Date.now() - RATE_LIMIT_VENTANA_MINUTOS * 60_000).toISOString()
  const { count: intentosRecientes, error: countError } = await supabase
    .from('pin_intentos')
    .select('*', { count: 'exact', head: true })
    .gte('creado_en', desde)
  if (countError) {
    return new Response(
      JSON.stringify({ error: `No se pudo chequear el límite de intentos: ${countError.message}` }),
      { status: 500 },
    )
  }
  if (excedeLimite(intentosRecientes ?? 0)) {
    await enviarAlerta(
      'Rayando el CDA: demasiados intentos de PIN',
      `Se superó el límite de intentos de PIN (${intentosRecientes} en los últimos ${RATE_LIMIT_VENTANA_MINUTOS} minutos). Alguien podría estar intentando adivinarlo.`,
    )
    return new Response(JSON.stringify({ error: 'Demasiados intentos fallidos, esperá unos minutos.' }), {
      status: 429,
    })
  }

  // --- Validar PIN ---
  const pinEsperado = Deno.env.get('PUBLISH_PIN')
  if (!pinEsperado || pin !== pinEsperado) {
    await supabase.from('pin_intentos').insert({})
    return new Response(JSON.stringify({ error: 'PIN incorrecto' }), { status: 401 })
  }

  // --- Reclamar la fila de forma atómica (evita duplicados por doble click) ---
  const expiraAntes = new Date(Date.now() - CLAIM_EXPIRA_MINUTOS * 60_000).toISOString()
  const { data: reclamada, error: claimError } = await supabase
    .from('clips')
    .update({ publicando_en: new Date().toISOString() })
    .eq('id', clipId)
    .eq('estado', 'aprobado')
    .eq('publicado', false)
    .or(`publicando_en.is.null,publicando_en.lt.${expiraAntes}`)
    .select()
    .maybeSingle()

  if (claimError) {
    return new Response(JSON.stringify({ error: `No se pudo reclamar el clip: ${claimError.message}` }), {
      status: 500,
    })
  }
  if (!reclamada) {
    return new Response(
      JSON.stringify({ error: 'El clip ya se está publicando, ya se publicó, o no está en estado aprobado.' }),
      { status: 409 },
    )
  }

  if (!reclamada.video_url) {
    await supabase.from('clips').update({ publicando_en: null }).eq('id', clipId)
    return new Response(
      JSON.stringify({
        error: 'Falta video_url en este clip (es anterior a este subsistema) — re-procesar el clip o subir el video a Storage a mano.',
      }),
      { status: 422 },
    )
  }

  if (dryRun) {
    await supabase.from('clips').update({ publicando_en: null }).eq('id', clipId)
    return new Response(
      JSON.stringify({
        dry_run: true,
        clip: reclamada,
        mensaje: 'Dry-run OK: PIN válido, clip reclamable, video_url presente. No se publicó nada real.',
      }),
      { status: 200 },
    )
  }

  const publicarYoutubeFlag = Deno.env.get('PUBLICAR_YOUTUBE') === 'true'
  const publicarInstagramFlag = Deno.env.get('PUBLICAR_INSTAGRAM') === 'true'
  const publicarTiktokFlag = Deno.env.get('PUBLICAR_TIKTOK') === 'true'

  const errores: string[] = []
  const actualizacion: Record<string, unknown> = {}

  if (publicarYoutubeFlag) {
    try {
      const accessToken = await obtenerAccessTokenYoutube({
        clientId: Deno.env.get('YOUTUBE_CLIENT_ID')!,
        clientSecret: Deno.env.get('YOUTUBE_CLIENT_SECRET')!,
        refreshToken: Deno.env.get('YOUTUBE_REFRESH_TOKEN')!,
      })
      await publicarYoutube(
        reclamada.youtube_video_id,
        reclamada.youtube_titulo || reclamada.titulo || '',
        reclamada.youtube_descripcion || '',
        accessToken,
      )
    } catch (e) {
      errores.push(`YouTube: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  if (publicarInstagramFlag && !reclamada.instagram_media_id) {
    try {
      const { data: tokenRow, error: tokenError } = await supabase
        .from('instagram_token')
        .select('access_token')
        .eq('id', true)
        .maybeSingle()
      if (tokenError || !tokenRow) {
        throw new Error('No hay token de Instagram guardado — revisar refrescar-token-instagram.')
      }
      const mediaId = await publicarReel(
        reclamada.video_url,
        reclamada.copy_instagram || '',
        reclamada.portada_url ?? null,
        {
          igUserId: Deno.env.get('INSTAGRAM_BUSINESS_ACCOUNT_ID')!,
          accessToken: tokenRow.access_token,
          containerTimeoutMs: 60_000,
        },
      )
      actualizacion.instagram_media_id = mediaId
    } catch (e) {
      errores.push(`Instagram: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  if (publicarTiktokFlag) {
    try {
      const publishId = await publicarTiktok(reclamada.video_url, reclamada.copy_tiktok || '', {
        accessToken: Deno.env.get('TIKTOK_ACCESS_TOKEN')!,
      })
      actualizacion.tiktok_publish_id = publishId
    } catch (e) {
      errores.push(`TikTok: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  if (errores.length > 0) {
    await supabase.from('clips').update({ ...actualizacion, publicando_en: null }).eq('id', clipId)
    await enviarAlerta(`Rayando el CDA: falló la publicación de un clip (${clipId})`, errores.join('\n'))
    return new Response(JSON.stringify({ error: errores.join(' | ') }), { status: 502 })
  }

  const { data: publicado, error: finalError } = await supabase
    .from('clips')
    .update({ ...actualizacion, publicado: true, publicado_en: new Date().toISOString(), publicando_en: null })
    .eq('id', clipId)
    .select()
    .single()

  if (finalError) {
    await enviarAlerta(
      `Rayando el CDA: clip ${clipId} se publicó pero no se pudo marcar publicado=true`,
      finalError.message,
    )
    return new Response(
      JSON.stringify({ error: `Se publicó pero no se pudo actualizar el registro: ${finalError.message}` }),
      { status: 500 },
    )
  }

  return new Response(JSON.stringify({ ok: true, clip: publicado }), { status: 200 })
})
```

- [ ] **Step 2: Agregar la columna `tiktok_publish_id` que usa este handler (faltó en Task 1)**

Agregar a `pipeline/supabase_migration_clips.sql`, junto a las columnas de Task 1:

```sql
alter table rayando_cda.clips add column if not exists tiktok_publish_id text;
```

Si Task 1 ya se aplicó contra el proyecto real, correr solo esta línea nueva contra Supabase (con la misma confirmación previa que Task 1 Step 3).

- [ ] **Step 3: Deploy de la función (requiere Supabase CLI instalado y logueado, `supabase link` ya hecho contra el proyecto)**

```powershell
supabase functions deploy publicar-clip
```

- [ ] **Step 4: Configurar los secretos de la función**

```powershell
supabase secrets set PUBLICAR_YOUTUBE=true PUBLICAR_INSTAGRAM=true PUBLICAR_TIKTOK=false
supabase secrets set PUBLISH_PIN=<elegir un PIN>
supabase secrets set YOUTUBE_CLIENT_ID=<del .env del pipeline> YOUTUBE_CLIENT_SECRET=<del .env del pipeline>
supabase secrets set YOUTUBE_REFRESH_TOKEN=<ver nota abajo>
supabase secrets set INSTAGRAM_BUSINESS_ACCOUNT_ID=<del .env del pipeline>
supabase secrets set RESEND_API_KEY=<de resend.com> ALERT_EMAIL_TO=<email del usuario>
```

Nota sobre `YOUTUBE_REFRESH_TOKEN`: es el `refresh_token` que ya vive dentro de `youtube_token.json` (generado la primera vez que se autorizó YouTube desde `publicar.py`) — abrir ese archivo y copiar el valor del campo `refresh_token`. **Antes de confiar en este secreto sin supervisión**, verificar el "Publishing status" del proyecto en Google Cloud Console (ver spec, sección "Verificación previa requerida") — si sigue en Testing, el refresh token vence a los 7 días y hay que pasar el proyecto a producción.

- [ ] **Step 5: Verificación dry-run contra el clip fixture de prueba**

Primero, en el dashboard de Supabase, poner temporalmente el clip fixture (`estado='prueba'`, ver `app/README.md`) en `estado='aprobado'`, `publicado=false`, y confirmar que tiene `video_url` (si no lo tiene, correr Task 2 Step 2 para subirle un video de prueba y setearle `video_url` a mano en esa fila).

```powershell
curl -X POST "https://<PROJECT_REF>.supabase.co/functions/v1/publicar-clip" `
  -H "Authorization: Bearer <ANON_KEY>" `
  -H "Content-Type: application/json" `
  -d '{"clip_id": "<id-del-fixture>", "pin": "<el-pin-que-configuraste>", "dry_run": true}'
```

Expected: respuesta 200 con `{"dry_run": true, ...}`, y en el dashboard de Supabase el clip fixture sigue con `estado='aprobado'`, `publicado=false`, `publicando_en=null` (el dry-run revierte el claim).

- [ ] **Step 6: Verificación de PIN incorrecto**

Repetir el `curl` con un PIN inventado. Expected: 401, y una fila nueva en `rayando_cda.pin_intentos`.

- [ ] **Step 7: Volver el fixture a `estado='prueba'`**

En el dashboard de Supabase, devolver el clip fixture a `estado='prueba'` (protocolo de aislamiento de datos de prueba, ver `app/README.md`).

- [ ] **Step 8: Commit**

```bash
git add supabase/functions/publicar-clip/index.ts pipeline/supabase_migration_clips.sql
git commit -m "Orquestador publicar-clip: claim atómico, PIN, rate-limit, YouTube/Instagram/TikTok, dry-run"
```

---

## Task 10: `refrescar-token-instagram` + deploy + cron + secretos

**Files:**
- Create: `supabase/functions/refrescar-token-instagram/refresh.ts`
- Create: `supabase/functions/refrescar-token-instagram/refresh_test.ts`
- Create: `supabase/functions/refrescar-token-instagram/index.ts`

**Interfaces:**
- Produces: `TokenRefrescado` (interface), `refrescarTokenInstagram(accessTokenActual, fetchImpl?): Promise<TokenRefrescado>`; endpoint HTTP `POST /functions/v1/refrescar-token-instagram` (sin body, pensado para cron).

- [ ] **Step 1: Escribir el test primero**

Crear `supabase/functions/refrescar-token-instagram/refresh_test.ts`:

```typescript
import { assertEquals, assertStringIncludes } from 'https://deno.land/std@0.224.0/assert/mod.ts'
import { refrescarTokenInstagram } from './refresh.ts'

Deno.test('refrescarTokenInstagram arma la URL correcta y calcula vence_en', async () => {
  let urlCapturada: string | undefined
  const ahora = Date.now()
  const fakeFetch = async (url: string | URL) => {
    urlCapturada = url.toString()
    return new Response(JSON.stringify({ access_token: 'token-nuevo', expires_in: 5184000 }), { status: 200 })
  }
  const resultado = await refrescarTokenInstagram('token-viejo', fakeFetch as typeof fetch)
  assertStringIncludes(urlCapturada!, 'grant_type=ig_refresh_token')
  assertStringIncludes(urlCapturada!, 'access_token=token-viejo')
  assertEquals(resultado.accessToken, 'token-nuevo')
  const venceEnMs = new Date(resultado.venceEn).getTime()
  // Debe vencer ~5184000 segundos (60 días) después de ahora, con margen de 5s por el tiempo de test.
  const esperado = ahora + 5184000 * 1000
  assertEquals(Math.abs(venceEnMs - esperado) < 5000, true)
})

Deno.test('refrescarTokenInstagram lanza error si el refresh falla', async () => {
  const fakeFetch = async () => new Response('token inválido', { status: 400 })
  let lanzo = false
  try {
    await refrescarTokenInstagram('token-viejo', fakeFetch as typeof fetch)
  } catch {
    lanzo = true
  }
  assertEquals(lanzo, true)
})
```

- [ ] **Step 2: Correr el test y confirmar que falla**

```powershell
deno test refrescar-token-instagram/refresh_test.ts
```

Expected: FAIL, `refresh.ts` no existe.

- [ ] **Step 3: Crear `supabase/functions/refrescar-token-instagram/refresh.ts`**

```typescript
export interface TokenRefrescado {
  accessToken: string
  venceEn: string
}

// Documentado en pipeline/.env.example: el token de Instagram se refresca
// sin interacción humana vía este GET, mientras no haya vencido del todo.
export async function refrescarTokenInstagram(
  accessTokenActual: string,
  fetchImpl: typeof fetch = fetch,
): Promise<TokenRefrescado> {
  const url = `https://graph.instagram.com/refresh_access_token?grant_type=ig_refresh_token&access_token=${accessTokenActual}`
  const resp = await fetchImpl(url)
  if (!resp.ok) {
    throw new Error(`Instagram: no se pudo refrescar el token (${resp.status}): ${await resp.text()}`)
  }
  const data = await resp.json()
  const expiresInSeconds = data.expires_in as number
  const venceEn = new Date(Date.now() + expiresInSeconds * 1000).toISOString()
  return { accessToken: data.access_token as string, venceEn }
}
```

- [ ] **Step 4: Correr el test de nuevo**

```powershell
deno test refrescar-token-instagram/refresh_test.ts
```

Expected: 2 passed.

- [ ] **Step 5: Crear `supabase/functions/refrescar-token-instagram/index.ts`**

```typescript
import { getSupabaseAdmin } from '../_shared/supabaseAdmin.ts'
import { enviarAlerta } from '../_shared/email.ts'
import { refrescarTokenInstagram } from './refresh.ts'

Deno.serve(async (_req: Request) => {
  const supabase = getSupabaseAdmin()

  const { data: tokenRow } = await supabase
    .from('instagram_token')
    .select('access_token')
    .eq('id', true)
    .maybeSingle()

  if (!tokenRow) {
    await enviarAlerta(
      'Rayando el CDA: no hay token de Instagram guardado',
      'La tabla rayando_cda.instagram_token está vacía. Hay que cargar un token inicial a mano (ver pipeline/README.md, sección Instagram Graph API) antes de que el refresco automático pueda seguir funcionando.',
    )
    return new Response(JSON.stringify({ error: 'No hay token guardado' }), { status: 500 })
  }

  try {
    const nuevo = await refrescarTokenInstagram(tokenRow.access_token)
    await supabase.from('instagram_token').upsert({
      id: true,
      access_token: nuevo.accessToken,
      vence_en: nuevo.venceEn,
      actualizado_en: new Date().toISOString(),
    })
    return new Response(JSON.stringify({ ok: true, vence_en: nuevo.venceEn }), { status: 200 })
  } catch (e) {
    const mensaje = e instanceof Error ? e.message : String(e)
    await enviarAlerta(
      'Rayando el CDA: falló el refresco automático del token de Instagram',
      `${mensaje}\n\nHay que renovarlo a mano: ver pipeline/README.md, sección Instagram Graph API. Este es el único caso que queda como tarea manual.`,
    )
    return new Response(JSON.stringify({ error: mensaje }), { status: 500 })
  }
})
```

- [ ] **Step 6: Deploy**

```powershell
supabase functions deploy refrescar-token-instagram
```

- [ ] **Step 7: Cargar el token inicial de Instagram en la tabla**

La tabla `instagram_token` arranca vacía — cargar el token de larga duración que ya tenés en `pipeline/.env` (`INSTAGRAM_ACCESS_TOKEN`) una única vez, a mano, desde el SQL Editor de Supabase:

```sql
insert into rayando_cda.instagram_token (id, access_token, actualizado_en)
values (true, '<pegar INSTAGRAM_ACCESS_TOKEN de pipeline/.env>', now())
on conflict (id) do update set access_token = excluded.access_token, actualizado_en = now();
```

- [ ] **Step 8: Programar el cron semanal**

En el SQL Editor de Supabase (requiere las extensiones `pg_cron` y `pg_net`, habilitables desde Database → Extensions en el dashboard si no están activas):

```sql
create extension if not exists pg_cron;
create extension if not exists pg_net;

select cron.schedule(
  'refrescar-token-instagram-semanal',
  '0 9 * * 1', -- todos los lunes a las 9:00 UTC
  $$
  select net.http_post(
    url := 'https://<PROJECT_REF>.supabase.co/functions/v1/refrescar-token-instagram',
    headers := jsonb_build_object('Authorization', 'Bearer <SERVICE_ROLE_KEY>')
  );
  $$
);
```

- [ ] **Step 9: Verificación manual**

```powershell
curl -X POST "https://<PROJECT_REF>.supabase.co/functions/v1/refrescar-token-instagram" `
  -H "Authorization: Bearer <SERVICE_ROLE_KEY>"
```

Expected: 200, `{"ok": true, "vence_en": "..."}`. Confirmar en el dashboard que `rayando_cda.instagram_token.actualizado_en` se actualizó y `vence_en` quedó ~60 días en el futuro.

- [ ] **Step 10: Commit**

```bash
git add supabase/functions/refrescar-token-instagram/
git commit -m "Edge Function programada: refresco automático semanal del token de Instagram"
```

---

## Task 11: Frontend — botón "Publicar en redes" en Historial

**Files:**
- Modify: `app/src/components/HistoryCard.jsx`
- Modify: `app/src/App.jsx:1-119`

**Interfaces:**
- Consumes: `supabase.functions.invoke` (ya expuesto por `app/src/lib/supabaseClient.js`, sin cambios ahí).
- Produces: `App.jsx` expone `handlePublicar(id, pin)`; `HistoryCard.jsx` recibe una prop nueva `onPublicar`.

- [ ] **Step 1: Agregar `handlePublicar` en `App.jsx`, después de `handleUndo` (línea 182)**

```javascript
  async function handlePublicar(id, pin) {
    const { data, error: invokeError } = await supabase.functions.invoke('publicar-clip', {
      body: { clip_id: id, pin },
    })
    if (invokeError) {
      let mensaje = invokeError.message
      if (invokeError.context) {
        try {
          const body = await invokeError.context.json()
          if (body?.error) mensaje = body.error
        } catch {
          // el body no era JSON parseable, se usa el mensaje genérico
        }
      }
      throw new Error(mensaje)
    }
    setHistoryClips((prev) =>
      prev.map((c) => (c.id === id ? { ...c, ...data.clip } : c))
    )
    return data
  }
```

- [ ] **Step 2: Pasar `onPublicar` a `HistoryCard` en el render de la pestaña Historial**

En el bloque `{!loading && !error && tab === 'historial' && historyClips.map(...)}`, agregar la prop:

```javascript
            <HistoryCard key={clip.id} clip={clip} onUndo={handleUndo} onCoverRemove={handleCoverRemove} onPublicar={handlePublicar} />
```

- [ ] **Step 3: En `HistoryCard.jsx`, agregar el estado y el handler**

Cambiar la firma del componente (línea 39):

```javascript
export default function HistoryCard({ clip, onUndo, onCoverRemove, onPublicar }) {
```

Agregar estado, junto a los `useState` existentes (después de `removingCover`):

```javascript
  const [publicando, setPublicando] = useState(false)
```

Agregar el handler, después de `handleCoverRemove`:

```javascript
  async function handlePublicar() {
    const resumen = [
      'Se va a publicar de verdad, ahora mismo:',
      '',
      `Título de YouTube: ${clip.youtube_titulo || '(sin título)'}`,
      `Copy de Instagram: ${clip.copy_instagram || '(sin copy)'}`,
      '',
      'Esto pasa el video a público en YouTube y publica el Reel en Instagram. No se puede deshacer.',
      '¿Confirmás?',
    ].join('\n')
    if (!window.confirm(resumen)) return

    const pin = window.prompt('PIN para publicar:')
    if (!pin) return

    setPublicando(true)
    setErrorMsg('')
    try {
      await onPublicar(clip.id, pin)
    } catch (err) {
      setErrorMsg(err.message || 'No se pudo publicar. Probá de nuevo.')
    } finally {
      setPublicando(false)
    }
  }
```

- [ ] **Step 4: Agregar el botón en la zona de acciones (junto al botón "Deshacer", dentro del `<div className="border-t border-border px-4 py-3 flex flex-col gap-2">` final)**

Reemplazar el bloque final del componente (desde `<div className="border-t border-border px-4 py-3 flex flex-col gap-2">` hasta el cierre de `</article>`) por:

```jsx
      <div className="border-t border-border px-4 py-3 flex flex-col gap-2">
        {errorMsg && (
          <p className="text-sm text-destructive font-medium" role="alert">
            {errorMsg}
          </p>
        )}
        {clip.estado === 'aprobado' && !clip.publicado && (
          <button
            type="button"
            onClick={handlePublicar}
            disabled={publicando}
            className="self-start flex items-center gap-1.5 text-sm font-semibold text-primary disabled:opacity-40 cursor-pointer"
          >
            {publicando ? <SpinnerGap size={15} className="animate-spin" /> : <CheckCircle size={15} weight="bold" />}
            Publicar en redes
          </button>
        )}
        {clip.publicado && (
          <span className="self-start flex items-center gap-1.5 text-sm font-semibold text-accent">
            <CheckCircle size={15} weight="fill" />
            Publicado
          </span>
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
```

(`CheckCircle` ya está importado en este archivo, se usa para el badge de "Aprobado" — no hace falta agregar el import).

- [ ] **Step 5: Verificación manual en el navegador**

```powershell
cd app
npm run dev
```

Con el clip fixture (`estado='aprobado'`, `publicado=false` temporalmente, mismo protocolo de Task 9 Step 5) visible en Historial:
1. Confirmar que aparece el botón "Publicar en redes".
2. Click → confirmar que aparece el `window.confirm` con el resumen correcto.
3. Cancelar el confirm → nada pasa.
4. Click de nuevo, confirmar, poner un PIN incorrecto → aparece el mensaje de error inline ("PIN incorrecto").
5. Click de nuevo, confirmar, poner el PIN correcto → el botón muestra el spinner, y al terminar cambia a "Publicado" (o muestra el error real si algún flag de YouTube/Instagram falla por credenciales de prueba — validar contra la respuesta de la Edge Function en la consola del navegador).
6. Devolver el fixture a `estado='prueba'`, `publicado=false` al terminar.

- [ ] **Step 6: Commit**

```bash
git add app/src/App.jsx app/src/components/HistoryCard.jsx
git commit -m "Agregar botón 'Publicar en redes' en Historial (confirmación + PIN + Edge Function)"
```

---

## Task 12: Frontend — limpiar Storage al rechazar un clip

**Files:**
- Modify: `app/src/App.jsx:108-118`

**Interfaces:**
- Consumes: `supabase.storage` (ya usado en `handleCoverRemove`).

- [ ] **Step 1: Modificar `handleReject` para borrar `video_url` de Storage best-effort, mismo patrón que `handleCoverRemove`**

Reemplazar la función `handleReject` (líneas 108-118) por:

```javascript
  async function handleReject(id, fields, notasRevision) {
    const payload = {}
    for (const key of EDITABLE_FIELDS) payload[key] = fields[key]
    payload.estado = 'rechazado'
    payload.revisado_por = reviewer
    payload.revisado_en = new Date().toISOString()
    payload.notas_revision = notasRevision || null
    const { error: updateError } = await supabase.from('clips').update(payload).eq('id', id)
    if (updateError) throw updateError

    const clip = pendingClips.find((c) => c.id === id)
    if (clip?.video_url) {
      const marker = '/object/public/clips-video/'
      const idx = clip.video_url.indexOf(marker)
      if (idx !== -1) {
        const path = clip.video_url.slice(idx + marker.length)
        try {
          await supabase.storage.from('clips-video').remove([path])
        } catch {
          // Best-effort, igual que el borrado de portadas: si falla, queda
          // un archivo huérfano ocasional en vez de bloquear el rechazo.
        }
      }
    }

    setPendingClips((prev) => prev.filter((c) => c.id !== id))
  }
```

- [ ] **Step 2: Verificación manual**

Con el clip fixture en `estado='pendiente'` y un `video_url` real (subido en Task 2/9), rechazarlo desde la pestaña Pendientes. Confirmar en el dashboard de Supabase (Storage → bucket `clips-video`) que el archivo correspondiente desapareció, y que el clip pasó a `estado='rechazado'` igual que antes. Devolver el fixture a `estado='prueba'` al terminar.

- [ ] **Step 3: Commit**

```bash
git add app/src/App.jsx
git commit -m "Borrar el video de Storage (best-effort) al rechazar un clip"
```

---

## Task 13: Verificación end-to-end real única

**Files:** ninguno (verificación manual pura, según Testing de la spec).

- [ ] **Step 1: Preparar el fixture**

En el dashboard de Supabase: clip `estado='prueba'` → `estado='aprobado'`, `publicado=false`, confirmar que tiene `video_url`, `youtube_video_id` (de un video de prueba real, no listado, que sea aceptable pasar a público brevemente) y `youtube_titulo`/`copy_instagram` con contenido claramente marcado de prueba (`[CLIP DE PRUEBA]`, como ya indica `app/README.md`).

- [ ] **Step 2: Publicar de verdad desde la app**

`npm run dev` en `app/`, ir a Historial, usar el botón "Publicar en redes" con el PIN real, confirmar.

- [ ] **Step 3: Verificar en cada plataforma**

- YouTube: el video pasó a público, con el título/descripción esperados.
- Instagram: se publicó el Reel en @rayandoelcda con el copy esperado.
- Supabase: el clip quedó `publicado=true`, `publicado_en` seteado, `instagram_media_id` presente.

- [ ] **Step 4: Limpiar el contenido de prueba publicado**

Volver el video de YouTube a no listado (o borrarlo) y borrar el Reel de prueba de Instagram — no debe quedar contenido de prueba visible públicamente.

- [ ] **Step 5: Devolver el fixture a estado de prueba**

En Supabase: `estado='prueba'`, `publicado=false`, `publicando_en=null`, `instagram_media_id=null` — mismo protocolo ya documentado en `app/README.md`.

- [ ] **Step 6: Confirmar con el usuario que el subsistema 1 queda cerrado**

No hay commit en este task (es solo verificación) — reportar el resultado y, si todo salió bien, marcar la tarea del plan como completada.

---

## Self-Review (completado antes de entregar el plan)

**Cobertura de la spec:** cada sección de `docs/superpowers/specs/2026-07-27-publicacion-final-redes-design.md` tiene tarea: migración → Task 1; subida de video en `publicar.py` → Task 2; `publicar_automatico.py` como fallback → Task 3; Edge Function `publicar-clip` (PIN, rate-limit, claim atómico, YouTube/Instagram/TikTok, dry-run, alertas) → Tasks 4-9; refresco automático de Instagram → Task 10; botón + confirmación + PIN en el frontend → Task 11; limpieza de Storage al rechazar → Task 12; verificación real única → Task 13. La columna `tiktok_publish_id` usada en Task 9 no estaba en el Task 1 original — se agregó explícitamente en el Step 2 de Task 9 en vez de dejarla como referencia suelta.

**Placeholders:** ninguno — todos los pasos de código tienen el código completo, no hay "TODO"/"similar a la tarea N".

**Consistencia de tipos/nombres:** `video_url`, `publicando_en`, `instagram_media_id`, `tiktok_publish_id`, `instagram_token.access_token` se usan con el mismo nombre en SQL, Python y TypeScript en todas las tareas donde aparecen. Las firmas de `publicarReel`, `publicarYoutube`, `publicarTiktok`, `refrescarTokenInstagram` declaradas en las Interfaces de cada tarea coinciden con cómo se llaman en Task 9/10.
