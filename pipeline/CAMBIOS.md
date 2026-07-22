# Cambios aplicados — rediseño de portadas v2 (09/07)

Feedback que originó este cambio: las portadas v1 no funcionaban como
"gancho" — fotograma al azar (salió uno con los ojos cerrados), título
demasiado largo (el "título SEO" completo, pensado para SEO/YouTube, no para
gritar en 2 segundos de scroll) y tipografía plana (Impact del sistema). Se
rediseñó el sistema completo con nuevas reglas permanentes de diseño.

## 1. Titular corto y gritado (nuevo campo `titulo_portada`)

Se agregó el campo `titulo_portada` a `copys.md` y a `clip_overrides.json`:
titular de máximo 5-6 palabras en MAYÚSCULAS, editable a mano. Si un clip no
lo tiene curado, se genera automáticamente recortando el título SEO a las
primeras 6 palabras (fallback, funciona para clips futuros sin curación).

Titulares escritos a mano para los 5 clips del 06/07 (leyendo la
transcripción/contexto de cada uno):

| Clip | `titulo_portada` | `palabra_clave` |
|---|---|---|
| arbitraje-indecente-wanderers | ¡ARBITRAJE INDECENTE! | INDECENTE |
| capitan-influencer | ¿MUSRRI VS INFLUENCER? | MUSRRI |
| hype-catolica | ¡QUEREMOS EL CLÁSICO! | CLÁSICO |
| oro-panamericanos | ¡ORO CON CRISIS DE PÁNICO! | ORO |
| polemica-nico-castillo | ¿CUÁNTAS PATADAS PA ESTE? | PATADAS |

`palabra_clave` se fijó a mano en los 5 (en vez de dejar la auto-detección)
para tener control editorial total sobre qué palabra se destaca en amarillo;
es opcional, con fallback automático (palabra más larga del titular que no
sea muletilla) para clips nuevos.

## 2. Tipografía: Anton (Google Fonts)

Se descargó `Anton-Regular.ttf` (Google Fonts, licencia SIL Open Font
License 1.1, libre para uso comercial) a `Proyecto\fonts\`. Condensada,
mayúsculas gruesas, pensada para titulares gritados — reemplaza a Impact del
sistema. Se usa tanto para el titular como para la franja de marca inferior.
El tamaño de fuente se calcula como fracción del alto del canvas (no
píxeles fijos), para que escale igual en la vertical (1080×1920) y la
horizontal (1280×720) sin invadir nunca el logo — bug real que apareció en
la primera prueba (el titular se dibujaba con un tamaño pensado para la
vertical y tapaba el logo en la horizontal) y se corrigió antes de generar
los clips finales.

## 3. Jerarquía de color y franja diagonal

Texto principal blanco con contorno/sombra negra gruesa (`stroke_width` de
Pillow). La palabra clave del titular se destaca en amarillo `#FFD700`.
Detrás del bloque de texto se dibuja una franja diagonal azul marino
semitransparente para legibilidad sobre cualquier fondo, en vez del
degradado oscuro plano de la v1.

## 4. Selección de fotograma con criterio (en vez de al azar)

`portadas.py` (módulo nuevo) extrae 7 fotogramas distribuidos en el clip
(saltando el 8% inicial/final) y los puntúa con heurísticas simples:
nitidez (varianza del Laplaciano) + detección de rostro y ojos abiertos
(Haar cascades de OpenCV — `opencv-python-headless`, nuevo en
`requirements.txt`). Un rostro detectado sin ojos visibles (pestañeo,
perfil) resta puntaje en vez de sumar, así se evita justamente el problema
original ("salió uno con los ojos cerrados"). El mejor candidato se usa
automáticamente.

**Ajuste durante las pruebas:** con los parámetros por defecto de OpenCV
(`minNeighbors=5`, `minSize=(60,60)`), el detector de rostro daba falsos
positivos en texturas/fondos (se probó en `oro-panamericanos`, un clip cuyo
video fuente es una captura de pantalla del streaming de los Panamericanos:
el "rostro" detectado caía sobre una pared verde vacía, y la portada
resultante recortaba una franja sin nada interesante). Se subió
`minNeighbors` a 8 y `minSize` a una fracción del ancho del frame (4.5%) en
vez de un valor absoluto — con eso el detector encontró los rostros reales
(los panelistas en las cámaras reactivas) y el recorte automático mejoró
notoriamente. Documentado en `portadas.py` (`_score_frame`).

También se agregó recorte con foco en el rostro: cuando el fotograma
elegido tiene un rostro detectado, el recorte a 9:16/16:9 se centra
horizontalmente en ese rostro en vez de en el centro geométrico de la
imagen — antes, en formatos de videollamada con varios paneles, el recorte
centrado agarraba una franja sin nada relevante aunque el rostro estuviera
más al costado.

`portada_candidatas.jpg` (nuevo, uno por clip): contact sheet con los 4
mejores candidatos numerados (nitidez/rostro/ojos/score de cada uno) + una
fila de vista previa en miniatura al 20% de la portada real, para juzgar si
el titular se lee bien "en el feed" antes de publicar. Para usar otro
candidato, el número del contact sheet se anota como `frame_portada` en
`clip_overrides.json`.

## 5. Composición "VS"

Cuando el titular contiene "vs" (o se fuerza con `vs_composicion: true`),
la portada compone dos fotogramas del clip separados por una línea diagonal
blanca con una insignia "VS" en el cruce. Aplicado a `capitan-influencer`
(`"¿MUSRRI VS INFLUENCER?"`, `vs_composicion: true`) — la v1 había dejado
este clip como portada estándar porque no había fotos de archivo de dos
protagonistas enfrentados; la v2 resuelve esto usando dos fotogramas del
propio clip (dos momentos del panel) en vez de fotos de archivo que no
existen, lo que igual comunica "enfrentamiento" sin inventar material.

## 6. Biblioteca de recursos propia

Se creó `RayandoelCDA\recursos-portadas\` para fotos propias (hinchada,
estadio, jugadores) y el campo `imagen_fondo` en `clip_overrides.json` para
usar un archivo de esa carpeta como fondo de portada en vez de un fotograma
del clip. El sistema no busca ni descarga imágenes de internet — solo usa
material del clip o de esta carpeta. La carpeta quedó vacía (solo con un
`README.txt` explicando el campo) porque no había fotos propias para este
lote; queda lista para cuando se necesite.

## 7. Marca consistente y legibilidad en miniatura

El logo se mantiene siempre arriba, en el mismo lado que en los videos.
Se agregó una franja inferior delgada con "RAYANDO EL CDA" en Anton. La
verificación de legibilidad en miniatura (regla "debe leerse al 20%") se
resolvió generando esa vista previa directamente dentro de
`portada_candidatas.jpg`, en vez de un archivo separado.

## 8. Regeneración y housekeeping

- Los 5 clips del 06/07 se regeneraron con el nuevo sistema. Las portadas
  v1 (`portada_vertical.jpg` / `portada_horizontal.jpg` de la versión
  anterior) quedaron en `v1\` dentro de cada carpeta de clip, junto a los
  demás archivos v1 ya guardados ahí (video/subtítulos de la primera ronda
  de feedback).
- `copys.md` de los 5 clips se regeneró para incluir la nueva línea
  `**Portada:** <titulo_portada>`.
- Nuevos módulos: `portadas.py` (todo el sistema de portadas) y
  `ffmpeg_utils.py` (helpers de ffmpeg/ffprobe compartidos). `cortar_clip.py`
  quedó más corto: ya no contiene la lógica de composición de portada, solo
  la orquesta.
- `requirements.txt`: se agregó `opencv-python-headless<5` (fijado por
  debajo de la 5.x porque esa serie no trae los Haar cascades incluidos en
  el paquete) y `numpy`.
- `config.py`: nuevos parámetros `PORTADA_FONT_SIZE_MAX_RATIO`/`_MIN_RATIO`,
  `PORTADA_COLOR_DESTACADO`, `PORTADA_COLOR_FRANJA`, `PORTADA_VS_*`,
  `PORTADA_MARCA_*`, `PORTADA_CANDIDATOS_*`, `RECURSOS_PORTADAS_DIR`, etc.
  (ver `config.py` para el detalle completo).
- `README.md`: reescrita la sección "Portadas automáticas" con el diseño v2
  completo, estructura de carpetas actualizada (`fonts\`,
  `recursos-portadas\`, `portada_candidatas.jpg`).

## Pendientes / recomendaciones para más adelante

1. **`oro-panamericanos` sigue mostrando la barra del navegador** en la
   parte superior de la portada: ese tramo del programa es una captura de
   pantalla del streaming oficial de los Panamericanos con las pestañas del
   navegador visibles (parte real del video fuente, no un error del
   sistema). El recorte con foco en rostro mejoró mucho la composición
   (ahora se ve a Valentina Toro y el resto del panel en vez de una pared
   vacía), pero si quieren una portada 100% limpia para este clip, lo más
   rápido es agregar una foto/captura sin la barra del navegador a
   `recursos-portadas\` y usar `imagen_fondo`.
2. Sigue pendiente confirmar "Pepe Roja" en `capitan-influencer` (ver
   CAMBIOS anteriores) y verificar por oído el offset de `hype-catolica`.
3. Si en el futuro se quiere una composición VS con fotos reales de dos
   protagonistas (en vez de dos momentos del mismo clip), basta con subir
   esas fotos a `recursos-portadas\` — el campo `imagen_fondo` no soporta
   hoy dos imágenes a la vez para VS, así que esa combinación (VS +
   imagen_fondo) quedaría como mejora futura si se necesita.

---

# Cambios aplicados — feedback editorial del 06/07

Resumen de lo que se hizo en respuesta al feedback del equipo editorial sobre
los 5 clips del programa del 06/07. Todo lo descrito abajo ya está aplicado y
los archivos regenerados están en `clips\2026-07-06\<nombre-clip>\`. Las
versiones anteriores quedaron guardadas en `v1\` dentro de cada carpeta de
clip, por si quieren comparar.

## 1. Diccionario de nombres propios (mejora permanente del pipeline)

- **`diccionario.json`** (nuevo, en `Proyecto\`): términos correctos del
  universo del programa (Wanderers, Fernando Gago, Johnny Herrera, Musrri,
  Valentina Toro, Nico Castillo, Marcelo Díaz, Azul Azul, ANFP, Corfuch, la U,
  la Chuncha, el Bulla, el Romántico Viajero, CDA, Copa Chile) + variantes mal
  transcritas ya detectadas comparando fonéticamente contra el `.srt` maestro
  del 06/07, más una lista de `correcciones_especiales` para frases puntuales.
- **`corregir_nombres.py`** (nuevo): corrector con 3 capas — reemplazo exacto
  de frases especiales, reemplazo exacto de variantes conocidas (palabra o
  frase completa, sin distinguir mayúsculas) y fuzzy matching (`difflib`)
  contra el nombre correcto de cada término, para variantes futuras no
  listadas todavía. Corrige `.srt`, `.json` y `.ass`.
- **`transcribir.py`**: ahora pasa los términos del diccionario como
  `initial_prompt` a faster-whisper (para transcribir mejor desde el origen)
  y aplica `corregir_nombres` automáticamente al `.srt`/`.json` maestro apenas
  termina de transcribir.
- **`cortar_clip.py`**: aplica `corregir_nombres` de nuevo al construir los
  subtítulos de cada clip (capa extra de seguridad, barata).
- Se corrió el corrector sobre el `.srt`/`.json` maestro del 06/07: **9
  segmentos corregidos**, entre ellos:
  - "guardia" / "Wander" / "Wander Sierra" → **Wanderers** (4 apariciones)
  - "John Irrera" → **Johnny Herrera**
  - "Lucho Murri" → **Lucho Musrri**
  - "la NFP" → **la ANFP**
  - "en el Osi para este" → **en el hocico pa este** (clip Nico Castillo)

**Pendiente / decisión editorial:** en el clip `capitan-influencer` aparece
también "Pepe Roja" (probablemente "Pepe Rojas", con "s" final). No lo corregí
automáticamente porque no hay suficiente contexto en el programa para
confirmar el nombre completo y no quise inventarlo. Si me confirman el nombre
correcto, lo agrego al diccionario.

## 2. Logo permanente en los verticales

Se agregó overlay del logo (`C:\...\RayandoelCDA\Logo PNG.png`) en
`build_vertical()` de `cortar_clip.py`, con transparencia (usa el canal alfa
del PNG) y posición/tamaño configurables en `config.py`
(`LOGO_POSICION="top-right"`, `LOGO_ANCHO_RATIO=0.16`, `LOGO_MARGEN_PX=40`,
`LOGO_OPACIDAD=0.9`). Aplicado a los 5 clips regenerados.

## 3. Portadas automáticas (nueva funcionalidad)

`cortar_clip.py` ahora genera, sin servicios externos (ffmpeg + Pillow), dos
archivos por clip:
- `portada_vertical.jpg` (1080×1920)
- `portada_horizontal.jpg` (1280×720)

Cada una toma un fotograma a mitad del clip, le aplica un degradado oscuro
inferior para legibilidad, el título en mayúsculas con tipografía Impact
(auto-ajustada de tamaño para caber en máximo 5 líneas) y el logo en la
esquina superior. Generadas para los 5 clips.

**Nota sobre `capitan-influencer`:** el pedido original sugería explorar una
portada estilo "versus" para este clip. Evalué la idea pero el clip es un
comentario de panel (no hay dos protagonistas enfrentados con material visual
claro para componer un versus real), así que se dejó con portada estándar
como indicaba el pedido como opción de respaldo.

## 4. Copys automáticos (nueva funcionalidad)

`cortar_clip.py` genera `copys.md` por clip con título SEO + copy de
Instagram + título/descripción de YouTube Shorts + copy de TikTok, siempre
con los hashtags base `#UdeChile #LaU #VamosLaU #RayandoElCDA` más hashtags
específicos por tema. El contenido se redactó a mano leyendo la transcripción
completa de cada clip (quedó en `clip_overrides.json`, editable). Si un clip
nuevo no tiene entrada en `clip_overrides.json`, el sistema genera el título y
el contexto automáticamente a partir del nombre de carpeta y las primeras
frases de la transcripción, así que la función sirve también para clips
futuros sin curación manual.

Para `polemica-nico-castillo` los títulos sugeridos usan el gancho pedido:
*"La polémica de Nico Castillo: '¿cuántas patadas en el hocico pa este?'"*
(título SEO, título de YouTube y copy de Instagram/TikTok).

## 5. Correcciones específicas por clip

Todos los in/out points se recalcularon cruzando los subtítulos de cada clip
contra el `.json` maestro del programa (los segmentos del `.json` no tienen
duración fija; se identificó el punto exacto de corte original de cada clip y
se ajustó desde ahí).

- **arbitraje-indecente-wanderers**: el corte terminaba a mitad de la palabra
  "España" (`00:34:04.000` → cortaba "...rival de Espa-"). Se extendió el
  out-point a `00:34:04.750`, justo al final de esa frase, para que cierre
  natural. Subtítulos corregidos ("guardia"→Wanderers) + logo + portada +
  copys.
- **capitan-influencer**: se mantuvo el encuadre e in/out originales sin
  cambios (decisión editorial confirmada: sin zoom al hablante). Solo se
  corrigieron subtítulos (Johnny Herrera, Lucho Musrri) + logo + portada
  estándar + copys.
- **hype-catolica**: dos correcciones:
  1. *Offset audio/subtítulos*: se detectó que los segmentos de este tramo del
     programa (charla rápida, varias voces) vienen con timestamps de Whisper
     algo adelantados respecto al audio real. Se aplicó un desplazamiento
     manual de **+0.35s** a los subtítulos de este clip específico (no es un
     parámetro global de config, fue una corrección puntual con un script
     ad-hoc). **Esto es una corrección heurística** — no tengo forma de
     escuchar el audio para verificar el offset exacto, así que les pido que
     revisen el resultado y me avisen si hay que ajustar el delta. La causa
     raíz (segmentación de Whisper poco precisa en tramos de conversación
     rápida/cruzada) se documenta como mejora pendiente más abajo.
  2. *Corte final*: el clip incluía el arranque de la mención a "Vale Toro my
     love" cortada a la mitad. Se movió el out-point de `00:35:22.000` a
     `00:35:20.750`, terminando en "le ganamos con Paqui pues weon", antes de
     esa mención. Subtítulos corregidos + logo + portada + copys.
- **oro-panamericanos**: dos correcciones:
  1. *Escala de video*: se subió `VERTICAL_FOREGROUND_SCALE` a `1.35` en
     `config.py` (ahora es el default global, como se pidió) — el video en
     primer plano ocupa más alto del vertical y se ve menos blur.
  2. *In-point*: se movió de `00:17:20.000` (arrancaba con la introducción del
     video "Mira, los Juegos Panamericanos de Santiago... Vamos, Valentina, 42
     segundos") a `00:17:22.950`, para que el clip arranque directo con la
     pregunta del entrevistador: *"Esto fue un momento de lo más importante de
     tu carrera, ¿no?"*. Subtítulos + logo + portada + copys.
- **polemica-nico-castillo**: sin cambios de in/out. Subtítulos corregidos
  ("en el hocico pa este") + logo + portada + copys con el gancho pedido.

## 6. Pipeline / documentación

- `config.py`: nuevos parámetros `VERTICAL_FOREGROUND_SCALE`, `LOGO_*`,
  `PORTADA_*`, `COPYS_HASHTAGS_BASE`.
- `requirements.txt`: se agregó `Pillow` (se instaló en este equipo).
- `README.md`: documentadas las 4 funcionalidades nuevas (diccionario, logo,
  portadas, copys) con sus parámetros, y actualizada la estructura de
  carpetas.

## Pendientes / recomendaciones para más adelante

1. **Confirmar "Pepe Roja"** en `capitan-influencer` (¿"Pepe Rojas"?) para
   agregarlo al diccionario.
2. **Verificar por oído** el offset aplicado a `hype-catolica` (+0.35s) — es
   una corrección heurística, no validada con audio real.
3. **Mejora de raíz para el problema de sincronía**: activar
   `word_timestamps=True` en faster-whisper y reconstruir los subtítulos de
   clip a partir de timestamps por palabra (no por segmento) daría una
   sincronía mucho más fina, especialmente en tramos de conversación cruzada
   como el de `hype-catolica`. No lo implementé ahora porque cambia cómo se
   arma todo `subtitulos.srt`/`.ass` (usa segmentos, no palabras) y hay que
   probarlo bien antes de dejarlo como default; lo dejo anotado para la
   próxima iteración del pipeline.
4. El diccionario de nombres es un punto de partida: cuando aparezca un
   nombre mal transcrito nuevo en futuros programas, basta con agregarlo a
   `diccionario.json` (como variante o como corrección especial) — no
   requiere tocar código.
5. La portada "versus" para `capitan-influencer` quedó como estándar (ver
   sección 3); si tienen imágenes de archivo del capitán y del influencer que
   quieran componer manualmente, puedo armar una versión versus con eso.
