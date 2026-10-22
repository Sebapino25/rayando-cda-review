# PLAN-CAPSULAS — Cápsulas horizontales por temática + orden por capítulo

**Proyecto:** La Herramienta Rayando el CDA · Repo `Sebapino25/rayando-cda-review` · Local `C:\Users\sebap\rayando-cda`
**Rama:** `feature/capsulas` (la Fase 1 se mergea a `main` antes del lunes 26/10)
**Fecha del plan:** 22/10/2026

## Objetivo
1. Que todos los videos (shorts y cápsulas) queden ordenados por capítulo desde el **capítulo 81 (lunes 26/10/2026)**.
2. Que el pipeline, además de los shorts, genere solo **cápsulas horizontales por temática** (5 a 10 min, techo 15), con portada base, 3 opciones de título vendibles con respaldo, y una pestaña "Horizontales" en la app de revisión (junto a "Verticales", que son los shorts actuales).

## Hitos
- **Lunes 26/10, 23:00 (cap. 81):** Fase 1 en producción. Los shorts del cap. 81 salen con su capítulo.
- **Lunes 02/11 (cap. 82):** primeras cápsulas reales generadas por el pipeline (Fases 2 a 6 cerradas).
- **Después:** auditoría opcional con Fable → replicar en SPA cuando SPA entre al pipeline.

## Decisiones tomadas (no reabrir sin motivo)
- Las cápsulas corren **automáticas**, en el mismo pipeline, después de los shorts.
- La IA decide cuántas, con **tope 6**. Puede devolver menos (incluso 2) si no hay temas que se sostengan solos. Los shorts mantienen tope 8.
- Es un **corte directo** del video de OBS: sin reencuadre, blur, zona de título ni margen de 125 px.
- **Se recodifica con NVENC** (no copia sin recodificar): corte exacto, audio normalizado, fade de entrada y salida. El modo copia queda como opción en la config.
- **Duración:** objetivo 5 a 10 min, techo duro 15. Pasar de 10 exige justificación escrita del modelo y aparece con un aviso en la app. Las cápsulas de más de 8 min llevan capítulos con marcas de tiempo en la descripción.
- **Subtítulos:** no se queman en el video. Se sube el SRT a YouTube como pista de subtítulos.
- **YouTube:** misma cuenta. Se sube como no listado y se publica desde la app con PIN, igual que los shorts.
- **Títulos:** 3 opciones por cápsula (farandulesco, de dato, de pregunta). Se permiten adjetivos grandilocuentes. **Nunca** cifras, cargos, logros, nombres o datos que no estén dichos en el video. Cada título lleva un **respaldo**: la cita textual y el minuto que lo sostiene. René o Cristián eligen o ajustan.
- **Invitado:** la IA propone el nombre a partir de la transcripción y el diccionario de nombres propios. Quien revisa lo confirma en la app antes de publicar.
- **Ejemplos de títulos:** tabla en Supabase, editable desde la app. Cada título elegido o ajustado queda guardado como ejemplo para el prompt.
- **Capítulo:**
  - Solo cuentan los programas de los lunes. La primera grabación de un lunes (o de la madrugada del martes, antes de las 06:00) recibe el número del último capítulo + 1. No hay hora mínima el lunes: un ensayo de la tarde crea el capítulo y el programa de la noche lo reusa (misma fecha).
  - Varios archivos de la misma noche comparten el capítulo. Reprocesar no suma.
  - La fecha del programa sale del nombre del mkv (inicio de grabación). Si empezó un martes antes de las 06:00, cuenta como el lunes anterior.
  - Los capítulos viven en la tabla `rayando_cda.capitulos` (numero único, fecha única, tipo `normal`/`extraordinario`); `clips.capitulo` guarda el número.
  - Un programa extraordinario (por ejemplo, un miércoles) se marca con `--extraordinario` (crea MAX+1) o `--capitulo N` (fuerza uno existente). Sin esa marca, no recibe número.
  - El número **no** es editable en la app (solo se muestra y se filtra). Se corrige con `pipeline/corregir_capitulo.py <clip_id|fecha> <N>`, que actualiza Supabase y la descripción en YouTube, previa confirmación.
  - En YouTube: la línea "Del capítulo 81 de Rayando el CDA" y el hashtag `#RECDA81` al final de la descripción. Los pone el código de forma determinista (no la IA), también al pasar a público. No se crean listas de reproducción por capítulo.
- **Config por programa:** el código nuevo no escribe "Rayando" a fuego. Schema, rutas, duraciones, reglas de título y hashtag salen de un archivo de configuración por programa. SPA queda **fuera de alcance** de este plan.
- La unificación de carpetas audiovisuales va **después** de este plan. No mover rutas durante este trabajo.

## Estructura: misma herramienta, separada por dentro
No se crea una herramienta ni un repo aparte. Las cápsulas son otro formato del mismo programa y comparten grabación, transcripción, diccionario, tabla `clips`, app y conexión a YouTube.
- **Código:** carpeta propia dentro del repo (ej. `horizontales/`) para corte, detección y títulos de cápsulas. El código de shorts solo se toca en la Fase 1 (capítulo).
- **Archivos generados:** los MP4 de cápsulas van a una carpeta nueva, hermana de la de shorts. No se mueve ninguna ruta existente.
- **Datos:** misma tabla `clips`, separada por la columna `formato`.
- **App:** una sola app con dos pestañas, "Verticales" y "Horizontales".

## Fases

### Fase 0 — Reconocimiento (sin cambios de código)
**Modelo:** Sonnet · **Sesión:** conversación nueva
- Leer el repo y reportar:
  - cómo se disparan hoy el pipeline (Task Scheduler) y el procesamiento;
  - dónde está el código que cortaba en horizontal;
  - columnas actuales de `rayando_cda.clips`;
  - cómo `copys_ia.py` arma títulos y descripciones;
  - qué llamadas hace a la API de YouTube;
  - cómo la app lee y agrupa los clips.
- Revisar el perfil de OBS "Rayando Lunes": formato de grabación (mkv/mp4), códec e intervalo de keyframes.
- Verificar que existan `CLAUDE.md` y `BITACORA.md`. Si falta `BITACORA.md`, crearla.
- Listar (sin borrar) los clips no publicados y rechazados, con su id de YouTube, para la limpieza (ver Anexo).
- **Listo cuando:** existe un reporte con todo lo anterior y `PLAN-CAPSULAS.md` está en la raíz del repo.

### Fase 1 — Capítulo en todos los videos ⏰ antes del lunes 26/10
**Modelo:** Opus · **Sesión:** /clear antes
- Migración aditiva (`pipeline/supabase_migration_capitulos.sql`): tabla `rayando_cda.capitulos` + columna `capitulo` (int, nullable) en `clips`. Semilla: cap. 80 = 19/10/2026, y sus clips con `capitulo=80`; el resto queda en null.
- `pipeline/capitulos.py`: lógica de asignación (reglas de arriba) con pruebas de fechas en `test_capitulos.py`. `procesar_programa.py` suma `--extraordinario`, `--capitulo N` y `--dry-run`.
- Descripción de YouTube: `publicar.descripcion_con_capitulo` agrega la línea y el hashtag por código (no en `copys_ia.py`, no vía IA). La Edge Function `publicar-clip` (`capitulo.ts`), `publicar_automatico.py` y los re-subidas (`reprocesar_video.py`, `reprocesar_subtitulos.py`) los conservan al reescribir la descripción. Instagram y TikTok: fuera de alcance.
- `pipeline/corregir_capitulo.py`: comando de corrección (Supabase + YouTube `videos.update`), con confirmación.
- App: "Cap. N" en cada clip y filtro por capítulo en Por publicar, Antiguas y Publicados. No editable. Pendientes no cambia.
- **Fuera de alcance:** cualquier cosa de cápsulas, columna `formato`, config por programa.
- **Listo cuando:** procesar una grabación de prueba con fecha de lunes asigna 81. Reprocesarla sigue en 81. La descripción muestra el hashtag. La app filtra por capítulo. Los shorts siguen saliendo igual que antes.
- **Para producción:** merge a `main` (despliega la app) + deploy de la Edge Function `publicar-clip`, ambos antes del lunes 26/10 23:00. La migración ya está aplicada.

### Fase 2 — Config por programa + corte horizontal desde JSON manual
**Modelo:** Opus · **Sesión:** /clear antes
- Archivo de config por programa (Rayando por ahora).
- Columna `formato` (`short` | `capsula`) en `clips`; los existentes quedan como `short`.
- Script que recibe un JSON de tiempos escrito a mano (inicio, fin, tema) y corta con NVENC: audio normalizado, fade de entrada y salida, mismo encuadre de OBS.
- **Listo cuando:** René elige 2 tramos del cap. 80 a mano y recibe 2 MP4 horizontales correctos, y los shorts no cambian.

### Fase 3 — Detección por tema
**Modelo:** Sonnet · **Sesión:** /clear antes · **Prompt:** se diseña en el chat antes de esta fase.
- Una sola pasada sobre la transcripción completa (la que ya existe), con Sonnet vía API.
- Devuelve hasta 6 bloques con inicio, fin, tema, por qué se sostiene solo y la justificación si pasa de 10 min. Las cápsulas no se pueden solapar entre sí.
- Guarda `candidatos_capsulas.json`, igual que los shorts, para no re-detectar.
- **Listo cuando:** corre sobre el cap. 80 y los cortes empiezan y terminan en frases completas.

### Fase 4 — Títulos, copy e invitado
**Modelo:** Sonnet · **Sesión:** /clear antes · **Prompt:** se diseña en el chat antes de esta fase.
- 3 títulos por cápsula con respaldo (cita y minuto), descripción con capítulos si dura más de 8 min, hashtag de capítulo y nombre de invitado propuesto.
- Tabla `rayando_cda.titulos_ejemplo` y uso de esos ejemplos en el prompt.
- **Listo cuando:** ningún título del cap. 80 afirma un dato sin respaldo.

### Fase 5 — App: pestañas "Verticales" / "Horizontales" + portada base
**Modelo:** Sonnet · **Sesión:** /clear antes
- La vista actual de shorts pasa a llamarse "Verticales" (sin cambiar su funcionamiento). Pestaña nueva "Horizontales": video, 3 títulos con su respaldo, elegir o editar, confirmar el invitado, aviso si pasa de 10 min, aprobar o rechazar.
- Portada base de 1280×720 (frame sugerido) para que René la termine en Canva, y forma de subir la portada final.
- Guardar el título elegido como ejemplo.
- **Listo cuando:** Cristián puede revisar y aprobar una cápsula de punta a punta en la app.

### Fase 6 — Subida y publicación
**Modelo:** Opus · **Sesión:** /clear antes
- Integrar las Fases 2 a 4 al pipeline automático después de los shorts.
- Subida no listada + SRT como pista de subtítulos.
- "Publicar" con PIN: título elegido, portada final, público.
- Manejo de errores igual que en los shorts (si una cápsula falla, no frena las demás).
- **Listo cuando:** una grabación de prueba genera shorts y cápsulas solos, y una cápsula se publica desde la app.

### Fase 7 — Prueba real (cap. 82) y ajuste
**En el chat:** revisar con René y Cristián qué cápsulas sirvieron, ajustar prompts y duración, y decidir si vale la pena la auditoría con Fable antes de SPA.

## Riesgos
- **Romper los shorts:** todo en rama; cada fase verifica que los shorts sigan iguales.
- **Capítulo mal asignado** (ensayos de lunes, cortes de OBS): reglas de arriba + `corregir_capitulo.py`.
- **Cuota de YouTube:** en principio de sobra (100 subidas al día desde dic. 2025). Se confirma en la Fase 0.
- **Portada por API:** requiere el canal verificado. Se confirma en la Fase 0.
- **Títulos que prometen de más:** respaldo obligatorio + revisión humana.

## Anexo — Limpieza de no publicados (opcional, fuera de las fases)
Script que, con la lista de la Fase 0 y tu confirmación explícita, borra cada video en YouTube **y** su registro en `clips` (o lo marca como eliminado), para no dejar registros huérfanos en la app. Es irreversible: correr solo después de revisar la lista.
