"""Limpieza automática de la cola de clips.

El "programa vigente" es el MAX(semana) de rayando_cda.clips. Cuando entra
un programa nuevo (el pipeline corre la madrugada del martes), lo de
programas anteriores deja de ser "la semana en curso". Este script borra
del todo (fila de Supabase + video y portada de Storage + video no listado
de YouTube; los dos últimos best-effort) lo que ya no se va a usar:

  - estado='pendiente' de un programa anterior: nadie lo aprobó a tiempo.
  - estado='rechazado' sin publicar de un programa anterior: hubo toda la
    semana para deshacer el rechazo desde la app.
  - estado='aprobado' sin publicar cuya `semana` tiene más de
    config.DIAS_RESERVA_ANTIGUAS días: estuvo en la pestaña "Antiguas"
    (reserva) y no se publicó.

NO toca publicados ni estado='correccion_video' (trabajo en curso).

Uso:
    python limpiar_clips.py                    # dry-run: lista qué borraría
    python limpiar_clips.py --apply            # borra de verdad
    python limpiar_clips.py --apply --dias-reserva 45
    python limpiar_clips.py --apply --clip-id <uuid>   # uno puntual (sin filtros)

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


def _parse_date(valor: str | None) -> _dt.date | None:
    if not valor:
        return None
    try:
        return _dt.date.fromisoformat(str(valor)[:10])
    except ValueError:
        return None


def clips_a_limpiar(
    filas: list[dict],
    programa_vigente: str | None,
    hoy: _dt.date,
    dias_reserva: int,
) -> list[dict]:
    """Filas que corresponde borrar. Función pura, testeable.

    `programa_vigente` es el MAX(semana) válido ('YYYY-MM-DD') — las filas con
    ese `semana` (o posterior) son la semana en curso y nunca se tocan. Una
    fila con `semana` inválida o vacía nunca se toca (no se puede ubicar en el
    tiempo)."""
    corte_reserva = hoy - _dt.timedelta(days=dias_reserva)
    fecha_vigente = _parse_date(programa_vigente)
    fuera = []
    for fila in filas:
        estado = fila.get("estado")
        if fila.get("publicado") or estado == "correccion_video":
            continue
        fecha = _parse_date(fila.get("semana"))
        if fecha is None:
            continue
        if estado in ("pendiente", "rechazado"):
            if fecha_vigente is not None and fecha < fecha_vigente:
                fuera.append(fila)
        elif estado == "aprobado":
            if fecha < corte_reserva:
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


def _programa_vigente(sb) -> str | None:
    """MAX(semana) que sea una fecha ISO válida. `semana` es texto libre en la
    tabla real (hay filas de prueba tipo 'qa-fixture'), así que no alcanza con
    ordenar y tomar la primera — hay que descartar lo que no parsea."""
    res = (
        sb.table(config.SUPABASE_TABLE)
        .select("semana")
        .order("semana", desc=True)
        .limit(50)
        .execute()
    )
    for fila in res.data or []:
        if _parse_date(fila.get("semana")) is not None:
            return fila["semana"]
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--apply", action="store_true", help="Borrar de verdad (sin esto es dry-run)")
    parser.add_argument("--dias-reserva", type=int, default=config.DIAS_RESERVA_ANTIGUAS,
                        help=f"Días de vida de un aprobado sin publicar, contados desde su "
                             f"`semana` (default {config.DIAS_RESERVA_ANTIGUAS})")
    parser.add_argument("--clip-id", help="Limpiar solo este clip (ignora todos los filtros)")
    args = parser.parse_args()

    try:
        sb = publicar.get_supabase_client()
        if args.clip_id:
            filas = (
                sb.table(config.SUPABASE_TABLE)
                .select("id, estado, publicado, semana, youtube_video_id, video_url, portada_url, youtube_titulo")
                .eq("id", args.clip_id)
                .execute()
                .data
                or []
            )
            objetivo = filas
        else:
            vigente = _programa_vigente(sb)
            filas = (
                sb.table(config.SUPABASE_TABLE)
                .select("id, estado, publicado, semana, youtube_video_id, video_url, portada_url, youtube_titulo")
                .in_("estado", ["pendiente", "rechazado", "aprobado"])
                .eq("publicado", False)
                .execute()
                .data
                or []
            )
            objetivo = clips_a_limpiar(filas, vigente, _dt.date.today(), args.dias_reserva)
    except Exception as e:
        print(f"ERROR: no se pudo leer Supabase: {e}")
        return 1

    if not objetivo:
        print("Nada que limpiar.")
        return 0

    verbo = "Borrando" if args.apply else "[dry-run] borraría"
    print(f"{verbo} {len(objetivo)} clip(s):")
    errores = 0
    for fila in objetivo:
        etiqueta = fila.get("youtube_titulo") or fila["id"]
        print(f"  - [{fila.get('estado')}] {fila['id']} (semana {fila.get('semana')}) {etiqueta}")
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
