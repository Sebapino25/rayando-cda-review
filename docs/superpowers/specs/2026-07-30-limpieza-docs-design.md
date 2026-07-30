# Limpieza de documentación desactualizada (subsistema 3)

Fecha: 2026-07-30
Estado: listo para plan de implementación

## Contexto

Los subsistemas 1 (publicación final a redes), 2 (disparador automático) y 5
(corrección automática de video) ya están implementados y en producción (ver
[[rayando_cda_publicacion_final_status]]), pero varios documentos del repo
nunca se actualizaron para reflejarlo — quedaron describiendo un estado del
proyecto que ya no es cierto, o simplemente no mencionan piezas del sistema
que hoy son centrales. Esto se auditó en dos pasadas (2026-07-29 y
2026-07-30, esta última reverificando que nada de esto se haya resuelto de
paso durante el trabajo del subsistema 5).

## Hallazgos (alcance de este subsistema)

1. **`pipeline/README.md` — "Estado del proyecto"** (línea 7-13): dice
   "Fase 1 implementada", solo procesamiento manual, "todavía no hay
   publicación automática a Instagram/TikTok ni publicación final a
   YouTube". Falso hoy: los subsistemas 1, 2 y 5 ya lo resuelven.
2. **Mismo README, diagrama "Flujo del sistema"** (línea 39-40): la nota
   final marca la publicación como "fase futura" — también desactualizada.
3. **Mismo README, sección "Uso"**: solo documenta el flujo manual
   clip-por-clip (`cortar_clip.py`). No menciona `procesar_programa.py` (el
   orquestador que detecta candidatos y corta/publica un programa entero
   sin intervención manual) ni `detectar_momentos.py` — el corazón real del
   subsistema 2, hoy solo nombrados de pasada en "Disparador automático".
4. **Mismo README, sección "Próximos pasos (fuera de la Fase 1)"** (línea
   494-501): sus dos únicos ítems ("detección automática de momentos" y
   "publicación final a Instagram/YouTube público") ya están hechos —
   hallazgo nuevo de esta segunda pasada. Solo TikTok sigue realmente
   pendiente (código construido, flag apagado, falta resubmitir el
   Developer App — ver [[rayando_cda_publicacion_final_status]]).
5. **Mismo README, "Disparador automático"**: falta una nota de
   troubleshooting sobre Avast poniendo en cuarentena
   `auto_procesar_loop.ps1`/`registrar_tarea_programada.ps1` (ya pasó una
   vez, commit `2182949`) — mismo patrón que la nota de Avast/SSL que ya
   existe en "Instalación", pero un problema distinto (cuarentena de
   archivo, no intercepción SSL).
6. **`pipeline/.env.example`**: falta `ANTHROPIC_API_KEY`, requerida por
   `detectar_momentos.py`, `copys_ia.py` e `interpretar_correccion.py`. No
   es solo texto desactualizado — bloquearía configurar el pipeline en una
   PC nueva siguiendo el README al pie de la letra.
7. **`app/README.md` — tabla "Columnas esperadas"**: no incluye las
   columnas de publicación que ya usa el botón "Publicar en redes"
   (`publicado`, `publicado_en`, `video_url`, `publicando_en`,
   `portada_url`, `instagram_media_id`, `tiktok_publish_id`).
8. **`pipeline/CAMBIOS.md`**: es un changelog histórico (portadas/copys,
   06/07-09/07) que nunca sumó una entrada para los subsistemas 1, 2 y 5.

`supabase_migration_clips.sql` se revisó y está al día (ya documenta su
propio drift) — no necesita cambios.

## Alcance

4 archivos, todos de texto/documentación/config — ningún cambio de lógica
de código:
- `pipeline/README.md` (hallazgos 1-5)
- `pipeline/.env.example` (hallazgo 6)
- `app/README.md` (hallazgo 7)
- `pipeline/CAMBIOS.md` (hallazgo 8)

## Contenido por archivo

**`pipeline/README.md`:**
- "Estado del proyecto" → reescribir sin el framing de "Fase 1": describir
  el pipeline de punta a punta (detección automática o lista confirmada →
  corte → publicación no listada a YouTube, disparado solo cada 5 minutos)
  más publicación final (pública) a YouTube/Instagram vía botón en la app,
  más corrección automática de video. Único pendiente real: TikTok.
- Diagrama "Flujo del sistema" → quitar la nota "(fase futura: ...)",
  reemplazar por una línea que indique que ese paso ya ocurre (aprobación
  en la app → botón "Publicar en redes", ver `app/README.md`).
- Nueva sección "Procesamiento automático de un programa completo" (después
  de "2. Cortar un clip", antes de "## Publicación"): explica
  `procesar_programa.py`, `detectar_momentos.py`, el JSON de candidatos
  confirmados (`candidatos_<fecha>.json`), y referencia cruzada a
  "Disparador automático" más abajo.
- "Disparador automático" → agregar nota de troubleshooting sobre
  cuarentena de Avast en los scripts de Task Scheduler, con la solución ya
  aplicada (excepción en Avast + restaurar desde git).
- "Próximos pasos" → renombrar a algo sin el framing de fase (ej.
  "Pendiente") y dejar solo TikTok como ítem real.

**`pipeline/.env.example`**: agregar bloque `--- Anthropic (detección de
candidatos, copys e interpretación de correcciones, todo por IA) ---` con
`ANTHROPIC_API_KEY=` y una línea de qué scripts la usan.

**`app/README.md`**: agregar a la tabla de columnas: `publicado`,
`publicado_en`, `video_url`, `publicando_en`, `portada_url`,
`instagram_media_id`, `tiktok_publish_id`, con tipo y una nota corta de qué
las llena.

**`pipeline/CAMBIOS.md`**: nueva entrada al tope
(`# Cambios aplicados — publicación final, disparador automático y
corrección de video (27-30/07)`) resumiendo los tres subsistemas, mismo
formato que las entradas existentes.

## No-objetivos

- No se toca `supabase_migration_clips.sql` (ya está al día).
- No se documenta el subsistema 4 (difusión/monetización) porque todavía
  no existe — no hay nada que describir.
- No se resuelve TikTok (Developer App) — solo se documenta como pendiente,
  igual que ya está en memoria/otros specs.
- No hay cambios de código, solo de documentación/config.

## Testing

Ningún test automatizado aplica (son archivos de texto/documentación). La
única "verificación" es releer cada sección modificada contra el código
real después de escribirla, y confirmar que `pipeline/.env.example` sigue
siendo válido como plantilla (no rompe `cp .env.example .env`).
