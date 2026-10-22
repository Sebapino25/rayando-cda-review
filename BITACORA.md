# BITÁCORA

## 22/10/2026 — Fase 0 (reconocimiento de cápsulas), rama feature/capsulas
- Sin cambios de código. Se creó la rama, esta bitácora, `limpieza_pendiente.md` y se incorporó `PLAN-CAPSULAS.md`.
- No existe `CLAUDE.md` en el repo (el plan lo da por existente): falta crearlo.
- Pipeline: tarea `RayandoCDA_AutoProcesar` (mar 00:00 a mié 10:00, cada 5 min) -> `auto_procesar.ps1` -> `transcribir.py <archivo>` + `procesar_programa.py <archivo>`.
- Corte horizontal actual: `cortar_clip.py` (`cut_horizontal` / `cut_recode`, libx264 crf18 con pad 0.4 s y fade 0.25 s) -> `horizontal_original.mp4`.
- `clips`: 28 columnas; `semana` es text; no hay `capitulo` ni `formato`.
- OBS (perfil `Rayando_el_CDA_lunes`): mkv, h264 High 1080p30, keyframe cada 8,33 s (250 frames, default NVENC).

## 22/10/2026 — Fase 1 (capítulo en todos los shorts), rama feature/capsulas
- Migración aplicada en producción (`pipeline/supabase_migration_capitulos.sql`, aditiva): tabla `rayando_cda.capitulos` (solo service_role) + `clips.capitulo`. Semilla cap. 80 = 2026-10-19; sus 4 clips quedaron con `capitulo=80`, el resto en null (fixture incluido).
- `pipeline/capitulos.py`: fecha del programa desde el nombre del mkv (martes < 06:00 = lunes anterior); lunes reusa el capítulo de esa fecha o crea MAX+1; otro día solo con `--extraordinario` / `--capitulo N`. Una fecha anterior al último capítulo sin capítulo propio NO crea uno (evita numerar mal un reproceso viejo). Si Supabase falla, los shorts salen igual sin capítulo (aviso en el log).
- `procesar_programa.py`: flags `--extraordinario`, `--capitulo N`, `--dry-run` (no corta, no llama a la IA, no sube ni escribe; muestra capítulo y descripción final con los copys.md ya generados). `cortar_clip.py` (CLI manual) también asigna capítulo.
- Descripción YouTube: `publicar.descripcion_con_capitulo` (idempotente; quita una línea/hashtag de capítulo previo). La usan publicar.py (subida), publicar_automatico.py, reprocesar_video.py, reprocesar_subtitulos.py y la Edge Function (`publicar-clip/capitulo.ts`), que antes pisaban la descripción con `youtube_descripcion` al pasar a público. La línea NO se guarda en `youtube_descripcion`: se compone al subir/publicar.
- `pipeline/corregir_capitulo.py <clip_id|fecha> <N>`: actualiza Supabase y YouTube (videos.update), con confirmación; por fecha también crea/renumera la fila en `capitulos`. Excluye qa-fixture.
- App: badge "Cap. N" (ClipCard y HistoryCard) y filtro por capítulo en Por publicar/Antiguas/Publicados (se oculta si no hay capítulos, ej. SPA). Pendientes sin cambios.
- Verificación: test_capitulos.py OK, resto de tests Python OK (salvo test_instagram_publish, que necesita credenciales reales; ya fallaba igual), deno test capitulo_test OK + deno check index.ts, build y oxlint OK, dry-run del mkv del 19/10 -> capitulo=80 y descripciones terminadas en `#RECDA80`. Vista local de la app: filtro 46 -> 3 con Cap. 80.
- Ajuste en test_reprocesar_video_rollback.py: los dobles de `publicar` ahora incluyen `descripcion_con_capitulo`.
- Nuevo `CLAUDE.md` en la raíz.
- Pendiente: merge a main + deploy de `publicar-clip` antes del lunes 26/10 23:00. Los 3 clips del cap. 80 ya públicos no tienen el hashtag en YouTube (opcional: `corregir_capitulo.py 2026-10-19 80`).

## 22/10/2026 — Fase 1 a producción + separación producción/desarrollo
- `test_instagram_publish.py` NO se corrió en main: no es prueba unitaria (publica un post real en @rayandoelcda si hay credenciales). Es idéntico en main y en la rama, no importa nada de lo cambiado, y falla en ambas por falta de `INSTAGRAM_BUSINESS_ACCOUNT_ID` en `.env`. La corrida de la sesión anterior dejó en Storage `portadas/prueba/test_instagram_publish_1792696667.jpg` (sin borrar, a la espera de Seba).
- Merge `feature/capsulas` -> `main` (9f70e9f) y push. Deploy de GitHub Pages OK (run 39840343767).
- Edge Function `publicar-clip` desplegada con `npx supabase functions deploy publicar-clip --project-ref qfxfwfcdgqcbmdspjvtk --use-api`; arranca bien (POST sin PIN -> 400 esperado).
- `corregir_capitulo.py 2026-10-19 80`: plan mostrado (4 clips, 3 públicos + 1 no listado; solo agrega "Del capítulo 80…" + `#RECDA80`), a la espera de confirmación.
- Producción `C:\Users\sebap\rayando-cda` queda en `main`. La tarea `RayandoCDA_AutoProcesar` ejecuta `C:\Users\sebap\rayando-cda\pipeline\auto_procesar.ps1`, que fija `$PipelineDir` a esa misma carpeta.
- Desarrollo: worktree `C:\Users\sebap\rayando-cda-dev` en `feature/capsulas` (fast-forward a main). Copiados: `app/.env`, `pipeline/.env`, `pipeline/youtube_token.json` (`YOUTUBE_TOKEN_FILE` es relativo). No copiados: logs, backups viejos del token, `supabase/.temp`, `deno.lock`. `npm ci` hecho en dev. Grabaciones/clips siguen en OneDrive (compartidos).
- Regla dura producción/desarrollo agregada a CLAUDE.md y PLAN-CAPSULAS.md.

## 22/10/2026 — Cierre cap. 80 + candado a la prueba en vivo de Instagram
- `corregir_capitulo.py 2026-10-19 80` corrido con confirmación de Seba: 4 videos con "Del capítulo 80 de Rayando el CDA" + `#RECDA80` (una sola vez cada uno); privacidad y categoría sin cambios.
- Borrada de Storage `portadas/prueba/test_instagram_publish_1792696667.jpg` (la dejó mi corrida anterior). Queda `test_instagram_publish_1790185986.jpg` (23/09, anterior, no se tocó).
- `test_instagram_publish.py` solo corre con `RUN_LIVE_TESTS=1`; sin eso termina con exit 0 sin tocar Storage ni Instagram. CLAUDE.md actualizado.
