# Incidente 08–09/09/2026: el título del vertical tapado por el video, y el reproceso que recortó el clip

## Qué se vio

En clip 6 de la semana 2026-09-07 (`candidato-05`, título de portada *"Un
regreso cargado de simbolismo"*), la última línea del título quemado en la
franja superior del vertical ("SIMBOLISMO") quedaba parcialmente tapada por el
video real.

El equipo cargó el pedido en la app: *"El título queda tapado con el video en
la parte que dice 'simbolismo', ajustar."* Ese texto va al campo
`comentarios_video`, que dispara **`reprocesar_video.py`** (corrección de
in/out point). El resultado fue peor: el clip quedó recortado a 2 segundos
(00:47:47–00:47:49), subido a YouTube, pisado en Storage y con la fila de
Supabase en `pendiente` con timestamps y transcripción rotos. No se publicó a
ninguna red.

## Causas

### 1. El título no cabía en el alto de la franja (`portadas.py`)

`render_video_titulo_png` centra el título en el espacio libre bajo el logo
(~379 px con fuente 16:9 y logo arriba). `_fit_title` elegía el tamaño de
fuente mirando **sólo el ancho y la cantidad de líneas**, nunca el alto. Con 3
líneas el bloque medía ~606 px: al centrarlo, se desbordaba ~114 px hacia
abajo, sobre el video.

**Fix:** `_fit_title` acepta `max_total_height` y, cuando se pasa, exige que el
bloque completo entre en ese alto (nuevo helper `_block_height`).
`render_video_titulo_png` lo usa y además clampea el borde inferior del texto a
la altura de la franja (si un título larguísimo cae en el fallback a
`min_size`, prefiere rozar el logo antes que taparse con el video). La portada
(`compose_cover`) no cambia: sin `max_total_height` el comportamiento es el de
antes.

### 2. La IA de corrección interpretó un pedido de título como un corte (`interpretar_correccion.py`)

El pedido mencionaba *"la parte que dice simbolismo"*. El modelo tomó esa frase
como una referencia a la transcripción y *"ajustar"* como "cortá ahí", y
devolvió `confianza=true` con un rango de 2 segundos.

**Fix:** el system prompt ahora dice explícitamente que este flujo **sólo**
cambia dónde empieza/termina el clip; que pedidos sobre título, portada,
subtítulos, logo, audio o encuadre deben devolver `confianza=false` con un
motivo que diga que no es una corrección de in/out; y advierte que una frase
citada ("...en la parte que dice X") suele ser una referencia para ubicar otro
problema, no un pedido de cortar ahí.

### 3. El reproceso de subtítulos borraba el título del video (`reprocesar_subtitulos.py`)

`reprocesar_subtitulos.py` llamaba a `cortar_clip.build_vertical(carpeta,
has_subtitles=True)` **sin** `titulo_portada`, así que cada corrección de
subtítulos rearmaba el vertical sin el texto del título en la franja superior.
Bug preexistente, independiente de este incidente, pero salió a la luz acá (el
backup `v2\` del clip no tenía título).

**Fix:** se le pasa `titulo_portada`, leído de `copys.md` con el nuevo helper
compartido `cortar_clip.titulo_portada_de_copys()` (movido desde
`reprocesar_video.py`, que ya hacía lo mismo).

## Recuperación de clip 6

- Vertical reconstruido desde el backup `v2\` (28 s, subtítulos corregidos de
  René) con el fix de `_fit_title`; portadas regeneradas.
- Subido a YouTube no listado (`hMCtlvoz4Qc`); video y portada pisados en
  Supabase Storage (mismo path).
- Fila `c2ff199a-31eb-4df4-86cb-d6e07fc34372`: `timestamp_inicio=2841.3`,
  `timestamp_fin=2869.3`, `transcripcion` = `transcripcion_original` (sincro,
  442 chars), `youtube_video_id=hMCtlvoz4Qc`, `estado='pendiente'`,
  `comentarios_video` limpio. Quedó para re-revisión, no publicado.
- Quedaron 3 videos no listados viejos en YouTube para borrar a mano:
  `pvMAgWbcnNs`, `51dXTPoOtSI`, `o3oLu2jEyF4`.

## Tests

`pipeline/test_portadas_titulo.py` (nuevo): `_fit_title` respeta el alto, un
título corto no se achica de más, el PNG no dibuja bajo la franja, y el default
sin `max_total_height` no cambia. Pasan también los tests de
`interpretar_correccion`, `reprocesar_video` y `reprocesar_subtitulos`.
