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
