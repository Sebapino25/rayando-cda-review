# La Herramienta — Rayando el CDA

Pipeline que corta los shorts del programa de los lunes, los sube a YouTube (no listado) y los registra en Supabase para revisión en una app web. Plan vigente: `PLAN-CAPSULAS.md`; diario de cambios: `BITACORA.md`.

## Stack
- `pipeline/`: Python 3.12 (Windows, PC de Seba). ffmpeg, faster-whisper, API de Anthropic (detección y copys), API de YouTube, supabase-py. Config en `pipeline/config.py`; secretos en `pipeline/.env`.
- `app/`: React + Vite + Tailwind. GitHub Pages; despliega solo al hacer push a `main` (`.github/workflows/deploy.yml`). Lee Supabase con la anon key. Una app para dos programas (`?p=spa`).
- `supabase/functions/`: Edge Functions en Deno (`publicar-clip` publica con PIN en YouTube/IG/TikTok). Se despliegan a mano, no con el push.
- Supabase: proyecto "La Herramienta Rayando el CDA" (`qfxfwfcdgqcbmdspjvtk`), schema `rayando_cda` (tablas `clips`, `capitulos`, tokens). Migraciones como `.sql` idempotentes en `pipeline/`.

## Cómo corre
- Tarea programada `RayandoCDA_AutoProcesar` (mar 00:00 a mié 10:00, cada 5 min) -> `pipeline/auto_procesar.ps1` -> `transcribir.py <mkv>` + `procesar_programa.py <mkv>`; después `reprocesar_video.py`, `reprocesar_subtitulos.py` y `limpiar_clips.py`.
- Grabaciones OBS en `C:\Users\sebap\OneDrive\Escritorio\RayandoelCDA\grabaciones` ("AAAA-MM-DD HH-MM-SS.mkv"); clips en `...\clips\<fecha>\candidato-NN\`.
- Capítulo: `pipeline/capitulos.py` (lunes = MAX+1, martes antes de 06:00 = lunes anterior). La línea "Del capítulo N…" y `#RECDA<N>` los pone el código (`publicar.descripcion_con_capitulo` y `publicar-clip/capitulo.ts`), nunca la IA.

## Comandos
- Pruebas Python: `cd pipeline; python test_<nombre>.py` (cada test es un script). `test_instagram_publish.py` es una prueba EN VIVO (publica en @rayandoelcda): sin `RUN_LIVE_TESTS=1` se omite; nunca activarla sin pedido de Seba.
- Pruebas Deno: `cd supabase/functions; deno test publicar-clip/`
- App: `cd app; npm run build; npx oxlint src`
- Dry-run del pipeline (no corta ni sube nada): `python procesar_programa.py "<mkv>" --dry-run`
- Programa fuera de lunes: `--extraordinario` o `--capitulo N`. Corregir capítulo: `python corregir_capitulo.py <clip_id|AAAA-MM-DD> <N>` (pide confirmación; toca Supabase y YouTube).
- Deploy Edge Function: `supabase functions deploy publicar-clip` (o la MCP de Supabase).

## Reglas duras
- Producción = C:\Users\sebap\rayando-cda en main (lo usa el Task Scheduler). Desarrollo = C:\Users\sebap\rayando-cda-dev. Nunca cambiar de rama ni desarrollar en la carpeta de producción. (dev es un git worktree de la misma repo; producción solo recibe `git pull --ff-only` de main; `auto_procesar.ps1` tiene la ruta de producción fija.)
- No mover rutas existentes (grabaciones, clips, buckets, nombres de carpetas).
- No romper los shorts: cualquier cambio al pipeline se verifica con las pruebas y un `--dry-run`. Lo nuevo (capítulo, cápsulas) nunca debe frenar la salida de shorts.
- No tocar el schema `siempre_pasa_algo` (SPA) ni su app.
- Excluir siempre la fila de prueba `semana = 'qa-fixture'` (estado `prueba`) de barridos, limpiezas y correcciones.
- Migraciones solo aditivas (`add column if not exists`, tablas nuevas). Nada de drop/rename en `clips`.
- Nada se publica ni se borra en YouTube/IG/TikTok sin confirmación explícita de Seba.
- El capítulo no se edita en la app; se corrige con `corregir_capitulo.py`.
- Trabajo en ramas; merge a `main` solo cuando Seba lo pide. Anotar cada sesión en `BITACORA.md`.
