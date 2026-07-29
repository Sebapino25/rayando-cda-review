"""Cierra el loop de corrección de in/out points pedida por el equipo
editorial: busca en rayando_cda.clips las filas con
estado='correccion_video', usa la API de Anthropic (interpretar_correccion)
para interpretar comentarios_video contra la transcripción completa del
programa y, si hay confianza, vuelve a cortar el clip (horizontal +
vertical con subtítulos/logo/portada) desde la grabación original con el
nuevo rango, lo sube como nuevo video no listado de YouTube y actualiza la
fila (estado vuelve a 'pendiente').

Nunca adivina: si la interpretación no tiene confianza, o la carpeta local
no se puede correlacionar sin ambigüedad, aborta sin tocar nada.

Corre en dry-run por defecto. Usa --apply para ejecutar de verdad,
--clip-id para probar contra un solo clip, y --uno para procesar solo la
fila más antigua pendiente (pensado para el disparador automático, que
llama a este script cada 5 minutos y deja que la siguiente corrida
procese el resto).
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import config
import cortar_clip
import publicar
from correlacionar_clip import candidata_mas_parecida, encontrar_carpetas_candidatas
from interpretar_correccion import InterpretacionError, interpretar_correccion


@dataclass
class DecisionReproceso:
    carpeta: Path | None
    nuevo_inicio: float | None
    nuevo_fin: float | None
    motivo_abort: str | None
    interpretacion_motivo: str = ""


def cargar_segments_de_carpeta(carpeta: Path) -> list[dict] | None:
    """Encuentra la grabación original (metadata.json -> video_fuente) y
    devuelve sus segmentos maestros de transcripción (mismo formato que
    usa detectar_momentos/interpretar_correccion)."""
    import json

    metadata_path = carpeta / "metadata.json"
    if not metadata_path.exists():
        return None
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    video_path = Path(metadata["video_fuente"])
    return cortar_clip.load_master_segments(video_path)


def decidir(row: dict) -> DecisionReproceso:
    """Localiza la carpeta local y determina los nuevos timestamps a
    partir de comentarios_video, SIN tocar ningún archivo. motivo_abort
    distinto de None significa "no continuar, avisar y no tocar nada"."""
    carpetas = encontrar_carpetas_candidatas(row)
    if len(carpetas) == 0:
        pista = candidata_mas_parecida(row)
        extra = f" Candidata más parecida (no usada): {pista[0]} (similitud {pista[1]:.1%})." if pista else ""
        return DecisionReproceso(
            carpeta=None, nuevo_inicio=None, nuevo_fin=None,
            motivo_abort=f"No se encontró ninguna carpeta local para el clip {row.get('id')}.{extra}",
        )
    if len(carpetas) > 1:
        nombres = ", ".join(str(c) for c in carpetas)
        return DecisionReproceso(
            carpeta=None, nuevo_inicio=None, nuevo_fin=None,
            motivo_abort=f"Ambigüedad: {len(carpetas)} carpetas calzan con el clip {row.get('id')}: {nombres}",
        )

    carpeta = carpetas[0]
    segments = cargar_segments_de_carpeta(carpeta)
    if not segments:
        return DecisionReproceso(
            carpeta=carpeta, nuevo_inicio=None, nuevo_fin=None,
            motivo_abort=f"No se pudo cargar la transcripción maestra para {carpeta} (metadata.json/video_fuente).",
        )

    try:
        interpretacion = interpretar_correccion(row.get("comentarios_video") or "", segments)
    except InterpretacionError as e:
        return DecisionReproceso(
            carpeta=carpeta, nuevo_inicio=None, nuevo_fin=None,
            motivo_abort=f"Falló la interpretación del pedido con la API de Anthropic: {e}",
        )

    if not interpretacion.confianza:
        return DecisionReproceso(
            carpeta=carpeta, nuevo_inicio=None, nuevo_fin=None,
            motivo_abort=f"La IA no tiene confianza en el pedido '{row.get('comentarios_video')}': {interpretacion.motivo}",
        )

    return DecisionReproceso(
        carpeta=carpeta,
        nuevo_inicio=interpretacion.timestamp_inicio,
        nuevo_fin=interpretacion.timestamp_fin,
        motivo_abort=None,
        interpretacion_motivo=interpretacion.motivo,
    )


def buscar_pendientes(supabase, clip_id: str | None) -> list[dict]:
    columnas = (
        "id,semana,estado,comentarios_video,transcripcion_original,"
        "titulo,youtube_titulo,youtube_descripcion,youtube_video_id,created_at"
    )
    query = supabase.table(config.SUPABASE_TABLE).select(columnas).eq("estado", "correccion_video")
    if clip_id:
        query = query.eq("id", clip_id)
    filas = query.order("created_at").execute().data
    # Defensivo: el fixture de QA (estado='prueba') nunca debería calzar
    # con este filtro, pero se excluye igual por si queda en un estado raro.
    return [f for f in filas if f.get("estado") != "prueba"]


from correlacionar_clip import respaldar_version_anterior
import portadas


class EjecutarError(Exception):
    """Falló un paso técnico al ejecutar la corrección (recorte, validación o subida)."""


def _ejecutar_recorte(carpeta: Path, video_path: Path, nuevo_inicio: float, nuevo_fin: float, nombre_clip: str):
    """Re-corta horizontal+vertical (subtítulos/logo/portada) con el nuevo
    rango, reusando las funciones de cortar_clip.py. Devuelve
    (vertical_path, transcripcion_texto)."""
    horizontal_path = carpeta / "horizontal_original.mp4"
    try:
        _method, actual_start, _actual_end = cortar_clip.cut_horizontal(
            video_path, nuevo_inicio, nuevo_fin, horizontal_path
        )
    except Exception as e:
        raise EjecutarError(f"Falló el recorte horizontal: {e}") from e

    # cut_horizontal agrega un margen de aire (config.CLIP_PAD_SECONDS) antes
    # del inicio pedido, así que el video ahora arranca en actual_start, no en
    # nuevo_inicio. Sin este ajuste los subtítulos quedarían desincronizados
    # hasta CLIP_PAD_SECONDS (mismo cálculo que cortar_clip.cortar_y_publicar).
    pad_offset = nuevo_inicio - actual_start

    segments = cortar_clip.load_master_segments(video_path)
    clipped = cortar_clip.clip_segments(segments, nuevo_inicio, nuevo_fin) if segments else []
    if pad_offset and clipped:
        clipped = [(cs + pad_offset, ce + pad_offset, text) for cs, ce, text in clipped]
    has_subtitles = bool(clipped)
    if has_subtitles:
        captions = cortar_clip.split_into_captions(clipped)
        cortar_clip.build_clip_srt(captions, carpeta / "subtitulos.srt")
        cortar_clip.build_clip_ass(captions, carpeta / "subtitulos.ass")

    overrides = cortar_clip._cargar_overrides(nombre_clip)
    titulo_portada = overrides.get("titulo_portada")
    try:
        cortar_clip.build_vertical(carpeta, has_subtitles, titulo_portada)
    except Exception as e:
        raise EjecutarError(f"Falló la generación del vertical: {e}") from e

    try:
        portadas.build_portadas(carpeta, horizontal_path, titulo_portada, overrides)
    except Exception as e:
        raise EjecutarError(f"Falló la generación de la portada: {e}") from e

    vertical_path = carpeta / "vertical.mp4"
    try:
        publicar.validar_clip(vertical_path)
    except publicar.ClipInvalido as e:
        raise EjecutarError(f"El vertical.mp4 recién generado no pasó la validación técnica: {e}") from e

    transcripcion_texto = cortar_clip.join_transcripcion(clipped)
    return vertical_path, transcripcion_texto


def procesar_fila(row: dict, apply: bool) -> bool:
    """Procesa una fila estado='correccion_video'. Devuelve True si se
    corrigió con éxito (o si en dry-run no hubiera nada que abortar),
    False si abortó o falló un paso técnico."""
    clip_id = row["id"]
    print(f"\n=== Clip {clip_id} (semana {row.get('semana')}) ===")
    print(f"  Pedido: {row.get('comentarios_video')!r}")

    decision = decidir(row)
    if decision.motivo_abort:
        print(f"  ABORTADO: {decision.motivo_abort}")
        return False

    print(f"  Carpeta local: {decision.carpeta}")
    print(f"  Nuevo rango: {cortar_clip.format_hhmmss(decision.nuevo_inicio)} -> {cortar_clip.format_hhmmss(decision.nuevo_fin)}")
    print(f"  Interpretación: {decision.interpretacion_motivo}")

    if not apply:
        print("  [dry-run] Se respaldaría la versión anterior, se re-cortaría con este rango, "
              "se subiría un video nuevo a YouTube y se actualizaría la fila a estado='pendiente'.")
        return True

    metadata_path = decision.carpeta / "metadata.json"
    import json
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    video_path = Path(metadata["video_fuente"])
    nombre_clip = decision.carpeta.name
    program_date = cortar_clip.program_date_from_name(video_path)

    print("  Respaldando versión anterior (vertical.mp4 + horizontal_original.mp4 + subtítulos) en vN\\...")
    destino_backup = respaldar_version_anterior(decision.carpeta)
    print(f"    Respaldado en: {destino_backup}")

    try:
        vertical_path, transcripcion_texto = _ejecutar_recorte(
            decision.carpeta, video_path, decision.nuevo_inicio, decision.nuevo_fin, nombre_clip
        )
    except EjecutarError as e:
        print(f"  FALLÓ: {e}")
        print(f"  (versión anterior respaldada en {destino_backup}, la fila de Supabase no se tocó)")
        return False

    titulo = row.get("titulo") or "Rayando el CDA"
    descripcion = f"{row.get('youtube_titulo') or ''}\n\n{row.get('youtube_descripcion') or ''}".strip()
    print(f'  Subiendo a YouTube como no listado: "{titulo}"...')
    try:
        nuevo_video_id = publicar.subir_youtube(vertical_path, titulo, descripcion=descripcion)
    except Exception as e:
        print(f"  FALLÓ la subida a YouTube: {e}")
        return False
    nueva_url = f"https://youtu.be/{nuevo_video_id}"
    print(f"  Subido: {nueva_url}")

    portada_storage_path = f"{program_date}/{nombre_clip}.jpg"
    try:
        publicar.subir_portada_storage(decision.carpeta / "portada_vertical.jpg", portada_storage_path)
    except Exception as e:
        print(f"  ADVERTENCIA: no se pudo re-subir la portada a Storage ({e}). portada_url queda con la imagen anterior.")

    video_storage_path = f"{program_date}/{nombre_clip}.mp4"
    try:
        publicar.subir_video_storage(vertical_path, video_storage_path)
    except Exception as e:
        print(f"  FALLÓ la re-subida del video a Storage: {e}")
        return False

    print("  Actualizando Supabase (estado -> pendiente, nuevos timestamps, youtube_video_id)...")
    publicar.actualizar_clip_supabase(
        clip_id,
        {
            "youtube_video_id": nuevo_video_id,
            "timestamp_inicio": decision.nuevo_inicio,
            "timestamp_fin": decision.nuevo_fin,
            "transcripcion": transcripcion_texto,
            "transcripcion_original": transcripcion_texto,
            "estado": "pendiente",
            "revisado_por": None,
            "revisado_en": None,
        },
    )

    video_id_anterior = row.get("youtube_video_id")
    resumen_extra = (
        "\n--- Reproceso de video (corrección de in/out) ---\n"
        f"Pedido: {row.get('comentarios_video')}\n"
        f"Nuevo rango: {cortar_clip.format_hhmmss(decision.nuevo_inicio)} -> {cortar_clip.format_hhmmss(decision.nuevo_fin)}\n"
        f"YouTube video ID anterior: {video_id_anterior}\n"
        f"YouTube video ID nuevo: {nuevo_video_id}\n"
        f"YouTube URL nueva: {nueva_url}\n"
    )
    with (decision.carpeta / "resumen.txt").open("a", encoding="utf-8") as f:
        f.write(resumen_extra)

    print(f"  Listo. Clip vuelve a 'pendiente' para revisión. youtube_video_id: {video_id_anterior} -> {nuevo_video_id}")
    print(f"  NOTA: el video anterior ({video_id_anterior}) sigue en YouTube como no listado; bórralo a mano si ya no sirve.")
    return True
