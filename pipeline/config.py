from pathlib import Path

PROJECT_DIR = Path(__file__).parent
BASE_DIR = Path(r"C:\Users\sebap\OneDrive\Escritorio\RayandoelCDA")

RECORDINGS_DIR = BASE_DIR / "grabaciones"
CLIPS_DIR = BASE_DIR / "clips"
TRANSCRIPTS_DIR = BASE_DIR / "transcripciones"
RECURSOS_PORTADAS_DIR = BASE_DIR / "recursos-portadas"

RECORDING_EXTENSIONS = (".mkv", ".mp4", ".mov")

WHISPER_MODEL_SIZE = "medium"
WHISPER_LANGUAGE = "es"
WHISPER_COMPUTE_TYPE_GPU = "float16"
WHISPER_COMPUTE_TYPE_CPU = "int8"
WHISPER_VAD_FILTER = True
WHISPER_BEAM_SIZE = 5

VERTICAL_WIDTH = 1080
VERTICAL_HEIGHT = 1920
REEL_MAX_SECONDS = 90

# --- Aire y fades en los cortes (para que no se sientan "cortados" al empezar
# o terminar, aunque los timestamps ya calcen con límites de oración de
# Whisper) ---
CLIP_PAD_SECONDS = 0.4  # margen de silencio agregado antes del inicio y después del fin
CLIP_FADE_SECONDS = 0.25  # duración del fade-in/fade-out de video y audio (debe ser <= CLIP_PAD_SECONDS)

SUBTITLE_FONT_NAME = "Arial"
SUBTITLE_FONT_SIZE = 58
SUBTITLE_OUTLINE = 4
SUBTITLE_SHADOW = 0
SUBTITLE_MARGIN_L = 50
SUBTITLE_MARGIN_R = 50
# Subido de 140 a 300px: a 140 el bloque de subtítulos quedaba pegado al
# borde inferior real (1920px de alto), justo donde Instagram/TikTok
# superponen su propia UI (caption, música, botones). Sigue bien adentro de
# la franja borrosa inferior, solo más arriba dentro de ella.
SUBTITLE_MARGIN_V = 300

# Máximo de palabras por pantalla al quemar subtítulos (ver
# cortar_clip.split_into_captions). Antes se quemaba el segmento de Whisper
# completo tal cual (a veces una oración entera de 15-20 palabras); ahora se
# divide en fragmentos cortos, repartiendo el tiempo del segmento original
# proporcional a la cantidad de palabras de cada fragmento (no hay timestamps
# por palabra porque Whisper corre sin word_timestamps, así que es una
# aproximación, no timing exacto por palabra).
SUBTITLE_MAX_WORDS_PER_CUE = 7

# Cuánto se agranda el video en primer plano del vertical antes de recortarlo de
# vuelta al ancho del canvas (1.0 = tal cual, sin zoom; ocupa solo el ancho
# completo pero queda "chico" verticalmente con mucho blur arriba/abajo). Un
# valor > 1.0 hace zoom (recorta un poco los bordes izq/der) y el video se ve
# más grande/protagonista, con menos blur visible.
VERTICAL_FOREGROUND_SCALE = 1.15

# --- Texto de titulo_portada en la franja superior de relleno (blur) del
# vertical (ver build_vertical en cortar_clip.py). Se dibuja debajo del logo,
# dentro del espacio libre que deja VERTICAL_FOREGROUND_SCALE arriba del
# video real. Los ratios son sobre el alto *disponible* (la franja menos el
# espacio que ocupa el logo), no sobre el alto del canvas completo.
VIDEO_TITULO_MARGEN_PX = 60
VIDEO_TITULO_MAX_LINEAS = 3
VIDEO_TITULO_FONT_SIZE_MAX_RATIO = 0.34
VIDEO_TITULO_FONT_SIZE_MIN_RATIO = 0.14
VIDEO_TITULO_LOGO_GAP_PX = 20  # separación extra debajo del logo, cuando el logo está arriba
VIDEO_TITULO_MIN_USABLE_PX = 120  # si el espacio libre bajo el logo es menor a esto, no se agrega texto

# --- Logo (overlay permanente en todos los verticales) ---
LOGO_PATH = BASE_DIR / "Logo PNG.png"
LOGO_POSICION = "top-right"  # top-left | top-right | bottom-left | bottom-right
LOGO_ANCHO_RATIO = 0.16  # ancho del logo como fracción del ancho del vertical
LOGO_MARGEN_PX = 40
LOGO_OPACIDAD = 0.9  # 0-1, se combina con el canal alfa del PNG si lo tiene

# --- Portadas automáticas (v2) ---
PORTADA_VERTICAL_SIZE = (1080, 1920)
PORTADA_HORIZONTAL_SIZE = (1280, 720)

# Tipografía: Anton (Google Fonts, licencia SIL Open Font License 1.1, libre para
# uso comercial). Descargada en fonts/Anton-Regular.ttf. Condensada, en mayúsculas
# gruesas, pensada para titulares gritados de una sola palabra por línea.
PORTADA_FONT_PATH = str(PROJECT_DIR / "fonts" / "Anton-Regular.ttf")
# Tamaño de fuente como fracción del ALTO del canvas (no píxeles absolutos), para
# que la vertical (1080x1920) y la horizontal (1280x720) escalen proporcional y
# el título nunca choque con el logo arriba ni con la franja de marca abajo.
PORTADA_FONT_SIZE_MAX_RATIO = 0.099  # ≈190px en la vertical de 1920 de alto
PORTADA_FONT_SIZE_MIN_RATIO = 0.036  # ≈70px en la vertical de 1920 de alto
PORTADA_MAX_LINEAS = 3

# Jerarquía de color del titular
PORTADA_TEXTO_COLOR = (255, 255, 255)  # blanco para el texto principal
PORTADA_TEXTO_SOMBRA_COLOR = (0, 0, 0)  # contorno/sombra negra gruesa
PORTADA_TEXTO_STROKE_RATIO = 0.09  # grosor del contorno como fracción del tamaño de fuente
PORTADA_COLOR_DESTACADO = (255, 215, 0)  # #FFD700 amarillo, para la palabra clave del titular
# Palabras que nunca se destacan como "palabra clave" aunque sean las más largas
PORTADA_STOPWORDS_CLAVE = {
    "que", "para", "esto", "esta", "este", "estos", "estas", "pero", "como",
    "donde", "cuando", "sobre", "entre", "hasta", "desde", "porque", "vamos",
    "todo", "toda", "todos", "todas", "quien", "cual", "cuales",
}

# Franja diagonal semitransparente azul oscuro detrás del titular (legibilidad)
PORTADA_COLOR_FRANJA = (8, 24, 51)  # azul marino oscuro
PORTADA_FRANJA_OPACIDAD = 190  # 0-255
PORTADA_FRANJA_PADDING_RATIO = 0.35  # relleno vertical alrededor del bloque de texto, como fracción del alto de línea
PORTADA_FRANJA_SLANT_RATIO = 0.06  # inclinación de la franja como fracción del ancho

# Oscurecido general de fondo (uniforme, independiente de la franja) para que el
# fotograma no compita con el texto
PORTADA_OSCURECIDO_OPACIDAD = 55  # 0-255

# Composición "VS" (dos fotogramas separados por una línea diagonal)
PORTADA_VS_SLANT_RATIO = 0.14  # inclinación de la línea divisoria como fracción del ancho
PORTADA_VS_LINEA_GROSOR = 8
PORTADA_VS_LINEA_COLOR = (255, 255, 255)
PORTADA_VS_BADGE_COLOR = (196, 22, 28)  # rojo insignia "VS"
PORTADA_VS_BADGE_TEXTO_COLOR = (255, 255, 255)

# Logo (misma posición que en los videos, ver LOGO_POSICION más arriba)
PORTADA_LOGO_ANCHO_RATIO = 0.22
PORTADA_MARGEN_PX = 60

# Franja inferior de marca
PORTADA_MARCA_TEXTO = "RAYANDO EL CDA"
PORTADA_MARCA_ALTURA_RATIO = 0.045  # alto de la franja como fracción del alto del canvas
PORTADA_MARCA_COLOR_FONDO = (8, 24, 51)
PORTADA_MARCA_COLOR_TEXTO = (255, 255, 255)
PORTADA_MARCA_COLOR_ACENTO = (255, 215, 0)  # línea delgada superior de la franja

# Selección de fotograma con criterio
PORTADA_CANDIDATOS_N = 7  # fotogramas candidatos distribuidos en el clip (6-8)
PORTADA_CANDIDATOS_MARGEN_INICIO = 0.08  # fracción del clip a saltar al inicio (evita negros/transiciones)
PORTADA_CANDIDATOS_MARGEN_FIN = 0.08
PORTADA_CANDIDATOS_TOP_N = 4  # cuántos candidatos se numeran en el contact sheet
PORTADA_MINIATURA_ESCALA = 0.20  # escala de la vista previa de legibilidad en el contact sheet

# --- Copys automáticos ---
COPYS_HASHTAGS_BASE = ["#UdeChile", "#LaU", "#VamosLaU", "#RayandoElCDA"]

# --- Publicación a YouTube (no listado) + registro en Supabase para revisión ---
# Paso final del pipeline (ver publicar.py): sube horizontal_original.mp4 como
# video no listado y registra el candidato en la tabla rayando_cda.clips para
# que René lo revise ahí. La calificación de contenido la hace René en esa
# tabla, no este script — acá solo se valida que el archivo sea técnicamente
# subible (existe, ffprobe lo lee, duración > 0).
YOUTUBE_TITULO_TEMPLATE = "Rayando el CDA - candidato {fecha} - clip {n}"
YOUTUBE_CATEGORY_ID = "17"  # Sports
YOUTUBE_PRIVACY_STATUS = "unlisted"
YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

SUPABASE_SCHEMA = "rayando_cda"
SUPABASE_TABLE = "clips"
SUPABASE_PORTADAS_BUCKET = "portadas"

# Clips que no pasan la validación técnica no se suben; queda registrado acá
# en vez de fallar en silencio.
PUBLICAR_ERROR_LOG = BASE_DIR / "errores_publicacion.log"

# --- Detección automática de momentos (ver detectar_momentos.py) ---
# Opus 4.8: es juicio editorial sobre la transcripción completa de un
# programa (humor/declaraciones fuertes/carga emocional), corre sin
# supervisión y solo una vez por semana — el costo real (~55-65K tokens de
# entrada por programa) es marginal en ambos modelos, así que no vale la
# pena arriesgar criterio por ahorrar centavos.
CANDIDATOS_MODEL = "claude-opus-4-8"
CANDIDATOS_MIN_N = 5
CANDIDATOS_MAX_N = 8
CANDIDATOS_DURACION_MIN = 20.0
# Duración máxima: mismo límite que REEL_MAX_SECONDS.
