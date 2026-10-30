"""Paso final del pipeline: sube el clip vertical final (9:16, con logo y
subtítulos ya incrustados — el mismo archivo que se publicaría) a YouTube
como no listado, y registra el candidato en la tabla rayando_cda.clips de
Supabase, para que René revise ahí exactamente lo que se publicaría (en vez
de revisar la carpeta local).

Antes de subir, valida que el archivo sea técnicamente subible (existe,
ffprobe lo puede leer, duración > 0). Si falla esa validación, no se sube y
queda registrado en config.PUBLICAR_ERROR_LOG — la calificación de
contenido ("¿es bueno?") la hace René en Supabase, no este script.

Requiere variables de entorno (ver .env.example): YOUTUBE_CLIENT_ID,
YOUTUBE_CLIENT_SECRET, YOUTUBE_TOKEN_FILE, SUPABASE_URL,
SUPABASE_SERVICE_ROLE_KEY.
"""

from __future__ import annotations

import datetime as _dt
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

import config
import ffmpeg_utils

load_dotenv(config.PROJECT_DIR / ".env")


class ClipInvalido(Exception):
    """El archivo de video no pasó la validación técnica previa a la subida."""


@dataclass
class Copys:
    titulo_seo: str
    titulo_portada: str
    copy_instagram: str
    youtube_titulo: str
    youtube_descripcion: str
    copy_tiktok: str


def _env(nombre: str) -> str:
    valor = os.environ.get(nombre)
    if not valor:
        raise RuntimeError(f"Falta la variable de entorno {nombre} (revisa tu .env)")
    return valor


# ---------- Validación técnica ----------

def validar_clip(video_path: Path) -> float:
    """Valida que el clip exista y sea un video legible con duración > 0.
    Devuelve la duración en segundos. Lanza ClipInvalido si falla."""
    if not video_path.exists():
        raise ClipInvalido(f"No existe el archivo: {video_path}")
    try:
        duracion = ffmpeg_utils.ffprobe_duration(video_path)
    except Exception as e:
        raise ClipInvalido(
            f"ffprobe no pudo leer el archivo (posible corrupción): {e}"
        ) from e
    if duracion <= 0:
        raise ClipInvalido(f"Duración inválida ({duracion}s)")
    return duracion


# ---------- YouTube ----------

# Credenciales de la cuenta de YouTube. Para un programa que no es Rayando
# tienen que estar en su .env.<programa>: si se heredaran de .env, el programa
# subiría al canal de Recda y gastaría la cuota de su proyecto de Google Cloud.
YOUTUBE_CLAVES_CUENTA = ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_TOKEN_FILE")


def _youtube_token_path() -> Path:
    return Path(os.environ.get("YOUTUBE_TOKEN_FILE", str(config.PROJECT_DIR / "youtube_token.json")))


def _claves_propias_del_programa() -> set[str]:
    from dotenv import dotenv_values

    valores = dotenv_values(config.PROJECT_DIR / f".env.{config.PROGRAMA}")
    return {k for k, v in valores.items() if v}


def youtube_faltante(exigir_token: bool = True) -> str | None:
    """None si el programa puede usar YouTube; si no, qué falta. Rayando no
    se revisa (comportamiento de siempre). Otro programa necesita su cuenta
    propia en .env.<programa> y, si exigir_token, el token ya autorizado con
    autorizar_youtube.py (las corridas son desatendidas: no hay quién apruebe
    en el navegador)."""
    if config.PROGRAMA == "rayando":
        return None
    propias = _claves_propias_del_programa()
    faltan = [k for k in YOUTUBE_CLAVES_CUENTA if k not in propias]
    if faltan:
        return f"faltan en .env.{config.PROGRAMA}: {', '.join(faltan)} (no se heredan de .env)"
    if exigir_token and not _youtube_token_path().exists():
        return (
            f"no existe {_youtube_token_path()}: autoriza el canal con "
            f"python autorizar_youtube.py --programa {config.PROGRAMA}"
        )
    return None


def _youtube_credentials():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    token_path = _youtube_token_path()
    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), config.YOUTUBE_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            client_config = {
                "installed": {
                    "client_id": _env("YOUTUBE_CLIENT_ID"),
                    "client_secret": _env("YOUTUBE_CLIENT_SECRET"),
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": ["http://localhost"],
                }
            }
            flow = InstalledAppFlow.from_client_config(client_config, config.YOUTUBE_SCOPES)
            # Primera vez: abre el navegador para pedir permiso. Corridas
            # siguientes reusan el token guardado en YOUTUBE_TOKEN_FILE.
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json(), encoding="utf-8")

    return creds


_canal_verificado = False


def canal_autorizado(youtube) -> tuple[str, str]:
    """(id, nombre) del canal al que pertenece el token (1 unidad de cuota)."""
    items = youtube.channels().list(part="id,snippet", mine=True).execute().get("items", [])
    if not items:
        raise RuntimeError("El token de YouTube no tiene canal asociado.")
    return items[0]["id"], items[0]["snippet"]["title"]


def get_youtube_client():
    """Cliente de la API de YouTube del programa. Si config.YOUTUBE_CANAL_ID
    está definido, verifica una vez por corrida que el token sea de ese canal
    (así un token cambiado por error no sube clips al canal equivocado)."""
    global _canal_verificado
    from googleapiclient.discovery import build

    falta = youtube_faltante()
    if falta:
        raise RuntimeError(f"YouTube de {config.PROGRAMA_NOMBRE} no está listo: {falta}")
    youtube = build("youtube", "v3", credentials=_youtube_credentials())
    if config.YOUTUBE_CANAL_ID and not _canal_verificado:
        canal_id, nombre = canal_autorizado(youtube)
        if canal_id != config.YOUTUBE_CANAL_ID:
            raise RuntimeError(
                f"El token de YouTube es del canal '{nombre}' ({canal_id}), pero "
                f"{config.PROGRAMA_NOMBRE} espera {config.YOUTUBE_CANAL_ID}. No se sube nada."
            )
        _canal_verificado = True
    return youtube


def subir_youtube(video_path: Path, titulo: str, descripcion: str = "") -> str:
    """Sube video_path a YouTube como video no listado. Devuelve el video_id."""
    from googleapiclient.http import MediaFileUpload

    youtube = get_youtube_client()
    body = {
        "snippet": {
            "title": titulo,
            "description": descripcion or "",
            "categoryId": config.YOUTUBE_CATEGORY_ID,
        },
        "status": {
            "privacyStatus": config.YOUTUBE_PRIVACY_STATUS,
            "selfDeclaredMadeForKids": False,
        },
    }
    media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True, mimetype="video/mp4")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"    Subiendo a YouTube... {int(status.progress() * 100)}%")
    return response["id"]


def eliminar_youtube(video_id: str) -> None:
    """Elimina un video de YouTube. La API no permite reemplazar el archivo
    de un video existente manteniendo su ID/link, así que reemplazar un clip
    significa subir uno nuevo (nuevo video_id/URL) y borrar el anterior."""
    youtube = get_youtube_client()
    youtube.videos().delete(id=video_id).execute()


# ---------- Supabase ----------

# Errores de red/infra transitorios de Supabase que conviene reintentar en
# vez de fallar la corrida entera y mandar una alerta al equipo: cortes de
# DNS del PC (getaddrinfo), timeouts de conexión/lectura, y los 5xx que
# Cloudflare devuelve —como una página HTML entera— cuando el origen de
# Supabase no responde a tiempo. Caso real 2026-09-08: un 522 en el primer
# select de reprocesar_subtitulos.py cortó la corrida y disparó un mail con
# la página de error de Cloudflare pegada adentro; el mismo select andaba
# bien ~10 s después.
_HTTP_TRANSITORIOS = {500, 502, 503, 504, 520, 521, 522, 524}


def _es_error_transitorio(exc: Exception) -> bool:
    try:
        import httpx

        if isinstance(
            exc,
            (
                httpx.ConnectError,
                httpx.ConnectTimeout,
                httpx.ReadTimeout,
                httpx.WriteTimeout,
                httpx.PoolTimeout,
                httpx.RemoteProtocolError,
            ),
        ):
            return True
    except ImportError:
        pass

    # postgrest.exceptions.APIError y las excepciones de storage3 exponen el
    # código HTTP como .code (str o int) o dentro de args[0] cuando se
    # construyeron desde un dict.
    codigo = getattr(exc, "code", None)
    if codigo is None and exc.args and isinstance(exc.args[0], dict):
        codigo = exc.args[0].get("code")
    try:
        if codigo is not None and int(codigo) in _HTTP_TRANSITORIOS:
            return True
    except (TypeError, ValueError):
        pass

    texto = str(exc).lower()
    return (
        "getaddrinfo failed" in texto
        or "temporary failure in name resolution" in texto
        or "the initial connection between cloudflare" in texto
    )


def reintentar_transitorio(fn, *, intentos: int = 4, espera_inicial: float = 3.0, factor: float = 3.0):
    """Ejecuta fn() reintentando ante errores de red/infra transitorios (ver
    _es_error_transitorio) con backoff exponencial. Cualquier otra excepción
    se re-lanza en el acto. Si se agotan los intentos, re-lanza la última."""
    espera = espera_inicial
    for intento in range(1, intentos + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - se re-lanza si no es transitorio
            if intento == intentos or not _es_error_transitorio(exc):
                raise
            print(
                f"  Error transitorio de Supabase ({type(exc).__name__}); "
                f"reintento {intento}/{intentos - 1} en {espera:.0f}s..."
            )
            time.sleep(espera)
            espera *= factor


def get_supabase_client():
    from supabase import create_client
    from supabase.client import ClientOptions

    url = _env("SUPABASE_URL")
    key = _env("SUPABASE_SERVICE_ROLE_KEY")
    return create_client(url, key, options=ClientOptions(schema=config.SUPABASE_SCHEMA))


def insertar_clip_supabase(payload: dict) -> str:
    """Inserta un registro en rayando_cda.clips. Devuelve el id insertado."""
    supabase = get_supabase_client()
    result = reintentar_transitorio(supabase.table(config.SUPABASE_TABLE).insert(payload).execute)
    return result.data[0]["id"]


def actualizar_clip_supabase(supabase_id: str, payload: dict) -> None:
    """Actualiza un registro existente en rayando_cda.clips (ej. al re-subir
    un clip re-cortado bajo un youtube_video_id nuevo, sin duplicar la fila
    ni perder la revisión/estado ya cargada por René)."""
    supabase = get_supabase_client()
    reintentar_transitorio(
        supabase.table(config.SUPABASE_TABLE).update(payload).eq("id", supabase_id).execute
    )


def subir_portada_storage(portada_path: Path, storage_path: str) -> str | None:
    """Sube la portada vertical generada al bucket público 'portadas' de
    Supabase Storage y devuelve su URL pública. Si el archivo no existe
    (por ejemplo, portadas.build_portadas falló silenciosamente) devuelve
    None sin cortar la publicación — la portada no es bloqueante.
    René/Cristián pueden reemplazarla después desde la app de revisión."""
    if not portada_path.exists():
        print(f"  Aviso: no se encontró {portada_path}, se publica sin portada_url.")
        return None
    supabase = get_supabase_client()
    data = portada_path.read_bytes()
    reintentar_transitorio(
        lambda: supabase.storage.from_(config.SUPABASE_PORTADAS_BUCKET).upload(
            storage_path,
            data,
            {"content-type": "image/jpeg", "upsert": "true"},
        )
    )
    return supabase.storage.from_(config.SUPABASE_PORTADAS_BUCKET).get_public_url(storage_path)


def subir_video_storage(video_path: Path, storage_path: str) -> str:
    """Sube el vertical.mp4 final al bucket público clips-video de Supabase
    Storage y devuelve su URL pública. A diferencia de la portada, esto NO
    es opcional: sin video_url la publicación final (Edge Function
    publicar-clip) no tiene forma de acceder al archivo — una falla acá se
    propaga, no hay fallback silencioso como en subir_portada_storage."""
    supabase = get_supabase_client()
    data = video_path.read_bytes()
    reintentar_transitorio(
        lambda: supabase.storage.from_(config.SUPABASE_CLIPS_VIDEO_BUCKET).upload(
            storage_path, data, {"content-type": "video/mp4", "upsert": "true"}
        )
    )
    return supabase.storage.from_(config.SUPABASE_CLIPS_VIDEO_BUCKET).get_public_url(storage_path)


# ---------- Orquestación ----------

def numero_clip(program_date: str, nombre_clip: str) -> int:
    """Posición (1-based) del clip entre todos los clips ya cortados para esa
    fecha de programa, en orden alfabético de nombre. Solo se usa para armar
    un título genérico de YouTube ("clip N"), no importa si cambia si se
    cortan clips fuera de orden — el título real lo define después la
    revisión editorial."""
    fecha_dir = config.CLIPS_DIR / program_date
    hermanos = sorted(p.name for p in fecha_dir.iterdir() if p.is_dir())
    return hermanos.index(nombre_clip) + 1


def _patron_capitulo(plantilla: str) -> str:
    return re.escape(plantilla).replace(re.escape("{n}"), r"\d+")


_LINEA_CAPITULO_RE = re.compile(rf"^[ \t]*{_patron_capitulo(config.CAPITULO_LINEA_YOUTUBE)}[ \t]*$", re.MULTILINE)
_HASHTAG_CAPITULO_RE = re.compile(rf"[ \t]*{_patron_capitulo(config.CAPITULO_HASHTAG)}\b")


def descripcion_con_capitulo(descripcion: str, capitulo: int | None) -> str:
    """Agrega (de forma determinista, no vía IA) la línea "Del capítulo N de
    Rayando el CDA" y, al final, el hashtag #RECDA<N>. Si el clip no tiene
    capítulo, devuelve la descripción tal cual. Es idempotente: antes de
    agregar, quita una línea/hashtag de capítulo previo (así
    corregir_capitulo.py puede reemplazar el 80 por el 81 sin duplicar).
    Misma lógica que supabase/functions/publicar-clip/capitulo.ts."""
    if capitulo is None:
        return descripcion
    limpia = _HASHTAG_CAPITULO_RE.sub("", _LINEA_CAPITULO_RE.sub("", descripcion or ""))
    limpia = re.sub(r"\n{3,}", "\n\n", limpia).strip()
    linea = config.CAPITULO_LINEA_YOUTUBE.format(n=capitulo)
    hashtag = config.CAPITULO_HASHTAG.format(n=capitulo)
    return f"{limpia}\n\n{linea}\n{hashtag}" if limpia else f"{linea}\n{hashtag}"


def titulo_generico(program_date: str, n_clip: int) -> str:
    return config.YOUTUBE_TITULO_TEMPLATE.format(fecha=program_date, n=n_clip)


def registrar_error(nombre_clip: str, mensaje: str) -> None:
    config.PUBLICAR_ERROR_LOG.parent.mkdir(parents=True, exist_ok=True)
    linea = f"[{_dt.datetime.now().isoformat(timespec='seconds')}] {nombre_clip}: {mensaje}\n"
    with config.PUBLICAR_ERROR_LOG.open("a", encoding="utf-8") as f:
        f.write(linea)


def publicar_clip(
    out_dir: Path,
    nombre_clip: str,
    program_date: str,
    video_path: Path,
    copys: Copys,
    razon: str | None,
    transcripcion: str,
    timestamp_inicio: float,
    timestamp_fin: float,
    capitulo: int | None = None,
) -> dict | None:
    """Valida, sube el vertical final a YouTube y registra en Supabase.
    Devuelve {"youtube_video_id", "youtube_url", "supabase_id"}, o None si la
    validación técnica falló (ver PUBLICAR_ERROR_LOG). También escribe
    resumen.txt en out_dir como respaldo local de lo que se subió."""
    try:
        validar_clip(video_path)
    except ClipInvalido as e:
        print(
            f"  ADVERTENCIA: '{nombre_clip}' no pasó la validación técnica, no se sube.\n"
            f"    Motivo: {e}\n"
            f"    Registrado en: {config.PUBLICAR_ERROR_LOG}"
        )
        registrar_error(nombre_clip, str(e))
        return None

    n_clip = numero_clip(program_date, nombre_clip)
    titulo = titulo_generico(program_date, n_clip)

    falta_youtube = youtube_faltante() if config.SUBIR_YOUTUBE else None
    if falta_youtube:
        # Los shorts no se frenan: sin YouTube listo se revisan desde Storage.
        print(f"  ADVERTENCIA: no se sube a YouTube ({falta_youtube}). Se revisa desde Supabase Storage.")
    if config.SUBIR_YOUTUBE and not falta_youtube:
        print(f"  Subiendo a YouTube como no listado: \"{titulo}\"...")
        descripcion_yt = descripcion_con_capitulo(
            f"{copys.youtube_titulo}\n\n{copys.youtube_descripcion}", capitulo
        )
        video_id = subir_youtube(video_path, titulo, descripcion=descripcion_yt)
        youtube_url = f"https://youtu.be/{video_id}"
        print(f"  Subido: {youtube_url}")
    else:
        video_id, youtube_url = None, None
        if not falta_youtube:
            print("  (SUBIR_YOUTUBE=False: no se sube a YouTube; se revisa desde Supabase Storage)")

    print("  Subiendo portada generada a Supabase Storage...")
    portada_storage_path = f"{program_date}/{nombre_clip}.jpg"
    try:
        portada_url = subir_portada_storage(out_dir / "portada_vertical.jpg", portada_storage_path)
    except Exception as e:
        print(f"  ADVERTENCIA: no se pudo subir la portada a Storage ({e}). Se publica sin portada_url.")
        portada_url = None
    if portada_url:
        print(f"  Portada: {portada_url}")

    print("  Subiendo vertical.mp4 a Supabase Storage...")
    video_storage_path = f"{program_date}/{nombre_clip}.mp4"
    video_url = subir_video_storage(video_path, video_storage_path)
    print(f"  Video URL: {video_url}")

    payload = {
        "youtube_video_id": video_id,
        "titulo": titulo,
        "copy_instagram": copys.copy_instagram,
        "youtube_titulo": copys.youtube_titulo,
        "youtube_descripcion": copys.youtube_descripcion,
        "copy_tiktok": copys.copy_tiktok,
        "razon": razon,
        "transcripcion": transcripcion,
        "timestamp_inicio": timestamp_inicio,
        "timestamp_fin": timestamp_fin,
        "semana": program_date,
        "capitulo": capitulo,
        "estado": "pendiente",
        "portada_url": portada_url,
        "video_url": video_url,
    }
    print(f"  Insertando en Supabase ({config.SUPABASE_SCHEMA}.{config.SUPABASE_TABLE})...")
    supabase_id = insertar_clip_supabase(payload)
    print(f"  Insertado: {supabase_id}")

    resumen = (
        f"Clip: {nombre_clip}\n"
        f"Fecha del programa (semana): {program_date}\n"
        f"Capítulo: {capitulo if capitulo is not None else '(sin capítulo)'}\n"
        f"YouTube video ID: {video_id}\n"
        f"YouTube URL: {youtube_url}\n"
        f"Supabase id: {supabase_id}\n"
        f"Portada: {portada_url or '(no se pudo subir, revisar manualmente)'}\n"
        f"Video URL: {video_url}\n"
        f"Estado: pendiente\n"
        f"Título subido (genérico, no final): {titulo}\n"
        f"Razón: {razon or '(no especificada)'}\n"
        f"Timestamps: {ffmpeg_utils.format_hhmmss(timestamp_inicio)} -> "
        f"{ffmpeg_utils.format_hhmmss(timestamp_fin)} "
        f"({timestamp_inicio:.3f}s -> {timestamp_fin:.3f}s)\n"
        f"Subido: {_dt.datetime.now().isoformat(timespec='seconds')}\n"
    )
    (out_dir / "resumen.txt").write_text(resumen, encoding="utf-8")

    return {"youtube_video_id": video_id, "youtube_url": youtube_url, "supabase_id": supabase_id}
