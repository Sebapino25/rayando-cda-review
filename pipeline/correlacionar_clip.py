"""Correlaciona una fila de rayando_cda.clips con su carpeta local en
clips\\<semana>\\<nombre>\\, comparando el texto de subtitulos.srt (unido)
contra transcripcion_original de esa fila. Usado por
reprocesar_subtitulos.py y reprocesar_video.py — ninguna columna en
Supabase guarda la carpeta local, así que esta es la única forma de
encontrarla.

El match tiene que ser exacto y único: si no hay ninguna coincidencia o
hay más de una, quien llama debe abortar y reportarlo, nunca adivinar.
"""

from __future__ import annotations

import difflib
import re
from pathlib import Path

import config

SRT_TIME_RE = re.compile(r"(\d{2}):(\d{2}):(\d{2}),(\d{3})")


def _srt_timestamp_to_seconds(ts: str) -> float:
    hh, mm, ss, ms = SRT_TIME_RE.match(ts.strip()).groups()
    return int(hh) * 3600 + int(mm) * 60 + int(ss) + int(ms) / 1000


def parse_srt(path: Path) -> list[tuple[float, float, str]]:
    """Lee un subtitulos.srt ya generado por cortar_clip.build_clip_srt y
    devuelve la misma estructura (cs, ce, text) que build_clip_srt/
    build_clip_ass reciben, para poder reusar esas funciones tal cual."""
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        return []
    segmentos = []
    for bloque in re.split(r"\n\s*\n", content):
        lineas = bloque.strip().splitlines()
        if len(lineas) < 3:
            continue
        inicio_str, fin_str = (t.strip() for t in lineas[1].split("-->"))
        inicio = _srt_timestamp_to_seconds(inicio_str)
        fin = _srt_timestamp_to_seconds(fin_str)
        texto = " ".join(lineas[2:]).strip()
        segmentos.append((inicio, fin, texto))
    return segmentos


def _normalizar(texto: str | None) -> str:
    return " ".join((texto or "").split())


def encontrar_carpetas_candidatas(row: dict) -> list[Path]:
    """Busca TODAS las carpetas locales (clips\\<semana>\\<nombre>\\) cuyo
    subtitulos.srt (texto unido) calza EXACTO con transcripcion_original de
    esta fila. En el caso sano esto devuelve una sola carpeta; quien llama
    es responsable de detenerse (no adivinar) si la lista queda vacía o
    tiene más de un elemento."""
    semana = row.get("semana") or ""
    fecha_dir = config.CLIPS_DIR / str(semana)
    if not fecha_dir.is_dir():
        return []

    objetivo = _normalizar(row.get("transcripcion_original"))
    if not objetivo:
        return []

    coincidencias = []
    for carpeta in sorted(p for p in fecha_dir.iterdir() if p.is_dir()):
        srt_path = carpeta / "subtitulos.srt"
        if not srt_path.exists():
            continue
        segmentos = parse_srt(srt_path)
        texto = _normalizar(" ".join(t for _, _, t in segmentos))
        if texto == objetivo:
            coincidencias.append(carpeta)
    return coincidencias


def candidata_mas_parecida(row: dict) -> tuple[Path, float] | None:
    """Diagnóstico para cuando no hubo match exacto: entre todas las
    carpetas de la misma semana, devuelve la que más se parece (ratio de
    difflib) a transcripcion_original, junto con el ratio. Es solo
    informativo — nunca se usa para elegir la carpeta a procesar."""
    semana = row.get("semana") or ""
    fecha_dir = config.CLIPS_DIR / str(semana)
    if not fecha_dir.is_dir():
        return None

    objetivo = _normalizar(row.get("transcripcion_original"))
    if not objetivo:
        return None

    mejor: tuple[Path, float] | None = None
    for carpeta in sorted(p for p in fecha_dir.iterdir() if p.is_dir()):
        srt_path = carpeta / "subtitulos.srt"
        if not srt_path.exists():
            continue
        segmentos = parse_srt(srt_path)
        texto = _normalizar(" ".join(t for _, _, t in segmentos))
        ratio = difflib.SequenceMatcher(None, texto, objetivo).ratio()
        if mejor is None or ratio > mejor[1]:
            mejor = (carpeta, ratio)
    return mejor
