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

def _youtube_credentials():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    token_path = Path(
        os.environ.get("YOUTUBE_TOKEN_FILE", str(config.PROJECT_DIR / "youtube_token.json"))
    )
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


def get_youtube_client():
    from googleapiclient.discovery import build

    return build("youtube", "v3", credentials=_youtube_credentials())


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

def get_supabase_client():
    from supabase import create_client
    from supabase.client import ClientOptions

    url = _env("SUPABASE_URL")
    key = _env("SUPABASE_SERVICE_ROLE_KEY")
    return create_client(url, key, options=ClientOptions(schema=config.SUPABASE_SCHEMA))


def insertar_clip_supabase(payload: dict) -> str:
    """Inserta un registro en rayando_cda.clips. Devuelve el id insertado."""
    supabase = get_supabase_client()
    result = supabase.table(config.SUPABASE_TABLE).insert(payload).execute()
    return result.data[0]["id"]


def actualizar_clip_supabase(supabase_id: str, payload: dict) -> None:
    """Actualiza un registro existente en rayando_cda.clips (ej. al re-subir
    un clip re-cortado bajo un youtube_video_id nuevo, sin duplicar la fila
    ni perder la revisión/estado ya cargada por René)."""
    supabase = get_supabase_client()
    supabase.table(config.SUPABASE_TABLE).update(payload).eq("id", supabase_id).execute()


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

    print(f"  Subiendo a YouTube como no listado: \"{titulo}\"...")
    descripcion_yt = f"{copys.youtube_titulo}\n\n{copys.youtube_descripcion}"
    video_id = subir_youtube(video_path, titulo, descripcion=descripcion_yt)
    youtube_url = f"https://youtu.be/{video_id}"
    print(f"  Subido: {youtube_url}")

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
        "estado": "pendiente",
    }
    print(f"  Insertando en Supabase ({config.SUPABASE_SCHEMA}.{config.SUPABASE_TABLE})...")
    supabase_id = insertar_clip_supabase(payload)
    print(f"  Insertado: {supabase_id}")

    resumen = (
        f"Clip: {nombre_clip}\n"
        f"Fecha del programa (semana): {program_date}\n"
        f"YouTube video ID: {video_id}\n"
        f"YouTube URL: {youtube_url}\n"
        f"Supabase id: {supabase_id}\n"
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
