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

## 30/10/2026 — Traslado audiovisual a C:\Audiovisual (Fase 3 de `C:\Proyectos\_hq\PLAN-ORDEN-2026-10-30.md`)
- Movido (mismo disco, sin borrar nada): `Escritorio\RayandoelCDA` -> `C:\Audiovisual\rayando-el-cda`; `Escritorio\19-10`, `Nueva carpeta`, `images (1).jpg` -> `rayando-el-cda\obs-recursos\`; carpetas con fecha 06-07…28-09 (10) -> `rayando-el-cda\2026\<fecha>` (junto a las de ene-jun; no a `capitulos\2026` porque `Capitulos` ya existe con los `cap N.m4a`); `C:\Siempre pasa Algo` -> `C:\Audiovisual\siempre-pasa-algo` (+ `Escritorio\Siempre pasa Algo` -> `fondos-escritorio`); `~\rayando-cda`, `rayando-cda-dev`, `spa-herramienta`, `parches-herramienta` -> `C:\Audiovisual\la-herramienta\`.
- Antes de mover: los 2.785 archivos (133 GB) tenían datos locales (ninguno solo en la nube). OneDrive se cerró durante la movida y se volvió a abrir.
- Rutas reescritas (27 archivos): `config.py`, `auto_procesar.ps1`, `auto_procesar_loop.ps1`, `registrar_tarea_programada.ps1` en producción, dev y spa; `programas/spa.json` (`base_dir`); `siempre-pasa-algo\mesa\mesa_spa.py`; `parches-herramienta\respaldar_herramienta.bat`; OBS: 4 colecciones + `.bak`, perfiles `Rayando_el_CDA_lunes`, `Rayando_Partido`, `SPA` (carpeta de grabación) y dock "Mesa Recda" en `user.ini`. Tarea `RayandoCDA_AutoProcesar` apunta a `C:\Audiovisual\la-herramienta\rayando-cda\pipeline\auto_procesar.ps1`. `git worktree repair` hecho.
- Commits "rutas tras traslado a C:\Audiovisual": main `fa40db8`, metricas-mediakit `903ceff`, multiprograma-spa `adddb30`. Sin push.
- **Pendiente: main de producción quedó adelante de origin/main (el commit de rutas + el de esta entrada). Hacer push de main antes del próximo `git pull --ff-only` en producción**, o el pull fallará.
- Prueba de aceptación OK (5/5): OBS sin fuentes en rojo y medios reproducen en las 4 colecciones (confirmado por Seba); `--dry-run` del mkv del 26/10 -> capítulo 81; tarea con ruta nueva y rehabilitada (próxima corrida mar 03/11 01:00); worktrees en rutas nuevas y `git status` limpio; selector y mesa-de-control abren desde la ruta nueva (confirmado por Seba).
- Reversión disponible: `C:\Audiovisual\_traslado\revertir.ps1` (usa `movimientos.csv`, `reemplazos.csv`, respaldos y `commits.csv`). Logs: `ejecutar.log`, `verificar.log`.
- Las rutas viejas que quedan en logs, docs, planes y entradas anteriores de esta bitácora son historial; no se tocaron.

## 30/10/2026 — Cuota de Supabase y video en YouTube (sin cambios de código)
- Org Supabase (Free), ciclo 3 oct a 3 nov: almacenamiento 1,023 de 1 GB (Recda 0,589, agencia-del-barrio 0,434); tráfico desde caché 7,28 de 5 GB (Recda 5,2, agencia 2,1). Si sigue sobre la cuota, hay restricción desde el 24 nov.
- `liberar_storage_recda.py`: el plan da 40 mp4 de `clips-video`, semanas del 2026-07-27 al 2026-09-28, sin qa-fixture. El `--apply` lo bloqueó el control de permisos; lo corrió Seba el 30/10 (40 borrados, 0 errores).
- Lo que consume tráfico: `ReproductorClip` usa el mp4 de Supabase solo si el clip no tiene `youtube_video_id`. `TikTokPublishPanel`, la descarga de `HistoryCard` y la publicación en IG/TikTok (que toman la URL directa) también leen el mp4 desde Supabase.
- Decisión de Seba: YouTube no listado como archivo permanente también para SPA (canal propio, ya verificado) y proyecto de Google Cloud aparte para SPA. Supabase queda solo como paso temporal hasta publicar en IG/TikTok. Quedó como A2b en `PLAN-UNIFICACION-Y-SERVICIO.md`.

## 30/10/2026 — A1a: unificación Recda + SPA, rama `unificacion` (en `rayando-cda-dev`)
- `metricas-mediakit` quedó como estaba (sin commits nuevos; sigue fuera de main). Rama nueva `unificacion` desde `multiprograma-spa` (que no se tocó) + merge de `main` (`0a401d8`). Conflictos: la app se tomó entera de main (es la desplegada; `app/` queda idéntica a main); `config.py` con el bloque multiprograma; `publicar.py`, `cortar_clip.py`, `reprocesar_video.py` y `reprocesar_subtitulos.py` combinan `SUBIR_YOUTUBE`/`PROGRAMA_NOMBRE`/`--sin-publicar` con `descripcion_con_capitulo`.
- `--programa rayando|recda|spa` en todos los scripts de entrada (`programa_cli.py`, importado antes de config; solo fija la variable `PROGRAMA`, que sigue funcionando). `recda` es alias de `rayando` (nombre interno sin cambios). `programas/rayando.json` solo informativo (redes, día, tarea); prohibido que traiga `config`. Constantes nuevas `REDES` y `DIA_PROGRAMA` (spa: youtube, jueves). (`c72564b`)
- Red de seguridad: `test_config_rayando_foto.py` compara las 100 constantes de config de main (`fixtures/config_rayando_main.json`, sacada de `764edb9`) con las de la rama, sin PROGRAMA, con `rayando` y con `recda`. Las únicas claves nuevas están declaradas con su valor para Recda. Dry-run del 19/10 (cap. 80) y del 26/10 (un partido en `grabaciones-partidos`; el dry-run propone cap. 81, pero ese día no hubo programa) con el código de main y el de la rama: salida idéntica, línea por línea.
- A2b (`191d7d9`): SPA sube a su propio YouTube (`SUBIR_YOUTUBE=true` en `spa.json`). Para un programa que no es Rayando, `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET` y `YOUTUBE_TOKEN_FILE` tienen que estar en su `.env.<programa>` (no se heredan de `.env`); si faltan o no hay token, el clip se revisa desde Storage como hasta ahora y los shorts no se frenan. `YOUTUBE_CANAL_ID` (perfil) verifica que el token sea del canal correcto antes de subir. `autorizar_youtube.py --programa spa` autoriza una vez y muestra el id del canal.
- Borrado del mp4 tras publicar (los dos programas): `limpiar_clips.py` libera el mp4 de Storage de los clips publicados hace 7+ días (`BORRAR_VIDEO_PUBLICADO_DIAS=7`, por TikTok a mano) y deja `video_url` en NULL; no toca fila, portada ni YouTube; excluye qa-fixture. `--sin-liberar-videos` lo apaga. `--mantener-capitulos` (SPA) ya no borra publicados. Plan en dry-run hoy: 7 mp4 de Recda (semanas 05/10 y 19/10), 0 de SPA. App: aviso cuando un clip no tiene YouTube ni mp4.
- Tests: todos los scripts OK; `pytest test_programas.py` 9/9; build de la app OK. `.env.spa` copiado de `spa-herramienta` a dev (no versionado).
- Capítulos: el 26/10 no hubo programa (fútbol), así que la tabla en 80 está bien y el lun 2/11 sale el 81 (confirmado por Seba). Ojo: no correr `procesar_programa.py` con el mkv del partido del 26/10 (lunes), porque crearía el cap. 81 con esa fecha.
- Fuera de A1a (A1b): capítulos de SPA (tabla en su schema; hoy SPA sale sin capítulo, aviso en el log), tarea `SPA_AutoProcesar`, bloqueo general de credenciales heredadas.

## 04/11/2026 — Verificación antes del merge de `unificacion` a main
- main no avanzó desde `764edb9`: el paso a main es fast-forward. Dry-run del cap. 81 real (mkv del 02/11) y del cap. 80 con el código de main y el de la rama: salida idéntica. Test foto y todos los tests OK.
- Prueba real de SPA sin publicar (`cortar_clip.py ... --sin-publicar --programa spa`, 25 s del cap. 5): vertical 1080x1920 con layout dividido, logo, subtítulos, portadas y copys con hashtags de SPA. La carpeta de prueba se borró.
- `rehacer_vertical.py` (lo usan también `recortar_clip.py`): ahora que SPA tiene YouTube, si el clip no está publicado sube el vertical corregido y actualiza `youtube_video_id`, porque la app reproduce desde YouTube y si no seguiría mostrando el video viejo. El anterior no se borra (queda no listado, igual que `reprocesar_subtitulos.py`). Prueba: `test_rehacer_vertical.py`.
- `limpiar_clips.py` en dry-run hoy: 7 mp4 de Recda y 11 de SPA (publicados del 22/10) por liberar.