"""Orquestador automático de punta a punta: toma una grabación, obtiene
candidatos a clip y, para cada uno, reusa cortar_clip.cortar_y_publicar()
(corte horizontal/vertical con subtítulos+logo, copys, portadas, validación
técnica, subida a YouTube no listado e insert en Supabase). Sin intervención
manual en el medio.

Candidatos: lista confirmada vs. detección en vivo
---------------------------------------------------
Si existe clips/<fecha>/candidatos_<fecha>.json, se usa esa lista directo
(mismo formato que ya se venía guardando a mano: una lista de objetos con
"numero", "timestamp_inicio", "timestamp_fin", "duracion_seg" y "razon" —
ver clips/2026-05-26/candidatos_2026-05-26.json). Es el caso de cuando ya
se corrió detectar_momentos.py aparte, se revisó la lista de candidatos y
se guardó confirmada en ese JSON: esta corrida no vuelve a llamar a la API
para detectar, solo corta/publica exactamente esos candidatos, respetando
el "numero" de cada uno para el nombre de carpeta (candidato-01, etc.).

Si ese archivo no existe, cae al comportamiento de siempre: llama a
detectar_momentos.detectar_candidatos() para detectar candidatos en vivo
sobre la transcripción completa.

En ambos casos, antes de cortar se descartan candidatos que se superpongan
con clips ya cortados para esa fecha de programa (clips/<fecha>/*/
metadata.json) — tanto manuales como de una corrida automática anterior —
para no duplicar el mismo momento. En el camino de detección en vivo, los
nombres de carpeta nuevos siguen la numeración ya usada en esa fecha, así
una corrida nueva nunca sobrescribe candidatos de una corrida anterior.

Uso:
    python procesar_programa.py "2026-07-06 23-13-36.mkv"

Requiere que la grabación ya esté transcrita (transcribir.py) y las
mismas variables de entorno que detectar_momentos.py/publicar.py/
copys_ia.py (ver .env.example). Si se usa la lista confirmada
(candidatos_<fecha>.json), no hace falta ANTHROPIC_API_KEY para detectar
(copys_ia.py igual la puede necesitar para generar los copys).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import config
import cortar_clip
import detectar_momentos

_CANDIDATO_RE = re.compile(r"^candidato-(\d+)$")


def _rangos_ya_cortados(fecha_dir: Path) -> list[tuple[float, float]]:
    """Timestamps (inicio, fin) en segundos de todos los clips ya cortados
    para esta fecha de programa, leídos de metadata.json (manuales o de
    una corrida automática anterior). Carpetas sin metadata.json (de
    antes de este cambio) se ignoran silenciosamente — no hay forma de
    saber su rango."""
    if not fecha_dir.exists():
        return []
    rangos = []
    for meta_path in fecha_dir.glob("*/metadata.json"):
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            inicio = cortar_clip.parse_time(data["timestamp_inicio"])
            fin = cortar_clip.parse_time(data["timestamp_fin"])
        except (KeyError, ValueError, json.JSONDecodeError):
            continue
        rangos.append((inicio, fin))
    return rangos


def _solapa(a_inicio: float, a_fin: float, rangos: list[tuple[float, float]]) -> bool:
    return any(not (a_fin < r_ini or a_inicio > r_fin) for r_ini, r_fin in rangos)


def _siguiente_numero_candidato(fecha_dir: Path) -> int:
    """Primer número de 'candidato-NN' libre en esta fecha, para que una
    corrida nueva nunca sobrescriba carpetas de una corrida anterior."""
    if not fecha_dir.exists():
        return 1
    maximo = 0
    for p in fecha_dir.iterdir():
        if p.is_dir():
            m = _CANDIDATO_RE.match(p.name)
            if m:
                maximo = max(maximo, int(m.group(1)))
    return maximo + 1


def _ruta_candidatos_fijos(fecha_dir: Path, program_date: str) -> Path:
    return fecha_dir / f"candidatos_{program_date}.json"


def _cargar_candidatos_fijos(path: Path) -> list[tuple[str, float, float, float, str]]:
    """Carga una lista de candidatos ya confirmada (mismo formato que
    clips/<fecha>/candidatos_<fecha>.json: lista de objetos con 'numero',
    'timestamp_inicio', 'timestamp_fin', 'duracion_seg', 'razon'). Devuelve
    tuplas (nombre, timestamp_inicio, timestamp_fin, duracion_segundos,
    razon) — el nombre de carpeta usa el 'numero' del JSON directo, no se
    renumera."""
    data = json.loads(path.read_text(encoding="utf-8"))
    candidatos = []
    for c in data:
        inicio = cortar_clip.parse_time(c["timestamp_inicio"])
        fin = cortar_clip.parse_time(c["timestamp_fin"])
        duracion = c.get("duracion_seg", round(fin - inicio, 2))
        candidatos.append((f"candidato-{int(c['numero']):02d}", inicio, fin, duracion, c["razon"]))
    return candidatos


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Procesa una grabación de punta a punta: detecta candidatos, corta, "
            "genera vertical/copys/portadas, valida y sube a YouTube + Supabase. "
            "Sin intervención manual en el medio."
        )
    )
    parser.add_argument("video", help="Nombre en 'grabaciones' o ruta absoluta del video")
    args = parser.parse_args()

    video_path = cortar_clip.resolve_video(args.video)
    program_date = cortar_clip.program_date_from_name(video_path)
    fecha_dir = config.CLIPS_DIR / program_date
    rangos_existentes = _rangos_ya_cortados(fecha_dir)

    candidatos_fijos_path = _ruta_candidatos_fijos(fecha_dir, program_date)
    if candidatos_fijos_path.exists():
        print(f"Usando lista de candidatos ya confirmada: {candidatos_fijos_path}")
        items = _cargar_candidatos_fijos(candidatos_fijos_path)
        total_detectados = len(items)

        a_procesar: list[tuple[str, float, float, float, str]] = []
        for nombre, inicio, fin, duracion, razon in items:
            if _solapa(inicio, fin, rangos_existentes):
                print(
                    f"  Descartado ({nombre}, {cortar_clip.format_hhmmss(inicio)} -> "
                    f"{cortar_clip.format_hhmmss(fin)}): se superpone con un clip ya cortado."
                )
                continue
            a_procesar.append((nombre, inicio, fin, duracion, razon))
            rangos_existentes.append((inicio, fin))
    else:
        segments = cortar_clip.load_master_segments(video_path)
        if segments is None:
            sys.exit(
                f"No se encontró transcripción para '{video_path.name}' en "
                f"{config.TRANSCRIPTS_DIR / video_path.stem}. Corré transcribir.py primero."
            )

        print(f"Analizando {len(segments)} segmentos de '{video_path.name}' con {config.CANDIDATOS_MODEL}...")
        try:
            candidatos = detectar_momentos.detectar_candidatos(segments)
        except detectar_momentos.DeteccionError as e:
            sys.exit(f"Error detectando candidatos: {e}")
        print(f"{len(candidatos)} candidatos detectados.")
        total_detectados = len(candidatos)

        candidatos_nuevos = []
        for c in candidatos:
            if _solapa(c.timestamp_inicio, c.timestamp_fin, rangos_existentes):
                print(
                    f"  Descartado ({cortar_clip.format_hhmmss(c.timestamp_inicio)} -> "
                    f"{cortar_clip.format_hhmmss(c.timestamp_fin)}): se superpone con un clip ya cortado."
                )
                continue
            candidatos_nuevos.append(c)
            rangos_existentes.append((c.timestamp_inicio, c.timestamp_fin))

        numero_inicial = _siguiente_numero_candidato(fecha_dir)
        a_procesar = [
            (f"candidato-{numero_inicial + i:02d}", c.timestamp_inicio, c.timestamp_fin, c.duracion_segundos, c.razon)
            for i, c in enumerate(candidatos_nuevos)
        ]

    if not a_procesar:
        sys.exit("No quedan candidatos nuevos después de descartar los que ya se cortaron antes.")

    print(f"\nProcesando {len(a_procesar)} candidatos nuevos (de {total_detectados} detectados)...\n")

    subidos: list[tuple[str, dict]] = []
    fallidos: list[str] = []
    for i, (nombre, inicio, fin, duracion, razon) in enumerate(a_procesar):
        print(
            f"{'=' * 70}\n[{i + 1}/{len(a_procesar)}] {nombre} "
            f"({cortar_clip.format_hhmmss(inicio)} -> "
            f"{cortar_clip.format_hhmmss(fin)}, {duracion}s)\n"
            f"Razón: {razon}\n{'=' * 70}"
        )
        try:
            resultado = cortar_clip.cortar_y_publicar(video_path, inicio, fin, nombre, razon=razon)
        except Exception as e:
            print(f"  ERROR procesando {nombre}: {e}")
            fallidos.append(nombre)
            print()
            continue

        if resultado:
            subidos.append((nombre, resultado))
        else:
            fallidos.append(nombre)
        print()

    print(
        f"\n{len(subidos)} clips subidos y listos para revisión de René "
        f"(de {len(a_procesar)} candidatos procesados):"
    )
    for nombre, r in subidos:
        print(f"  - {nombre}: YouTube {r['youtube_video_id']} ({r['youtube_url']}) — Supabase id {r['supabase_id']}")

    if fallidos:
        print(
            f"\n{len(fallidos)} candidatos no se subieron ({', '.join(fallidos)}): "
            f"fallaron la validación técnica o hubo un error. Revisa la consola arriba "
            f"y {config.PUBLICAR_ERROR_LOG}."
        )


if __name__ == "__main__":
    main()
