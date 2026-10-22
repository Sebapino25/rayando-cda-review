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
    python procesar_programa.py "2026-10-28 22-50-00.mkv" --extraordinario
    python procesar_programa.py "2026-10-19 22-53-58.mkv" --dry-run

Capítulo: cada clip queda con el capítulo del programa (ver capitulos.py
para las reglas; --extraordinario y --capitulo N para los casos fuera de
lunes). --dry-run no corta ni sube nada: muestra el capítulo y la
descripción final de YouTube.

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

import capitulos
import config
import cortar_clip
import detectar_momentos
import publicar

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


def _copys_de_carpeta(carpeta: Path) -> tuple[str, str] | None:
    """(título, descripción) de YouTube desde el copys.md de un clip ya
    cortado. Solo se usa para la vista previa del --dry-run."""
    copys_path = carpeta / "copys.md"
    if not copys_path.exists():
        return None
    texto = copys_path.read_text(encoding="utf-8")
    titulo = re.search(r"\*\*Título:\*\*\s*(.+)", texto)
    descripcion = re.search(r"\*\*Descripción:\*\*\s*(.+)", texto)
    if not titulo or not descripcion:
        return None
    return titulo.group(1).strip(), descripcion.group(1).strip()


def _mostrar_dry_run(fecha_dir: Path, a_procesar: list, capitulo: int | None) -> None:
    """--dry-run: no corta, no llama a la IA, no sube a YouTube ni escribe
    clips. Muestra el capítulo y cómo quedaría la descripción de YouTube,
    usando los copys de los clips ya cortados de esa fecha (si hay)."""
    print(f"\n[dry-run] capitulo={capitulo}")
    if a_procesar:
        print(f"[dry-run] Se cortarían y subirían {len(a_procesar)} candidatos nuevos:")
        for nombre, inicio, fin, _, _ in a_procesar:
            print(f"  - {nombre} ({cortar_clip.format_hhmmss(inicio)} -> {cortar_clip.format_hhmmss(fin)})")
    else:
        print("[dry-run] No quedan candidatos nuevos (todos se solapan con clips ya cortados).")

    ejemplos = [
        (p.name, c) for p in sorted(fecha_dir.glob("candidato-*")) if (c := _copys_de_carpeta(p))
    ] if fecha_dir.exists() else []
    if not ejemplos:
        ejemplos = [("(ejemplo)", ("<título de YouTube de la IA>", "<descripción de YouTube de la IA>"))]
    print("\n[dry-run] Descripción final de YouTube (con los copys ya generados en esta fecha):")
    for nombre, (titulo, descripcion) in ejemplos:
        final = publicar.descripcion_con_capitulo(f"{titulo}\n\n{descripcion}", capitulo)
        print(f"\n  {nombre}:")
        print("\n".join(f"    | {linea}" for linea in final.splitlines()))


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Procesa una grabación de punta a punta: detecta candidatos, corta, "
            "genera vertical/copys/portadas, valida y sube a YouTube + Supabase. "
            "Sin intervención manual en el medio."
        )
    )
    parser.add_argument("video", help="Nombre en 'grabaciones' o ruta absoluta del video")
    grupo_capitulo = parser.add_mutually_exclusive_group()
    grupo_capitulo.add_argument(
        "--extraordinario", action="store_true",
        help="Programa fuera de lunes que sí lleva número: crea MAX(capítulo)+1 como 'extraordinario'.",
    )
    grupo_capitulo.add_argument(
        "--capitulo", type=int, default=None,
        help="Fuerza un número de capítulo que ya existe en rayando_cda.capitulos.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help=(
            "No corta, no llama a la IA, no sube a YouTube ni escribe en Supabase: "
            "muestra el capítulo y la descripción final que quedaría."
        ),
    )
    args = parser.parse_args()

    video_path = cortar_clip.resolve_video(args.video)
    program_date = cortar_clip.program_date_from_name(video_path)
    fecha_dir = config.CLIPS_DIR / program_date
    rangos_existentes = _rangos_ya_cortados(fecha_dir)

    try:
        capitulo = capitulos.asignar_capitulo(
            video_path,
            extraordinario=args.extraordinario,
            capitulo_forzado=args.capitulo,
            dry_run=args.dry_run,
        )
    except capitulos.CapituloError as e:
        sys.exit(f"Error asignando capítulo: {e}")
    except Exception as e:  # noqa: BLE001 - el capítulo no debe frenar los shorts
        # Error de red/Supabase (ya con reintentos): los shorts salen igual,
        # sin capítulo. Se corrige después con corregir_capitulo.py.
        print(
            f"ADVERTENCIA: no se pudo asignar el capítulo ({type(e).__name__}: {e}). "
            "Los clips salen sin capítulo; corregir después con corregir_capitulo.py <fecha> <N>."
        )
        capitulo = None

    candidatos_fijos_path = _ruta_candidatos_fijos(fecha_dir, program_date)
    if args.dry_run and not candidatos_fijos_path.exists():
        print("[dry-run] No hay lista de candidatos confirmada: se detectarían en vivo (no se llama a la IA en dry-run).")
        _mostrar_dry_run(fecha_dir, [], capitulo)
        return
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

    if args.dry_run:
        _mostrar_dry_run(fecha_dir, a_procesar, capitulo)
        return

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
            resultado = cortar_clip.cortar_y_publicar(
                video_path, inicio, fin, nombre, razon=razon, capitulo=capitulo
            )
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
