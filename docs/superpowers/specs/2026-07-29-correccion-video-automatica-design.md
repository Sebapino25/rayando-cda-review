# Corrección automática de video a partir del feedback editorial (subsistema 5)

Fecha: 2026-07-29
Estado: aprobado por el usuario, listo para plan de implementación

## Contexto

La app de revisión (`app/`) ya permite al reviewer pedir "Corrección de
video": el clip pasa a `estado='correccion_video'` y queda con
`comentarios_video` (texto libre, obligatorio en ese caso) describiendo qué
hay que cambiar — hoy, en la práctica, casi siempre un pedido de ajustar el
in/out point del corte (ej. "empezá 2 segundos antes", "cortá antes de que
diga tal frase").

Esa corrección hoy es 100% manual: alguien lee `comentarios_video`, vuelve a
correr `cortar_clip.py` a mano con el nuevo rango, y actualiza la fila en
Supabase. No hay ningún script que conecte el pedido con una acción.

Esto es distinto del loop de corrección de **transcripción** (texto), que sí
está resuelto: `pipeline/reprocesar_subtitulos.py` detecta filas donde
`transcripcion != transcripcion_original`, vuelve a quemar los subtítulos
corregidos y sube un video nuevo — pero se corre a mano (`--apply`), no está
enganchado al disparador automático, y no toca el in/out del corte en sí,
solo el texto de los subtítulos sobre el mismo rango ya cortado.

Con el usuario alejándose de la participación activa en el día a día del
proyecto (ver [[rayando_cda_publicacion_final_status]]), este subsistema
cierra el loop que falta: que un pedido de corrección de in/out se aplique
solo, sin que nadie tenga que volver a cortar el clip a mano.

Este es el subsistema 5 (no estaba en la auditoría original de 4
subsistemas — surgió durante el brainstorming del subsistema 3, limpieza de
documentación, que quedó pausado para priorizar esto).

## Objetivo

Que cuando un reviewer pida "Corrección de video" con un pedido de ajustar
el in/out point, el sistema:

1. Interprete el pedido (texto libre) contra la transcripción completa del
   programa y determine los nuevos timestamps.
2. Vuelva a cortar el clip desde la grabación original con ese rango nuevo
   (subtítulos, logo, portada incluidos).
3. Lo suba como un nuevo video de YouTube (no listado) y actualice la fila
   en Supabase.
4. Deje el clip en `estado='pendiente'` para una revisión fresca, avisando
   al equipo por mail.

Todo esto enganchado al disparador automático existente (subsistema 2), sin
intervención manual — salvo cuando el sistema no tiene confianza suficiente
para interpretar el pedido, caso en el que avisa solo al dueño del proyecto
y no toca nada.

## No-objetivos

- **No** cubre otros tipos de corrección de video que puedan aparecer más
  adelante (cambiar el fotograma de portada, reemplazar footage, ajustar el
  logo, etc.) — el alcance de esta primera versión es específicamente
  ajustar in/out points. Si aparecen otros patrones de pedido reales, se
  evalúan como una extensión futura.
- **No** cambia el loop de corrección de transcripción ya existente
  (`reprocesar_subtitulos.py`) — sigue siendo manual, sin cambios.
- **No** agrega campos estructurados a la UI de la app (sigue siendo texto
  libre en `comentarios_video`).
- **No** resuelve la limpieza de documentación (subsistema 3, pausado) —
  se retoma después de este subsistema.

## Arquitectura

```
auto_procesar.ps1 (loop de 5 min, ya existe — subsistema 2)
  │  además de buscar grabaciones nuevas, ahora también:
  ▼
Consulta Supabase: filas estado='correccion_video' (excluye estado='prueba')
  │
  ▼
Por cada fila: python reprocesar_video.py --apply --clip-id <id>
  │
  ├─ 1. Encuentra la carpeta local (match exacto de texto contra
  │     transcripcion_original — mismo mecanismo que reprocesar_subtitulos.py)
  │     Si no hay match único → aborta, alerta solo al dueño del proyecto.
  │
  ├─ 2. Interpretar el pedido (nuevo módulo, usa ANTHROPIC_API_KEY, mismo
  │     patrón que detectar_momentos.py/copys_ia.py): recibe
  │     comentarios_video + la transcripción completa del programa (con
  │     timestamps) → devuelve (nuevo_inicio, nuevo_fin) O una señal
  │     explícita de "sin confianza" (frase no encontrada, pedido ambiguo).
  │     Sin confianza → aborta, alerta solo al dueño del proyecto con el
  │     pedido original y el motivo.
  │
  ├─ 3. Respalda la versión anterior en vN\ (reusa
  │     respaldar_version_anterior de reprocesar_subtitulos.py).
  │
  ├─ 4. Re-corta desde video_fuente (metadata.json) con el nuevo rango,
  │     reusando las funciones de cortar_clip.py (horizontal, vertical,
  │     subtítulos, portada) — no reimplementa el corte.
  │
  ├─ 5. Valida técnicamente (publicar.validar_clip). Si falla → aborta,
  │     alerta solo al dueño del proyecto con tail del log.
  │
  ├─ 6. Sube el nuevo vertical.mp4 a YouTube (no listado, nuevo
  │     youtube_video_id) y re-sube portada/video a Supabase Storage
  │     (mismo path, upsert=true → portada_url/video_url no cambian).
  │
  └─ 7. Actualiza la fila en Supabase: youtube_video_id, timestamp_inicio,
        timestamp_fin, transcripcion + transcripcion_original (recalculadas
        para el nuevo rango), estado='pendiente', revisado_por=null,
        revisado_en=null. comentarios_video se conserva (no se borra).
        Mail al equipo: "se aplicó la corrección pedida, volvé a revisar".
```

## Componentes

### 1. Módulo de correlación fila↔carpeta (compartido)

La lógica de `encontrar_carpetas_candidatas()`/`candidata_mas_parecida()` de
`reprocesar_subtitulos.py` se extrae a un módulo compartido (o se importa
directo desde `reprocesar_video.py`) para no duplicarla — ambos scripts la
necesitan igual: match exacto de texto contra `transcripcion_original`,
nunca adivinar si hay 0 o >1 coincidencias.

### 2. Intérprete de pedidos de corrección (nuevo)

Función nueva que arma un prompt con `comentarios_video` + la transcripción
completa del programa (segmentada con timestamps, ya disponible vía
`transcribir.py`/`.json` maestro) y le pide a la API de Anthropic los nuevos
`timestamp_inicio`/`timestamp_fin` del clip. Devuelve una estructura que
distingue explícitamente "encontrado con confianza" de "no se pudo
interpretar", con el motivo en este segundo caso (para el mail de alerta).

### 3. `pipeline/reprocesar_video.py` (nuevo)

Orquesta los pasos 1-7 de la arquitectura. Dry-run por defecto, `--apply`
para ejecutar, `--clip-id` para probar contra un solo clip — mismo patrón de
CLI que `reprocesar_subtitulos.py`.

### 4. `auto_procesar.ps1` — nuevo chequeo en el loop

Se agrega, junto al chequeo de grabaciones nuevas, una consulta a Supabase
por filas `estado='correccion_video'` (excluyendo `prueba`) y, por cada una,
una llamada a `reprocesar_video.py --apply --clip-id <id>`. Reusa
`Enviar-Alerta`/`Obtener-TailLog` ya existentes (subsistema 2) para las
notificaciones.

## Manejo de errores

Como esto corre desatendido (enganchado al loop), **toda falla avisa solo al
dueño del proyecto** (nunca al equipo completo), con detalle suficiente para
resolver a mano:

| Caso | Comportamiento |
|---|---|
| La IA no tiene confianza en los nuevos in/out (frase no encontrada, pedido ambiguo) | Aborta sin tocar nada. Mail solo al dueño del proyecto con `comentarios_video` original + motivo. Clip queda en `correccion_video`. |
| No se encuentra la carpeta local, o hay más de una coincidencia | Aborta. Mail solo al dueño del proyecto (a diferencia de `reprocesar_subtitulos.py`, que solo lo imprime en consola porque hoy se corre a mano). |
| Falla el re-corte técnico (ffprobe/validación) | Aborta, no sube nada. Mail solo al dueño del proyecto con tail del log. |
| Falla la subida a YouTube o a Storage | Aborta de forma segura — la fila de Supabase no se actualiza hasta que el paso crítico completo (subida) terminó bien. Mail solo al dueño del proyecto. |
| Falta `ANTHROPIC_API_KEY` o falla la llamada a la API | Tratado como error técnico. Mail solo al dueño del proyecto, clip sin tocar. |

## Testing

Este repo no usa pytest — scripts standalone con `assert` simple (mismo
patrón que `test_transcribir_cpu_fallback.py`, `instagram_test.ts`, etc.).

- **Intérprete de pedidos**: test con el cliente de Anthropic mockeado que
  verifica (a) con un pedido claro + transcripción, devuelve los timestamps
  correctos; (b) con un pedido ambiguo o una frase que no está en la
  transcripción, devuelve la señal de "sin confianza" en vez de inventar
  algo.
- **Correlación fila↔carpeta**: si se extrae a un módulo compartido, se le
  suma un test standalone para los casos 0/1/>1 coincidencias (hoy esa
  lógica no tiene test propio; vale la pena sumarlo ahora que se reutiliza
  en un segundo lugar).
- **Camino feliz completo** (recorte real + subida a YouTube + Supabase): no
  se fabrica una verificación end-to-end contra contenido real — hoy no
  existe ningún caso real de `estado='correccion_video'` todavía. El primer
  pedido de corrección real sirve como esa verificación, mirado de cerca
  (se puede correr `reprocesar_video.py` sin `--apply` primero para ver el
  dry-run antes de que el loop lo aplique solo).
- **Aislamiento de datos de prueba**: cualquier prueba automatizada usa el
  clip fixture `estado='prueba'` existente, nunca clips reales (ver
  [[feedback_test_data_isolation]]). El propio filtro de
  `reprocesar_video.py` excluye `estado='prueba'` del procesamiento
  automático, igual que ya hace `reprocesar_subtitulos.py`.
