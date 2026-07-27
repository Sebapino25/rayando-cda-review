"""Publicación final (pública) de clips ya aprobados — FALLBACK MANUAL.

Desde el subsistema de publicación final desde la app (ver
docs/superpowers/specs/2026-07-27-publicacion-final-redes-design.md), el
camino principal es el botón "Publicar en redes" de la app (Historial),
que dispara la Edge Function `publicar-clip`. Este script queda como
respaldo manual, para forzar una publicación desde la PC local si la Edge
Function falla o no está disponible.

Pasa el video de YouTube de "no listado" a "público" (con el título/
descripción ya revisados por el equipo) y publica el Reel en Instagram
(@rayandoelcda). Usa row['video_url'] (subido por publicar.py al cortar el
clip) cuando está presente; si falta (clips de antes de este subsistema),
sube el video desde la carpeta local encontrada por correlación de
contenido.

Cada plataforma se activa por separado con los flags de config.py
(AUTO_PUBLICAR_YOUTUBE / AUTO_PUBLICAR_INSTAGRAM), ambos en False por
defecto — este script no publica nada solo hasta que alguien los prenda a
mano.

Busca en rayando_cda.clips las filas con estado='aprobado' y
publicado=false (igual que reprocesar_subtitulos.py, los fixtures de QA con
estado='prueba' quedan afuera del barrido general — solo se tocan con
--clip-id explícito). Si un clip ya tiene instagram_media_id, no se vuelve a
publicar en Instagram (evita duplicar). Si todas las plataformas habilitadas
terminan bien para un clip, se marca publicado=true y publicado_en=now(); si
alguna falla, el clip queda pendiente para el próximo barrido y el error
queda registrado en config.PUBLICAR_ERROR_LOG (mismo archivo que usa
publicar.py) sin abortar el resto de la corrida.

Para Instagram, la carpeta local del clip se encuentra con la misma
correlación de contenido que reprocesar_subtitulos.encontrar_carpetas_candidatas
(subtitulos.srt vs transcripcion_original) — no hay columna en Supabase con
la ruta local.

Corre en dry-run por defecto. Usa --apply para ejecutar de verdad, y
--clip-id para probar contra un solo clip (sin filtrar por estado/publicado,
igual que reprocesar_subtitulos.py, para poder probar contra fixtures).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import sys
import time
from pathlib import Path

import requests

import config
import publicar
import reprocesar_subtitulos

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


GRAPH_API_BASE = "https://graph.instagram.com"


# ---------- YouTube ----------

def publicar_youtube_publico(video_id: str, titulo: str, descripcion: str) -> None:
    """Pasa un video de 'unlisted' a 'public' y actualiza título/descripción.
    La API de YouTube exige mandar el snippet completo en el update (si se
    manda solo title/description, categoryId puede resetearse), así que
    primero se lee el snippet/status actuales y se pisan solo los campos que
    correspondan."""
    youtube = publicar.get_youtube_client()
    actual = youtube.videos().list(part="snippet,status", id=video_id).execute()
    items = actual.get("items", [])
    if not items:
        raise RuntimeError(f"No se encontró el video {video_id} en YouTube (¿ID inválido o de otro canal?)")

    snippet = items[0]["snippet"]
    status = items[0]["status"]
    snippet["title"] = titulo
    snippet["description"] = descripcion
    status["privacyStatus"] = "public"

    youtube.videos().update(
        part="snippet,status",
        body={"id": video_id, "snippet": snippet, "status": status},
    ).execute()


# ---------- Instagram ----------

def _ig_env(nombre: str) -> str:
    valor = os.environ.get(nombre)
    if not valor:
        raise RuntimeError(f"Falta la variable de entorno {nombre} (revisa tu .env)")
    return valor


def crear_contenedor_reel(video_url: str, caption: str, cover_url: str | None) -> str:
    ig_user_id = _ig_env("INSTAGRAM_BUSINESS_ACCOUNT_ID")
    token = _ig_env("INSTAGRAM_ACCESS_TOKEN")
    data = {
        "media_type": "REELS",
        "video_url": video_url,
        "caption": caption,
        "access_token": token,
    }
    if cover_url:
        data["cover_url"] = cover_url
    resp = requests.post(f"{GRAPH_API_BASE}/{ig_user_id}/media", data=data)
    if resp.status_code != 200:
        raise RuntimeError(f"Error al crear el contenedor de media ({resp.status_code}): {resp.text}")
    return resp.json()["id"]


def esperar_contenedor_listo(creation_id: str, timeout_s: int) -> None:
    """A diferencia de una foto, un contenedor de Reel no queda FINISHED al
    toque: Instagram tiene que procesar el video primero."""
    token = _ig_env("INSTAGRAM_ACCESS_TOKEN")
    inicio = time.time()
    while time.time() - inicio < timeout_s:
        resp = requests.get(
            f"{GRAPH_API_BASE}/{creation_id}",
            params={"fields": "status_code", "access_token": token},
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Error consultando el contenedor ({resp.status_code}): {resp.text}")
        status = resp.json().get("status_code")
        if status == "FINISHED":
            return
        if status == "ERROR":
            raise RuntimeError(f"El contenedor de media falló: {resp.json()}")
        time.sleep(3)
    raise TimeoutError(f"El contenedor {creation_id} no llegó a FINISHED en {timeout_s}s")


def publicar_contenedor(creation_id: str) -> str:
    ig_user_id = _ig_env("INSTAGRAM_BUSINESS_ACCOUNT_ID")
    token = _ig_env("INSTAGRAM_ACCESS_TOKEN")
    resp = requests.post(
        f"{GRAPH_API_BASE}/{ig_user_id}/media_publish",
        data={"creation_id": creation_id, "access_token": token},
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Error al publicar ({resp.status_code}): {resp.text}")
    return resp.json()["id"]


def publicar_reel(row: dict, carpeta: Path | None) -> str:
    """Publica el Reel de Instagram. Usa row['video_url'] (subido por
    publicar.py al cortar el clip) si está presente — es el camino esperado
    para clips nuevos. Si falta (clips de antes de este subsistema), cae al
    comportamiento viejo: sube vertical.mp4 desde la carpeta local
    encontrada por correlación de contenido."""
    video_url = row.get("video_url")
    if not video_url:
        if carpeta is None:
            raise RuntimeError("No hay video_url en la fila y no se encontró carpeta local para subir el video a mano.")
        vertical_path = carpeta / "vertical.mp4"
        if not vertical_path.exists():
            raise RuntimeError(f"No existe {vertical_path}")
        storage_path = f"{row.get('semana')}/{carpeta.name}.mp4"
        print(f"    video_url ausente en la fila, subiendo {vertical_path.name} a Storage ({config.SUPABASE_CLIPS_VIDEO_BUCKET}/{storage_path})...")
        video_url = publicar.subir_video_storage(vertical_path, storage_path)
        print(f"    Video URL: {video_url}")

    caption = row.get("copy_instagram") or ""
    cover_url = row.get("portada_url")
    print("    Creando contenedor de media (REELS)...")
    creation_id = crear_contenedor_reel(video_url, caption, cover_url)
    print(f"    creation_id: {creation_id}")

    print(f"    Esperando a que el contenedor esté listo (timeout {config.INSTAGRAM_CONTAINER_TIMEOUT_S}s)...")
    esperar_contenedor_listo(creation_id, config.INSTAGRAM_CONTAINER_TIMEOUT_S)

    print("    Publicando...")
    media_id = publicar_contenedor(creation_id)
    print(f"    media_id: {media_id}")
    return media_id


# ---------- Orquestación ----------

def buscar_pendientes(supabase, clip_id: str | None) -> list[dict]:
    columnas = (
        "id,estado,publicado,semana,youtube_video_id,titulo,youtube_titulo,"
        "youtube_descripcion,copy_instagram,portada_url,instagram_media_id,"
        "transcripcion_original,video_url"
    )
    query = supabase.table(config.SUPABASE_TABLE).select(columnas)
    if clip_id:
        query = query.eq("id", clip_id)
        return query.execute().data

    # Barrido general: solo clips aprobados y no publicados aún. Los
    # fixtures de QA (estado='prueba') nunca entran acá, solo con --clip-id
    # explícito (igual criterio que reprocesar_subtitulos.buscar_pendientes).
    query = query.eq("estado", "aprobado").eq("publicado", False)
    return query.execute().data


def procesar_fila(row: dict, apply: bool) -> None:
    clip_id = row["id"]
    print(f"\n=== Clip {clip_id} (semana {row.get('semana')}, estado {row.get('estado')}) ===")

    if not config.AUTO_PUBLICAR_YOUTUBE and not config.AUTO_PUBLICAR_INSTAGRAM:
        print("  Ambos flags AUTO_PUBLICAR_YOUTUBE / AUTO_PUBLICAR_INSTAGRAM están en False en config.py: nada que hacer.")
        return

    nombre_clip = row.get("titulo") or clip_id
    exitos: dict[str, bool] = {}

    if config.AUTO_PUBLICAR_YOUTUBE:
        video_id = row.get("youtube_video_id")
        titulo = row.get("youtube_titulo") or row.get("titulo") or ""
        descripcion = row.get("youtube_descripcion") or ""
        if not apply:
            print(f"  [dry-run] YouTube: pasaría {video_id} a público con título \"{titulo}\".")
            exitos["youtube"] = True
        else:
            print(f"  YouTube: publicando {video_id} como público...")
            try:
                publicar_youtube_publico(video_id, titulo, descripcion)
                print("    OK.")
                exitos["youtube"] = True
            except Exception as e:
                mensaje = f"YouTube ({video_id}): {e}"
                print(f"    ERROR: {mensaje}")
                publicar.registrar_error(nombre_clip, mensaje)
                exitos["youtube"] = False

    if config.AUTO_PUBLICAR_INSTAGRAM:
        if row.get("instagram_media_id"):
            print(f"  Instagram: ya tiene instagram_media_id ({row['instagram_media_id']}), se omite (no se duplica).")
            exitos["instagram"] = True
        elif not apply:
            print("  [dry-run] Instagram: subiría vertical.mp4, crearía el Reel y lo publicaría.")
            exitos["instagram"] = True
        else:
            carpeta = None
            if not row.get("video_url"):
                print("  Instagram: video_url ausente, buscando carpeta local...")
                carpetas = reprocesar_subtitulos.encontrar_carpetas_candidatas(row)
                if len(carpetas) != 1:
                    mensaje = (
                        f"No se encontró una única carpeta local (encontradas: {len(carpetas)}) "
                        "cuyo subtitulos.srt calce EXACTO con transcripcion_original, y la fila no tiene video_url."
                    )
                    print(f"    ERROR: {mensaje}")
                    publicar.registrar_error(nombre_clip, f"Instagram: {mensaje}")
                    exitos["instagram"] = False
                    carpeta = "saltar"  # marcador para no caer al try de abajo
                else:
                    carpeta = carpetas[0]
                    print(f"    Carpeta local: {carpeta}")

            if carpeta != "saltar":
                try:
                    media_id = publicar_reel(row, carpeta)
                    publicar.actualizar_clip_supabase(clip_id, {"instagram_media_id": media_id})
                    print(f"    OK. instagram_media_id guardado: {media_id}")
                    exitos["instagram"] = True
                except Exception as e:
                    mensaje = f"Instagram: {e}"
                    print(f"    ERROR: {mensaje}")
                    publicar.registrar_error(nombre_clip, mensaje)
                    exitos["instagram"] = False

    if not apply:
        return

    if exitos and all(exitos.values()):
        print("  Todas las plataformas habilitadas terminaron bien: marcando publicado=true.")
        publicar.actualizar_clip_supabase(
            clip_id,
            {"publicado": True, "publicado_en": _dt.datetime.now(_dt.timezone.utc).isoformat()},
        )
    else:
        print("  Alguna plataforma falló: el clip queda pendiente para el próximo barrido.")


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Publicación final: pasa el YouTube de un clip aprobado a público "
            "y/o publica su Reel en Instagram, según los flags AUTO_PUBLICAR_* "
            "de config.py."
        )
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Ejecuta de verdad. Sin este flag corre en dry-run (solo muestra qué haría).",
    )
    parser.add_argument(
        "--clip-id", default=None,
        help="Procesa solo este id de rayando_cda.clips, sin filtrar por estado/publicado (para probar contra un solo clip, incluidos fixtures).",
    )
    args = parser.parse_args()

    print(
        f"AUTO_PUBLICAR_YOUTUBE={config.AUTO_PUBLICAR_YOUTUBE}  "
        f"AUTO_PUBLICAR_INSTAGRAM={config.AUTO_PUBLICAR_INSTAGRAM}"
    )

    supabase = publicar.get_supabase_client()
    filas = buscar_pendientes(supabase, args.clip_id)

    if not filas:
        if args.clip_id:
            print(f"No se encontró el clip {args.clip_id}.")
        else:
            print("No hay clips aprobados y no publicados.")
        return

    print(f"{'[APPLY]' if args.apply else '[DRY-RUN]'} {len(filas)} clip(s) a procesar.")
    for row in filas:
        procesar_fila(row, apply=args.apply)


if __name__ == "__main__":
    main()
