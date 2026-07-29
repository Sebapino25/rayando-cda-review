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
