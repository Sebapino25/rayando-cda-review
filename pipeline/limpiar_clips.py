"""Limpieza automática de la cola de clips.

Borra del todo (fila de rayando_cda.clips + video y portada de Supabase
Storage + video no listado de YouTube) los clips que ya no se van a usar:

  - estado='pendiente' sin revisar con más de config.DIAS_LIMPIAR_PENDIENTES
    días (default 7): si nadie los aprobó en una semana ya pasó el próximo
    programa y no se van a publicar.
  - estado='rechazado' sin publicar con más de config.DIAS_LIMPIAR_RECHAZADOS
    días (default 30): el colchón da tiempo a deshacer un rechazo desde la app.

NO toca: aprobados (son reserva -> pestaña "Antiguas" del front tras
RESERVA_DIAS), publicados, ni estado='correccion_video' (trabajo en curso).

Los borrados de YouTube/Storage son best-effort (un archivo huérfano no
bloquea el borrado de la fila, mismo criterio que la app al rechazar). Lo
disparan las corridas de auto_procesar.ps1 cuando no hay grabación pendiente.

Uso:
    python limpiar_clips.py                       # dry-run: lista qué borraría
    python limpiar_clips.py --apply               # borra de verdad
    python limpiar_clips.py --apply --dias-pendientes 10 --dias-rechazados 45
    python limpiar_clips.py --apply --clip-id <uuid>   # uno puntual (sin filtro de días)

Códigos de salida (para auto_procesar.ps1, mismo esquema que reprocesar_video.py):
    0  nada que limpiar (o dry-run)
    3  se limpió al menos un clip -> conviene avisar
    1  error (no se pudo conectar, o falló el borrado de alguna fila)
"""
from __future__ import annotations

import argparse
import datetime as _dt
import sys

import config
import publicar

# estado -> qué campo mirar para la antigüedad (con fallback a created_at).
_REFERENCIA = {
    "pendiente": ("created_at",),
    "rechazado": ("revisado_en", "created_at"),
}


def _parse_ts(valor: str | None) -> _dt.datetime | None:
    if not valor:
        return None
    texto = valor.strip().replace("Z", "+00:00")
    try:
        dt = _dt.datetime.fromisoformat(texto)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_dt.timezone.utc)
    return dt


def clips_a_limpiar(
    filas: list[dict],
    ahora: _dt.datetime,
    dias_pendientes: int,
    dias_rechazados: int,
) -> list[dict]:
    """Filas que corresponde borrar según su estado y antigüedad. Función
    pura, testeable. Ignora aprobados, publicados y correccion_video."""
    limites = {
        "pendiente": ahora - _dt.timedelta(days=dias_pendientes),
        "rechazado": ahora - _dt.timedelta(days=dias_rechazados),
    }
    fuera = []
    for fila in filas:
        estado = fila.get("estado")
        if estado not in limites or fila.get("publicado"):
            continue
        referencia = None
        for campo in _REFERENCIA[estado]:
            referencia = _parse_ts(fila.get(campo))
            if referencia is not None:
                break
        if referencia is None or referencia < limites[estado]:
            fuera.append(fila)
    return fuera


def _storage_path(url: str | None, bucket: str) -> str | None:
    """Extrae '<carpeta>/<archivo>' de una URL pública de Supabase Storage."""
    if not url:
        return None
    marcador = f"/object/public/{bucket}/"
    idx = url.find(marcador)
    if idx == -1:
        return None
    return url[idx + len(marcador):].split("?", 1)[0]


def _borrar_storage(sb, bucket: str, url: str | None) -> None:
    path = _storage_path(url, bucket)
    if not path:
        return
    try:
        sb.storage.from_(bucket).remove([path])
    except Exception as e:  # best-effort
        print(f"    aviso: no se pudo borrar {bucket}/{path}: {e}")


def _borrar_youtube(video_id: str | None) -> None:
    if not video_id:
        return
    try:
        publicar.eliminar_youtube(video_id)
    except Exception as e:  # best-effort (ej. ya borrado a mano -> 404)
        print(f"    aviso: no se pudo borrar el video de YouTube {video_id}: {e}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--apply", action="store_true", help="Borrar de verdad (sin esto es dry-run)")
    parser.add_argument("--dias-pendientes", type=int, default=config.DIAS_LIMPIAR_PENDIENTES,
                        help=f"Antigüedad mínima de un 'pendiente' en días (default {config.DIAS_LIMPIAR_PENDIENTES})")
    parser.add_argument("--dias-rechazados", type=int, default=config.DIAS_LIMPIAR_RECHAZADOS,
                        help=f"Antigüedad mínima de un 'rechazado' en días (default {config.DIAS_LIMPIAR_RECHAZADOS})")
    parser.add_argument("--clip-id", help="Limpiar solo este clip (ignora el filtro de días)")
    args = parser.parse_args()

    try:
        sb = publicar.get_supabase_client()
        query = sb.table(config.SUPABASE_TABLE).select(
            "id, estado, publicado, revisado_en, created_at, "
            "youtube_video_id, video_url, portada_url, youtube_titulo"
        ).in_("estado", ["pendiente", "rechazado"]).eq("publicado", False)
        if args.clip_id:
            query = query.eq("id", args.clip_id)
        filas = query.execute().data or []
    except Exception as e:
        print(f"ERROR: no se pudo leer Supabase: {e}")
        return 1

    ahora = _dt.datetime.now(_dt.timezone.utc)
    if args.clip_id:
        objetivo = filas
    else:
        objetivo = clips_a_limpiar(filas, ahora, args.dias_pendientes, args.dias_rechazados)

    if not objetivo:
        print("Nada que limpiar.")
        return 0

    verbo = "Borrando" if args.apply else "[dry-run] borraría"
    print(f"{verbo} {len(objetivo)} clip(s):")
    errores = 0
    for fila in objetivo:
        etiqueta = fila.get("youtube_titulo") or fila["id"]
        fecha = fila.get("revisado_en") or fila.get("created_at")
        print(f"  - [{fila.get('estado')}] {fila['id']} ({etiqueta}) desde {fecha}")
        if not args.apply:
            continue
        _borrar_youtube(fila.get("youtube_video_id"))
        _borrar_storage(sb, config.SUPABASE_CLIPS_VIDEO_BUCKET, fila.get("video_url"))
        _borrar_storage(sb, config.SUPABASE_PORTADAS_BUCKET, fila.get("portada_url"))
        try:
            sb.table(config.SUPABASE_TABLE).delete().eq("id", fila["id"]).execute()
            print("    fila borrada")
        except Exception as e:
            print(f"    ERROR borrando la fila: {e}")
            errores += 1

    if not args.apply:
        return 0
    return 1 if errores else 3


if __name__ == "__main__":
    sys.exit(main())
