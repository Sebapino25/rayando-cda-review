# Rayando el CDA

Sistema de automatización para cortar clips de "Rayando el CDA" (programa semanal
sobre Universidad de Chile, transmitido en vivo los lunes por YouTube y grabado
localmente con OBS) y publicarlos en redes sociales.

## Estado del proyecto

El pipeline corre de punta a punta sin intervención manual: una grabación
nueva se transcribe, se detectan candidatos a clip automáticamente (o se usa
una lista ya confirmada), se cortan y se suben a YouTube como no listados
para revisión editorial — todo disparado solo cada 5 minutos (ver
"Disparador automático" más abajo). Una vez que el equipo aprueba un clip en
la app de revisión, el botón "Publicar en redes" lo publica de verdad en
YouTube (público) e Instagram (Reels) vía Supabase Edge Functions, y si
pide una corrección de in/out point, se re-corta solo con IA (ver
"Corrección automática de video" más abajo).

Lo único pendiente es TikTok: el código de publicación ya está construido
pero con el flag apagado, porque el Developer App de TikTok nunca se
resubmitió para revisión (se perdió el formulario al pasar de
Sandbox a Producción).

## Flujo del sistema

```
Grabación OBS (.mkv)
        │
        ▼
  transcribir.py  →  .srt + .json (transcripciones\)
                      + corrección automática de nombres propios (diccionario.json)
        │
        ▼
  cortar_clip.py  →  horizontal_original.mp4 + vertical.mp4 (clips\)
                      + logo incrustado + portadas + copys.md + metadata.json
        │
        ▼
  publicar.py (se corre automáticamente al final de cortar_clip.py)
        →  valida el archivo (existe, ffprobe lo lee, duración > 0)
        →  sube vertical.mp4 (el clip final: 9:16, con logo y subtítulos ya
           incrustados) a YouTube como NO LISTADO — René revisa exactamente
           lo que se publicaría, no el corte crudo
        →  inserta el candidato en rayando_cda.clips (Supabase) con
           estado="pendiente" para que René lo revise ahí
        →  deja resumen.txt local como respaldo (no es el review principal)
        │
        ▼
 Aprobación en la app de revisión → botón "Publicar en redes" → publica de
 verdad en YouTube (público) e Instagram (Reels) vía Supabase Edge
 Functions (ver app/README.md). TikTok queda pendiente (flag apagado).
```

## Estructura de carpetas

Las grabaciones, transcripciones y clips viven **fuera** de esta carpeta de
proyecto (nunca se copian ni se mueven videos hacia `Proyecto\`):

```
RayandoelCDA\
├── Proyecto\                  ← este repositorio (código)
│   ├── config.py               Rutas y parámetros centralizados
│   ├── transcribir.py          Script de transcripción (faster-whisper)
│   ├── cortar_clip.py          Script de corte horizontal + vertical + logo + copys (orquesta portadas.py)
│   ├── portadas.py              Sistema de portadas v2: selección de fotograma, contact sheet, composición
│   ├── ffmpeg_utils.py          Helpers de ffmpeg/ffprobe compartidos
│   ├── corregir_nombres.py     Corrector de nombres propios (diccionario + fuzzy matching)
│   ├── diccionario.json        Términos correctos del universo del programa + variantes mal transcritas
│   ├── clip_overrides.json     Títulos/copys/portada editoriales por clip (opcional, con fallback automático)
│   ├── publicar.py              Sube a YouTube (no listado) + inserta en Supabase (rayando_cda.clips)
│   ├── supabase_migration_clips.sql  SQL idempotente para crear/actualizar la tabla en Supabase
│   ├── .env / .env.example      Credenciales YouTube OAuth + Supabase (`.env` nunca se sube a git)
│   ├── fonts\
│   │   └── Anton-Regular.ttf    Tipografía de titulares (Google Fonts, licencia SIL OFL 1.1)
│   ├── requirements.txt
│   └── README.md
├── Logo PNG.png                 Logo del programa (usado como overlay y en portadas)
├── recursos-portadas\           Fotos propias (hinchada, estadio, etc.) para usar como fondo de portada
├── cierres\                     Videos de cierre institucional (ver "Cierre institucional en los verticales")
│   ├── CIERRE VERTICAL.mp4 / CIERRE VERTICAL 2.mp4 / CIERRE VERTICAL 3.mp4
│   ├── CIERRE HORIZONTAL.MP4_  (guardado, aún sin integrar)
│   └── rotacion_estado.json    índice del último cierre usado (round-robin)
├── grabaciones\                Grabaciones de OBS (.mkv), NUNCA se tocan
│   └── 2026-07-06 23-13-36.mkv
├── transcripciones\            Salida de transcribir.py
│   └── 2026-07-06 23-13-36\
│       ├── 2026-07-06 23-13-36.srt
│       └── 2026-07-06 23-13-36.json
└── clips\                      Salida de cortar_clip.py
    └── 2026-07-06\                     ← fecha del programa (del nombre del archivo OBS)
        └── nombre-del-clip\
            ├── horizontal_original.mp4  16:9, tal cual el corte
            ├── vertical.mp4              9:16, con blur + logo + subtítulos incrustados
            ├── subtitulos.srt            recorte de subtítulos (referencia/portable)
            ├── subtitulos.ass            recorte de subtítulos (usado para incrustar)
            ├── portada_vertical.jpg      1080x1920, portada final (ver "Portadas automáticas")
            ├── portada_horizontal.jpg    1280x720, portada final
            ├── portada_candidatas.jpg    contact sheet de fotogramas candidatos + vista previa miniatura
            ├── copys.md                  título SEO + título de portada + copys IG/YouTube Shorts/TikTok
            ├── metadata.json             inicio/fin/video fuente/razón/transcripción del clip (input de publicar.py)
            ├── resumen.txt               respaldo local de la subida (IDs de YouTube/Supabase); el review real es en Supabase
            └── v1\                       (si el clip se regeneró) versión anterior, para comparar
```

La fecha del programa se obtiene del nombre del archivo de grabación (convención
de OBS: `YYYY-MM-DD HH-MM-SS.mkv`). Si el nombre no calza con ese patrón, se usa
la fecha de modificación del archivo.

## Instalación

Requiere Python 3.12, ffmpeg/ffprobe en el PATH (ya verificado en este equipo).

```powershell
cd "C:\Users\sebap\OneDrive\Escritorio\RayandoelCDA\Proyecto"
pip install -r requirements.txt
```

Esto instala `opencv-python-headless` (usado por `portadas.py` para las
heurísticas de nitidez/rostro; trae los Haar cascades incluidos, no requiere
descargas aparte) y `numpy`. La tipografía de portadas (`fonts/Anton-Regular.ttf`,
Google Fonts, licencia SIL Open Font License 1.1) ya está incluida en el
repositorio, no requiere instalación.

Para transcribir con GPU (NVIDIA RTX 3050 Ti, 4 GB VRAM) además se necesitan las
DLLs de cuBLAS/cuDNN (ya instaladas en este equipo vía pip):

```powershell
pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
```

Si no están disponibles o fallan al cargar, `transcribir.py` cae automáticamente
a CPU (más lento, pero funcional).

**Nota sobre Avast**: si `transcribir.py` falla la primera vez con un error SSL
(`CERTIFICATE_VERIFY_FAILED`) al descargar el modelo de Whisper, es porque Avast
intercepta las conexiones HTTPS con su propio certificado y Python no confía en
él por defecto. Ya se resolvió en este equipo agregando el certificado raíz de
Avast al bundle de `certifi`. Si se reinstala Python/certifi, puede ser necesario
repetirlo.

## Uso

### 1. Transcribir una grabación

```powershell
# Transcribe la grabación más reciente en la carpeta `grabaciones`
python transcribir.py

# Transcribe un archivo específico (nombre dentro de `grabaciones`)
python transcribir.py "2026-07-06 23-13-36.mkv"

# Transcribe una ruta absoluta cualquiera
python transcribir.py "C:\ruta\a\otro\video.mkv"

# Usar otro modelo de Whisper (ej. mayor precisión, más lento)
python transcribir.py --modelo large-v3
```

Genera `transcripciones\<nombre-grabación>\<nombre-grabación>.srt` y `.json`.
Muestra progreso segmento a segmento en consola. Si se interrumpe (Ctrl+C), igual
guarda como archivos finales todo lo transcrito hasta ese punto (marcado como
`"partial": true` en el `.json`) sin corromper nada; para completar la
transcripción hay que volver a correr el comando desde cero.

Modelo por defecto: `medium` (mejor balance calidad/velocidad para español con
jerga futbolera chilena en este hardware). Se puede subir a `large-v3` con
`--modelo` si la calidad no es suficiente — la grabación original se conserva,
así que siempre se puede re-transcribir.

### 2. Cortar un clip

```powershell
python cortar_clip.py "2026-07-06 23-13-36.mkv" 00:12:30 00:13:45 mejor-jugada-gol --razon "Gol y festejo, buen remate para redes"
```

Argumentos: `video` (nombre en `grabaciones` o ruta absoluta), `inicio` y `fin`
(formato `hh:mm:ss`, admite fracción de segundo `hh:mm:ss.mmm`), `nombre` (nombre
del clip, se usa como carpeta), `--razon` (opcional: por qué se eligió este
momento — no hay detección automática de momentos, así que si querés dejarla
registrada tenés que escribirla vos al cortar el clip; si se omite, queda
`NULL`).

Genera en `clips\<fecha-programa>\<nombre>\`:
- `horizontal_original.mp4`: corte 16:9. Se intenta primero sin recodificar
  (rápido); si el corte queda desfasado por límite de keyframes, se recorta de
  nuevo recodificando para precisión exacta al frame.
- `vertical.mp4`: 9:16 (1080×1920) para Reels/Shorts/TikTok, con el video en
  primer plano (con zoom, ver `VERTICAL_FOREGROUND_SCALE`) sobre un fondo
  desenfocado del mismo video, el **logo del programa incrustado** (ver
  sección Logo) y subtítulos incrustados extraídos y re-sincronizados desde la
  transcripción maestra del programa, ya pasados por el corrector de nombres
  propios (si existe transcripción). Si aún no se transcribió esa grabación,
  el vertical se genera igual pero sin subtítulos. Termina con un **cierre
  institucional** pegado al final (ver sección "Cierre institucional").
- `portada_vertical.jpg` / `portada_horizontal.jpg`: portadas automáticas (ver
  sección Portadas).
- `copys.md`: título SEO + copys para Instagram/YouTube Shorts/TikTok (ver
  sección Copys).
- `metadata.json`: inicio/fin/video fuente/razón/transcripción del clip.
- Al final, sube automáticamente el clip y registra el candidato en Supabase
  (ver sección siguiente).

Si el clip pedido dura más de 90 segundos, se advierte en consola pero se genera
igual (límite orientativo para Reels/Shorts/TikTok).

Si vuelves a correr `cortar_clip.py` con el mismo nombre de clip, los archivos
se sobrescriben en la misma carpeta (y se vuelve a subir a YouTube e insertar
en Supabase como un candidato nuevo — no actualiza el registro anterior).
Antes de regenerar un clip ya publicado conviene mover manualmente los
archivos viejos a una subcarpeta `v1\` dentro de la carpeta del clip, por si
se necesita comparar después (así se hizo al aplicar el feedback editorial
del 06/07).

## Procesamiento automático de un programa completo

En vez de cortar clips uno por uno a mano, `procesar_programa.py` orquesta
todo un programa de punta a punta: detecta candidatos, corta cada uno
(reusando `cortar_clip.cortar_y_publicar()`) y publica, sin intervención
manual en el medio. Es lo que corre el disparador automático (ver más
abajo) sobre cada grabación nueva.

```powershell
python procesar_programa.py "2026-07-06 23-13-36.mkv"
```

Requiere que la grabación ya esté transcrita (`transcribir.py`).

**Detección de candidatos**: si existe
`clips\<fecha>\candidatos_<fecha>.json` (una lista de objetos con `numero`,
`timestamp_inicio`, `timestamp_fin`, `duracion_seg` y `razon` — el mismo
formato que ya se guardaba a mano antes de automatizar esto), se usan esos
candidatos directo, respetando su `numero` para el nombre de carpeta
(`candidato-01`, etc.) — es el caso de haber corrido `detectar_momentos.py`
aparte, revisado la lista y confirmado el JSON. Si ese archivo no existe,
`detectar_momentos.py` detecta los candidatos en vivo con la API de
Anthropic sobre la transcripción completa (prioriza humor, declaraciones
fuertes sobre la U/la dirigencia, y momentos con carga emocional real; los
timestamps siempre calzan con límites de segmento reales de Whisper, nunca
un segundo inventado).

En ambos casos, antes de cortar se descartan candidatos que se superpongan
con clips ya cortados para esa fecha de programa (comparando contra
`metadata.json` de cada carpeta existente), para no duplicar el mismo
momento entre corridas manuales y automáticas.

Para solo ver qué candidatos detectaría la IA sin cortar ni subir nada:

```powershell
python detectar_momentos.py "2026-07-06 23-13-36.mkv"
```

## Publicación (YouTube no listado + Supabase)

Al final de `cortar_clip.py` se corre automáticamente `publicar.py`:

1. **Validación técnica** del `vertical.mp4` recién generado (existe,
   `ffprobe` lo puede leer, duración > 0). Si falla, el clip **no se sube** y
   queda registrado en `errores_publicacion.log` (en la raíz de
   `RayandoelCDA\`) — no es una calificación de contenido, solo un chequeo de
   que el archivo no esté roto.
2. Si pasa la validación, sube `vertical.mp4` — el clip **final** tal como se
   publicaría (9:16, con blur, logo y subtítulos ya incrustados, no el corte
   crudo) — a YouTube como video **no listado** (`privacyStatus: unlisted`),
   con un título genérico tipo `"Rayando el CDA - candidato 2026-07-06 - clip
   3"` (no importa que no sea el título final — eso lo decide después la
   revisión editorial). Así René revisa exactamente lo que vería la audiencia.
3. Inserta un registro en `rayando_cda.clips` (Supabase) con
   `youtube_video_id`, `titulo`, `copy_instagram`, `youtube_titulo`,
   `youtube_descripcion`, `copy_tiktok`, `razon`, `transcripcion`,
   `timestamp_inicio`, `timestamp_fin`, `semana` (fecha del programa) y
   `estado="pendiente"`. (La columna `copy_youtube` queda en la tabla como
   legacy — título+descripción juntos — pero el pipeline ya no le escribe.)
4. Deja `resumen.txt` en la carpeta del clip como **respaldo local** (IDs de
   YouTube/Supabase) — la revisión real la hace René en la tabla de Supabase,
   no revisando esta carpeta.

Al terminar, la consola imprime cuántos clips se subieron en esa corrida y con
qué IDs de Supabase.

### Configuración inicial (una sola vez)

1. Corre `supabase_migration_clips.sql` en el **SQL Editor** de tu proyecto de
   Supabase (crea el schema `rayando_cda` y la tabla `clips` si no existen, o
   agrega las columnas que falten si la tabla ya existía). Es idempotente,
   se puede correr de nuevo sin riesgo.
2. En el dashboard de Supabase: **Project Settings > API > Exposed schemas**,
   agrega `rayando_cda` (esto no se puede hacer por SQL). Sin este paso el
   cliente falla con un error `PGRST106` aunque el resto esté bien.
3. Copia `.env.example` a `.env` y completa `SUPABASE_URL` y
   `SUPABASE_SERVICE_ROLE_KEY` (la *service role* key, del panel de Supabase
   en Project Settings > API — **no** la `anon` key, porque el insert necesita
   saltarse RLS). Las variables de YouTube (`YOUTUBE_CLIENT_ID`/
   `YOUTUBE_CLIENT_SECRET`) ya quedaron completadas a partir del
   `client_secret_*.json` que ya tenías descargado de Google Cloud Console.
   También completa `RESEND_API_KEY` (dashboard de Resend) — sin ella, el
   disparador automático (ver sección "Disparador automático" más abajo) no
   puede mandar los mails de aviso/error; el resto de las variables está
   documentado en `.env.example`.
4. `pip install -r requirements.txt` (agrega `python-dotenv`,
   `google-api-python-client`, `google-auth-oauthlib` y `supabase`).
5. La **primera vez** que cortes y subas un clip, se abrirá el navegador para
   autorizar la cuenta de YouTube (OAuth). El token queda guardado en
   `youtube_token.json` (ruta configurable con `YOUTUBE_TOKEN_FILE`), así que
   las siguientes subidas no vuelven a pedir login.

`.env`, `youtube_token.json` y `errores_publicacion.log` están en
`.gitignore` — nunca se suben a git.

## Disparador automático (Task Scheduler)

Una tarea de Windows Task Scheduler llamada `RayandoCDA_AutoProcesar` corre
`auto_procesar.ps1` cada 5 minutos, **solo del martes 00:00 al miércoles
10:00** (ventana semanal, se repite sola): si hay una grabación nueva en
`grabaciones\` (sin transcripción todavía y sin cambios en los últimos 5
min, para no agarrar un archivo que OBS todavía está escribiendo), corre
`transcribir.py` + `procesar_programa.py` sola.

Esa ventana es también cuando la herramienta de correcciones (la app de
revisión) está disponible para que el equipo pida ajustes — fuera de ella el
PC puede quedar apagado. Si el equipo necesita un cambio fuera de la
ventana, avisan y se hace a mano. Ver el `$trigger` en
`registrar_tarea_programada.ps1` para el detalle exacto del horario.

**Notificaciones por mail (vía Resend):**
- Al terminar bien: aviso a todo el equipo (`seba.pino.v@gmail.com`,
  `Cristian.fajardoc@gmail.com`, `arriagada.rene@gmail.com`) con el link a
  la app para revisar los clips nuevos.
- Si falla: aviso solo a `seba.pino.v@gmail.com`, con las últimas líneas
  del log de esa corrida incluidas en el mail. El log completo queda en
  `pipeline\logs_auto\<nombre-grabación>.log`.

**Corrección automática de video:** además de procesar grabaciones
nuevas, cada corrida también revisa si hay algún clip en
`estado='correccion_video'` (pedido de ajustar el in/out point vía
`comentarios_video` en la app de revisión) y, si lo hay, corre
`reprocesar_video.py --apply --uno` para interpretarlo con IA y volver a
cortar el clip solo. Si la IA no tiene confianza en el pedido, o no se
puede encontrar la carpeta local del clip sin ambigüedad, aborta antes de
tocar ningún archivo — nunca se adivina un corte. Y si falla un paso
técnico más adelante (ffmpeg, validación, YouTube, Storage o el update de
Supabase), el clip se **restaura automáticamente a su versión anterior**
deshaciendo el respaldo `vN\`, para que la carpeta siga siendo
correlacionable y el siguiente intento reporte el error real. En los dos
casos el clip queda en `estado='correccion_video'` y llega un mail solo a
`seba.pino.v@gmail.com` con el detalle. Si sale bien, el clip vuelve a
`estado='pendiente'` y el equipo recibe el mismo tipo de aviso que al
terminar de procesar una grabación nueva.

**Un pedido que falla no se reintenta solo.** Después de un intento
fallido queda un marcador en
`pipeline\logs_auto\correccion_video_fallos.log` (clip id + hash de
`comentarios_video`), y las corridas automáticas saltean esa fila mientras
el texto del pedido no cambie. Así una sola fila trabada no gasta una
llamada a la API de Anthropic con la transcripción completa ni manda un
mail cada 5 minutos (Resend corta alrededor de 100 mails diarios en el
plan gratis, y pasado ese límite se perderían **todas** las alertas del
pipeline), y tampoco bloquea a los demás pedidos pendientes. Para
destrabarlo: editá `comentarios_video` en la app (el hash cambia y se
reintenta solo), o forzá el reintento a mano con

```powershell
python reprocesar_video.py --apply --clip-id <id>
```

(`--clip-id` ignora el marcador a propósito).

**Nota sobre Avast**: Avast puede poner en cuarentena (borrar)
`auto_procesar_loop.ps1` y/o `registrar_tarea_programada.ps1` al
bloquearlos por contenido, no por ser malware real — ya pasó una vez en
este equipo. Si alguno de los dos desaparece del todo, agregá una
excepción en Avast para la carpeta `pipeline\` y restauralos desde git
(`git checkout -- pipeline\auto_procesar_loop.ps1
pipeline\registrar_tarea_programada.ps1`).

**Para registrar la tarea (primera vez en una PC nueva, o para
re-registrarla si hace falta):**

```powershell
powershell -ExecutionPolicy Bypass -File pipeline\registrar_tarea_programada.ps1
```

Es idempotente — mata cualquier loop manual que haya quedado corriendo y
vuelve a crear la tarea desde cero. Corre solo mientras la sesión de
Windows esté iniciada (no requiere guardar la contraseña de la cuenta).

**Para revisar el estado:**

```powershell
Get-ScheduledTask -TaskName RayandoCDA_AutoProcesar | Select-Object TaskName, State
Get-ScheduledTaskInfo -TaskName RayandoCDA_AutoProcesar
Get-Content pipeline\logs_auto\loop.log -Tail 10
```

## Diccionario de nombres propios y corrección automática

`diccionario.json` contiene los términos correctos del universo del programa
(jugadores, apodos, instituciones) junto con variantes ya detectadas que
Whisper transcribe mal (ej. "guardia"/"Wander" → "Wanderers", "John Irrera" →
"Johnny Herrera", "Murri" → "Musrri", "NFP" → "ANFP"), y una lista de
`correcciones_especiales` para frases puntuales.

`corregir_nombres.py` aplica esas correcciones sobre `.srt`/`.json`/`.ass`:
primero reemplazos exactos (frase completa y palabra completa, sin distinguir
mayúsculas), y después fuzzy matching (`difflib`) palabra por palabra contra el
nombre "correcto" de cada término, para variantes nuevas que todavía no están
listadas. Se puede correr manualmente:

```powershell
python corregir_nombres.py "ruta\archivo.srt" "ruta\archivo.json"
```

Este corrector se aplica automáticamente en dos puntos del pipeline:
1. Al final de `transcribir.py`, sobre el `.srt`/`.json` maestro recién generado.
2. Al construir los subtítulos de cada clip en `cortar_clip.py` (capa extra de
   seguridad).

Además, `transcribir.py` pasa los términos del diccionario como `initial_prompt`
a faster-whisper, para que intente transcribirlos bien desde el origen.

Cuando aparezca un nombre mal transcrito nuevo, agrégalo como `variante` del
término correspondiente en `diccionario.json` (o como `corrección especial` si
es una frase puntual de un programa específico) y listo, queda corregido para
siempre hacia adelante.

## Logo permanente en los verticales

Todo `vertical.mp4` lleva el logo del programa incrustado (por defecto en la
esquina superior derecha). Parámetros en `config.py`:

- `LOGO_PATH`: ruta al PNG del logo (por defecto `Logo PNG.png` en la raíz de
  `RayandoelCDA\`).
- `LOGO_POSICION`: `top-left` / `top-right` / `bottom-left` / `bottom-right`.
- `LOGO_ANCHO_RATIO`: ancho del logo como fracción del ancho del vertical.
- `LOGO_MARGEN_PX`: margen respecto al borde.
- `LOGO_OPACIDAD`: 0-1.

## Cierre institucional en los verticales

Todo `vertical.mp4` (`build_vertical` en `cortar_clip.py`) termina con un
cierre institucional pegado al final, concatenado en el mismo filtro de
ffmpeg que arma el vertical. René entregó 3 variantes (1080×1920, mismo
formato que el vertical final) y se rota entre ellas en round-robin para que
no se sienta repetitivo — nunca se repite la misma dos veces seguidas,
incluso si el pipeline se reinicia entre clips (el índice se persiste en
disco).

Aplica automáticamente en los tres puntos que generan/regeneran el vertical:
corte normal, `reprocesar_subtitulos.py` y `reprocesar_video.py` (corrección
automática de in/out point).

Parámetros en `config.py`:

- `CIERRES_DIR`: carpeta con los videos de cierre (fuera del repo, en
  `RayandoelCDA\cierres\`, misma convención que `Logo PNG.png` y
  `recursos-portadas\`).
- `CIERRE_VERTICAL_FILES`: lista de nombres de archivo (orden de rotación).
- `CIERRE_ROTACION_STATE_PATH`: JSON (`rotacion_estado.json`) con el índice
  del último cierre usado.

René también entregó un cierre horizontal (`CIERRE HORIZONTAL.MP4_`), que
queda guardado en `CIERRES_DIR` sin integrar: `horizontal_original.mp4` no se
publica en ningún lado hoy (es solo material interno para generar el
vertical), así que no tiene un destino todavía. Si en algún momento se
publica un formato horizontal, agregarlo sería análogo a lo que hace
`build_vertical`.

## Portadas automáticas (v2)

`cortar_clip.py` delega la generación de portadas en `portadas.py`. El
objetivo es que la portada funcione como "gancho" en redes: titular corto y
gritado, tipografía de impacto, jerarquía de color clara y un fotograma
elegido con criterio (no al azar). Genera tres archivos por clip:
`portada_vertical.jpg` (1080×1920), `portada_horizontal.jpg` (1280×720) y
`portada_candidatas.jpg` (contact sheet de selección, ver abajo).

**Titular.** Usa el campo `titulo_portada` de `clip_overrides.json`: máximo
5-6 palabras en MAYÚSCULAS, gritado (ej. `"¡ARBITRAJE INDECENTE!"`,
`"¿MUSRRI VS INFLUENCER?"`). Si el clip no tiene `titulo_portada` curado a
mano, se genera un fallback automático recortando el "título SEO" a las
primeras 6 palabras — funciona para cualquier clip nuevo sin intervención,
pero para publicaciones importantes conviene escribir el titular a mano.

**Tipografía.** Anton (Google Fonts, licencia SIL Open Font License 1.1,
libre para uso comercial), condensada y en mayúsculas gruesas, instalada en
`fonts/Anton-Regular.ttf`. Se usa tanto para el titular como para la franja
de marca inferior. El tamaño se calcula como fracción del alto del canvas
(`PORTADA_FONT_SIZE_MAX_RATIO` / `_MIN_RATIO`), así que escala igual en la
vertical y en la horizontal sin chocar nunca con el logo.

**Jerarquía de color.** Texto principal blanco con contorno/sombra negra
gruesa (`stroke_width` de Pillow); la palabra clave del titular se destaca
en amarillo `#FFD700` (`PORTADA_COLOR_DESTACADO`). La palabra clave se toma
del campo `palabra_clave` en `clip_overrides.json` si existe, o si no se
auto-detecta la palabra más larga del titular que no sea una muletilla
(`PORTADA_STOPWORDS_CLAVE`). Detrás del bloque de texto se dibuja una franja
diagonal azul marino semitransparente (`PORTADA_COLOR_FRANJA`) para
legibilidad sobre cualquier fondo.

**Selección de fotograma con criterio.** En vez de tomar un fotograma fijo a
mitad del clip, `portadas.py` extrae `PORTADA_CANDIDATOS_N` (7 por defecto)
fotogramas distribuidos en el clip (saltando el 8% inicial/final para evitar
negros y transiciones) y puntúa cada uno con heurísticas simples:
- **Nitidez**: varianza del Laplaciano (`cv2.Laplacian(...).var()`); penaliza
  fotogramas borrosos/con motion blur.
- **Rostro y ojos abiertos**: detección con Haar cascades de OpenCV
  (`haarcascade_frontalface_default` + `haarcascade_eye`, con `minNeighbors`
  alto y `minSize` proporcional al ancho del frame para evitar falsos
  positivos en texturas/fondos). Un rostro con ambos ojos detectados suma
  puntaje; un rostro detectado sin ojos visibles (probable pestañeo o
  perfil) resta puntaje — así se evita el clásico "salió con los ojos
  cerrados".

El candidato con mayor puntaje se usa automáticamente. Cuando el fotograma
elegido tiene un rostro detectado, el recorte a 9:16/16:9 se centra
horizontalmente en ese rostro en vez de en el centro geométrico de la
imagen (`focus_x_ratio`) — evita cortar al sujeto cuando no está centrado en
el fotograma original (frecuente en los layouts de videollamada con varias
cámaras del programa).

`portada_candidatas.jpg` es un **contact sheet** con los
`PORTADA_CANDIDATOS_TOP_N` (4) mejores candidatos numerados (nitidez, rostro,
ojos y score de cada uno) más una fila de **vista previa en miniatura al
20%** de la portada real con cada candidato, para poder juzgar si el titular
se lee bien "en el feed" antes de publicar. Para usar otro candidato en vez
del mejor automático, anota el número que aparece en el contact sheet y
agrégalo como `frame_portada` en `clip_overrides.json` (ej. `"frame_portada":
3`), y vuelve a correr `cortar_clip.py` (o regenera solo la portada, ver
"Regenerar solo portadas" más abajo).

**Composición "VS".** Cuando `titulo_portada` contiene la palabra "vs" (o se
fuerza con `"vs_composicion": true` en el override), la portada compone dos
fotogramas del clip lado a lado separados por una línea diagonal blanca, con
una insignia "VS" en el cruce. Se puede desactivar con `"vs_composicion":
false`. Ejemplo real: `capitan-influencer` (`"¿MUSRRI VS INFLUENCER?"`).

**Imagen propia de fondo.** Para usar una foto propia (hinchada, estadio,
etc.) en vez de un fotograma del clip, coloca el archivo en
`RayandoelCDA\recursos-portadas\` y referencia su nombre con `"imagen_fondo":
"nombre-archivo.jpg"` en `clip_overrides.json`. En este modo no se extraen
candidatos ni se genera contact sheet (no aplica). El sistema **nunca**
busca ni descarga imágenes de internet — solo usa material del clip o de
`recursos-portadas\`.

**Marca.** El logo va siempre arriba, en el mismo lado que en los videos
(`LOGO_POSICION`). Abajo hay una franja delgada de marca con "RAYANDO EL
CDA" en Anton.

Todos los campos de override (`titulo_portada`, `palabra_clave`,
`frame_portada`, `imagen_fondo`, `vs_composicion`) son opcionales, editables
a mano en `clip_overrides.json`, y con fallback automático si faltan. Ver el
campo `_comentario_portadas_v2` en `clip_overrides.json` para el detalle de
cada uno, y los 5 clips del 06/07 para ejemplos reales.

Parámetros de diseño (tamaños, colores, ratios de la franja, del VS, del
contact sheet) están en `config.py`, sección `PORTADA_*`.

### Regenerar solo portadas

Si solo cambiaste `clip_overrides.json` (nuevo `titulo_portada`,
`frame_portada`, etc.) y no quieres volver a cortar/transcribir el clip:

```powershell
python -c "from pathlib import Path; import cortar_clip, portadas; out=Path(r'C:\Users\sebap\OneDrive\Escritorio\RayandoelCDA\clips\<fecha>\<nombre-clip>'); ov=cortar_clip._cargar_overrides('<nombre-clip>'); copys=cortar_clip.build_copys(out,'<nombre-clip>',[]); portadas.build_portadas(out, out/'horizontal_original.mp4', copys.titulo_portada, ov)"
```

(Esto regenera `copys.md` con el contenido curado en el override y las tres
imágenes de portada; no toca `horizontal_original.mp4` ni `vertical.mp4`.)

## Copys automáticos

`cortar_clip.py` genera `copys.md` por clip con título SEO + título de
portada + copy de Instagram + título/descripción de YouTube Shorts + copy de
TikTok, usando siempre los hashtags base de `config.COPYS_HASHTAGS_BASE`
(`#UdeChile #LaU #VamosLaU #RayandoElCDA`) más los que se agreguen por clip.

Por defecto el contenido se genera automáticamente a partir del nombre de la
carpeta (título) y las primeras frases de la transcripción del clip
(contexto) — funciona sin intervención para cualquier clip nuevo. Para
curar manualmente el título/copys de un clip específico (recomendado para
publicaciones importantes), agrega una entrada en `clip_overrides.json` con
la clave igual al nombre de la carpeta del clip; los campos que no se
especifiquen se completan automáticamente. Ver `clip_overrides.json` para
ejemplos reales (los 5 clips del 06/07).

## Configuración

Todas las rutas y parámetros (carpetas de grabaciones/clips/transcripciones,
modelo de Whisper, tamaño del formato vertical, escala del video en primer
plano, duración máxima de reel, estilo de subtítulos, logo, portadas, copys)
están centralizados en `config.py`.

## TikTok

El Developer App fue aprobado (06/08/2026): OAuth completo
(`rayando_cda.tiktok_token` con access + refresh token vigentes),
`refrescar-token-tiktok` corriendo cada 12hs sin intervención.

**Estado (26/08/2026) — TikTok automático está pausado; subida manual mientras tanto:**

`PUBLICAR_TIKTOK=true` sigue en los secrets de Supabase, pero **todos los
posts van a fallar (403)** hasta que se apruebe la auditoría, por el
motivo de más abajo. Cada clip aprobado sigue publicándose en YouTube e
Instagram normalmente desde "Publicar en redes"; TikTok hay que subirlo a
mano por ahora (ver "Subida manual" abajo).

El bloqueo de agosto (`403 unaudited_client_can_only_post_to_private_accounts`)
**no era la cuenta Business** (esa hipótesis quedó descartada). Hubo dos
bugs reales en `supabase/functions/publicar-clip/tiktok.ts`, ya corregidos
y desplegados (25/08): el código elegía mal el `privacy_level` cuando
`PUBLIC_TO_EVERYONE` no estaba disponible, y además confiaba en
`creator_info` para decidir si ya se podía postear público — pero
`creator_info` no refleja si la app pasó la auditoría, solo el estado
público/privado de la *cuenta*. Ahora hay una constante manual
`AUDITORIA_APROBADA = false` que fuerza `SELF_ONLY` siempre mientras no se
apruebe la auditoría. Cambiarla a `true` (y redeployar) es el único paso
de código que falta el día que se apruebe.

**Hallazgo del 26/08/2026, más importante — no alcanza con `SELF_ONLY` en
el post:** TikTok exige, para clientes sin auditar, que la *cuenta* de
TikTok esté configurada como privada en el momento de publicar ("All user
accounts using the API client to post must be set to private at the time
of posting", guía oficial de Content Sharing). Mandar `privacy_level:
SELF_ONLY` en el request no es suficiente si la cuenta @rayando.el.cda
está en público — y lo sigue estando (confirmado en vivo con
`creator_info`: `privacy_level_options` trae `PUBLIC_TO_EVERYONE`, algo
que solo aparece con la cuenta pública). Por eso el 26/08 volvió a fallar
un post entero (ni público ni privado) pese a que el código ya elegía bien
`SELF_ONLY` — la causa esta vez fue la cuenta, no el código.

**Decisión (26/08/2026): la cuenta se mantiene en público.** Pasarla a
privada evitaría el 403 y dejaría el flujo automático funcionando (en
privado) hasta la auditoría, pero le haría perder vistas a la cuenta
mientras tanto — se prefirió no hacerlo y apostar a que la auditoría se
apruebe pronto. Mientras siga pendiente, `PUBLICAR_TIKTOK=true` va a
seguir generando un error por cada clip (y su mail de alerta) sin publicar
nada; es esperado, no es una falla nueva que investigar.

**Subida manual a TikTok mientras tanto:** en la app de revisión, cada clip
aprobado tiene los botones **"Descargar clip (para subir a TikTok a mano)"**
y **"Descargar portada"**, tanto en la pestaña "Por publicar" como en
"Publicados" (antes desaparecían al publicar en redes). Bajar los dos,
subirlos a mano desde la cuenta @rayando.el.cda con el copy de TikTok del
clip. El `vertical.mp4` también está en Supabase Storage (bucket
`clips-video`) o en la carpeta local del clip.

Para que el botón siga funcionando después de "Publicar en redes", la Edge
Function `publicar-clip` **ya no borra el video de Storage al publicar** — el
video se conserva hasta que alguien toque **"Eliminar"** en el clip
publicado (ese botón limpia el archivo). Conviene eliminar los clips ya
subidos a TikTok cada tanto para que el bucket no crezca sin control.

**Auditoría de Direct Post: todavía no se envió.** Confirmado en
`developers.tiktok.com/app/7666642864034072596/live` — la sección Direct
Post sigue mostrando el botón "Apply" sin tocar. Es un trámite separado de
la aprobación general de la app (esa sí está lista, "Live in production"
desde el 06/08). Sin esta auditoría, TikTok no deja publicar nada por API
mientras la cuenta esté en público — ver hallazgo del 26/08 arriba.

**Para enviar la auditoría (siguiente paso, 26/08/2026):**

1. Grabar los dos tramos de demo que faltan, usando clips reales del
   programa del 24/08: el flujo en la app hasta "Publicar en redes"
   (aprobar → publicar → PIN) y qué pasa después de publicar (el clip
   apareciendo en TikTok). Ya existe un tramo grabado de la autorización de
   TikTok (OAuth) del 17/08.
2. Subir los videos en `developers.tiktok.com/app/7666642864034072596/live`
   → Content Posting API → Direct Post → Apply (acepta hasta 5 archivos, no
   hace falta unirlos en uno solo).
3. Enviar. Sin SLA público garantizado — como referencia, la revisión
   general de esta misma app tardó ~4 días con un rechazo y reenvío en el
   medio; la auditoría de Direct Post suele tardar más.
4. Aprobada la auditoría: cambiar `AUDITORIA_APROBADA` a `true` en
   `tiktok.ts` y redeployar — ahí el código empieza a postear
   `PUBLIC_TO_EVERYONE` automáticamente.
