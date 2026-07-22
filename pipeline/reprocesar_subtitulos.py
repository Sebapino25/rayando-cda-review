"""Cierra el loop de corrección de subtítulos: busca en rayando_cda.clips las
filas donde `transcripcion` (editable por René) quedó distinta de
`transcripcion_original` (copia automática al insertar, vía trigger), vuelve
a quemar los subtítulos corregidos sobre el clip ya cortado, sube el
resultado como un nuevo video no listado de YouTube, actualiza
youtube_video_id y sincroniza transcripcion_original = transcripcion.

No hay ninguna columna en Supabase que guarde la carpeta local del clip, así
que la carpeta se encuentra correlacionando contenido: el texto de
`subtitulos.srt` (unido) tiene que calzar exacto con `transcripcion_original`
(así se escribió originalmente — ver cortar_clip.join_transcripcion /
publicar.publicar_clip). El match tiene que ser exacto y único: si no hay
ninguna coincidencia o hay más de una, el script se detiene y lo reporta en
vez de adivinar (ver encontrar_carpetas_candidatas()).

El quemado de subtítulos en sí NO se reimplementa acá: se reusan
cortar_clip.build_clip_srt / build_clip_ass / build_vertical, las mismas
funciones que usa cortar_clip.py al cortar un clip nuevo.

Corre en dry-run por defecto (solo muestra qué haría). Usa --apply para
ejecutar de verdad, y --clip-id para probar contra un solo clip.
"""

import argparse
import difflib
import re
import shutil
import sys
from pathlib import Path

import config
import cortar_clip
import publicar

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


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


def redistribuir_texto(
    segmentos_originales: list[tuple[float, float, str]], texto_nuevo: str
) -> list[tuple[float, float, str]]:
    """Reparte texto_nuevo (la transcripción corregida a mano por René, como
    bloque único) sobre los mismos timestamps de segmentos_originales,
    proporcional a la cantidad de palabras que tenía cada segmento
    originalmente. La corrección se hace sobre el texto completo, no
    segmento a segmento, así que no hay forma de saber con certeza qué
    palabra corregida corresponde a qué segmento exacto — esto es la mejor
    aproximación posible sin volver a transcribir/alinear audio, y mantiene
    los mismos cortes de tiempo que ya se ven bien en pantalla."""
    palabras_nuevas = _normalizar(texto_nuevo).split()
    pesos = [len(texto.split()) for _, _, texto in segmentos_originales]
    total_peso = sum(pesos)
    if not palabras_nuevas or total_peso == 0:
        return []

    resultado = []
    restantes = palabras_nuevas
    n = len(segmentos_originales)
    for i, ((cs, ce, _), peso) in enumerate(zip(segmentos_originales, pesos)):
        if i == n - 1:
            cantidad = len(restantes)
        else:
            cantidad = min(round(len(palabras_nuevas) * peso / total_peso), len(restantes))
        chunk, restantes = restantes[:cantidad], restantes[cantidad:]
        if chunk:
            resultado.append((cs, ce, " ".join(chunk)))
    return resultado


def encontrar_carpetas_candidatas(row: dict) -> list[Path]:
    """Busca TODAS las carpetas locales (clips\\<semana>\\<nombre>\\) cuyo
    subtitulos.srt (texto unido) calza EXACTO con transcripcion_original de
    esta fila. En el caso sano esto devuelve una sola carpeta; quien llama
    es responsable de detenerse (no adivinar) si la lista queda vacía o
    tiene más de un elemento — ver procesar_fila()."""
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
    informativo — nunca se usa para elegir la carpeta a procesar, para no
    terminar quemando subtítulos sobre el video de otro clip por una
    diferencia de un espacio o un símbolo que en realidad merece revisión
    humana, no una adivinanza automática."""
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


def _siguiente_version_dir(carpeta: Path) -> Path:
    n = 1
    while (carpeta / f"v{n}").exists():
        n += 1
    return carpeta / f"v{n}"


def respaldar_version_anterior(carpeta: Path) -> Path:
    """Mueve vertical.mp4 + subtitulos.srt/.ass a una subcarpeta vN\\ antes
    de sobreescribirlos — misma convención manual descrita en el README
    ("Antes de regenerar un clip ya publicado conviene mover manualmente los
    archivos viejos a una subcarpeta v1\\")."""
    destino = _siguiente_version_dir(carpeta)
    destino.mkdir(parents=True, exist_ok=False)
    for nombre in ("vertical.mp4", "subtitulos.srt", "subtitulos.ass"):
        origen = carpeta / nombre
        if origen.exists():
            shutil.move(str(origen), str(destino / nombre))
    return destino


def buscar_pendientes(supabase, clip_id: str | None) -> list[dict]:
    columnas = (
        "id,youtube_video_id,titulo,youtube_titulo,youtube_descripcion,"
        "semana,estado,transcripcion,transcripcion_original"
    )
    query = supabase.table(config.SUPABASE_TABLE).select(columnas)
    if clip_id:
        query = query.eq("id", clip_id)
    filas = query.execute().data

    pendientes = [
        f for f in filas
        if _normalizar(f.get("transcripcion")) != _normalizar(f.get("transcripcion_original"))
    ]
    if not clip_id:
        # Los fixtures de QA (estado='prueba') no son contenido real; un
        # barrido general no debe tocarlos, solo --clip-id explícito.
        pendientes = [f for f in pendientes if f.get("estado") != "prueba"]
    return pendientes


def procesar_fila(row: dict, apply: bool) -> None:
    clip_id = row["id"]
    print(f"\n=== Clip {clip_id} (semana {row.get('semana')}, estado {row.get('estado')}) ===")
    print(f"  YouTube actual: {row.get('youtube_video_id')}")

    carpetas = encontrar_carpetas_candidatas(row)
    if len(carpetas) == 0:
        print(
            "  OMITIDO: no se encontró ninguna carpeta local cuyo subtitulos.srt "
            "calce EXACTO con transcripcion_original."
        )
        pista = candidata_mas_parecida(row)
        if pista is not None:
            carpeta_parecida, ratio = pista
            print(
                f"    Candidata más parecida (no se usó, solo diagnóstico): "
                f"{carpeta_parecida} (similitud {ratio:.1%})."
            )
            print(
                "    Si el ratio es muy alto, probablemente sea un espacio/símbolo "
                "distinto entre subtitulos.srt y transcripcion_original — revisá a mano, "
                "el script no adivina."
            )
        return
    if len(carpetas) > 1:
        print(
            f"  OMITIDO: se encontraron {len(carpetas)} carpetas cuyo subtitulos.srt "
            "calza EXACTO con transcripcion_original (ambigüedad, no se puede elegir "
            "automáticamente):"
        )
        for c in carpetas:
            print(f"    - {c}")
        print("    Resolvé la ambigüedad a mano (o corregí el contenido duplicado) antes de reprocesar.")
        return

    carpeta = carpetas[0]
    print(f"  Carpeta local: {carpeta}")

    horizontal = carpeta / "horizontal_original.mp4"
    srt_actual = carpeta / "subtitulos.srt"
    if not horizontal.exists():
        print(f"  OMITIDO: no existe {horizontal}")
        return

    segmentos_originales = parse_srt(srt_actual)
    nuevos_segmentos = redistribuir_texto(segmentos_originales, row.get("transcripcion") or "")
    if not nuevos_segmentos:
        print("  OMITIDO: no se pudo redistribuir el texto corregido sobre los segmentos existentes.")
        return

    print(
        f"  Transcripción corregida ({len(nuevos_segmentos)} segmentos redistribuidos "
        f"desde {len(segmentos_originales)} originales):"
    )
    print(f"    antes: {(row.get('transcripcion_original') or '')[:120]}...")
    print(f"    ahora: {(row.get('transcripcion') or '')[:120]}...")

    if not apply:
        print(
            "  [dry-run] Se respaldaría la versión anterior en vN\\, se quemarían los "
            "subtítulos corregidos sobre horizontal_original.mp4, se subiría un video "
            "nuevo a YouTube (no listado) y se actualizaría youtube_video_id + "
            "transcripcion_original en Supabase."
        )
        return

    print("  Respaldando versión anterior (vertical.mp4 + subtitulos.*) en vN\\...")
    destino_backup = respaldar_version_anterior(carpeta)
    print(f"    Respaldado en: {destino_backup}")

    print("  Regenerando subtitulos.srt/.ass con el texto corregido...")
    cortar_clip.build_clip_srt(nuevos_segmentos, carpeta / "subtitulos.srt")
    cortar_clip.build_clip_ass(nuevos_segmentos, carpeta / "subtitulos.ass")

    print("  Quemando subtítulos sobre horizontal_original.mp4 (cortar_clip.build_vertical)...")
    cortar_clip.build_vertical(carpeta, has_subtitles=True)
    vertical_path = carpeta / "vertical.mp4"

    try:
        publicar.validar_clip(vertical_path)
    except publicar.ClipInvalido as e:
        print(f"  OMITIDO: el vertical.mp4 recién quemado no pasó la validación técnica: {e}")
        print(f"  (subtitulos.srt/.ass ya quedaron actualizados; versión anterior respaldada en {destino_backup})")
        return

    titulo = row.get("titulo") or "Rayando el CDA"
    descripcion = f"{row.get('youtube_titulo') or ''}\n\n{row.get('youtube_descripcion') or ''}".strip()
    print(f'  Subiendo a YouTube como no listado: "{titulo}"...')
    nuevo_video_id = publicar.subir_youtube(vertical_path, titulo, descripcion=descripcion)
    nueva_url = f"https://youtu.be/{nuevo_video_id}"
    print(f"  Subido: {nueva_url}")

    print("  Actualizando Supabase (youtube_video_id + transcripcion_original)...")
    publicar.actualizar_clip_supabase(
        clip_id,
        {
            "youtube_video_id": nuevo_video_id,
            "transcripcion_original": row.get("transcripcion"),
        },
    )

    video_id_anterior = row.get("youtube_video_id")
    resumen_extra = (
        "\n--- Reproceso de subtítulos ---\n"
        f"YouTube video ID anterior: {video_id_anterior}\n"
        f"YouTube video ID nuevo: {nuevo_video_id}\n"
        f"YouTube URL nueva: {nueva_url}\n"
    )
    with (carpeta / "resumen.txt").open("a", encoding="utf-8") as f:
        f.write(resumen_extra)

    print(f"  Listo. youtube_video_id actualizado: {video_id_anterior} -> {nuevo_video_id}")
    print(
        f"  NOTA: el video anterior ({video_id_anterior}) sigue en YouTube como no "
        "listado; si ya no sirve, bórralo a mano desde YouTube Studio."
    )


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Busca clips donde transcripcion != transcripcion_original en "
            "rayando_cda.clips, vuelve a quemar los subtítulos corregidos "
            "sobre el video ya cortado, sube el resultado como nuevo video "
            "no listado de YouTube y sincroniza transcripcion_original."
        )
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Ejecuta de verdad. Sin este flag corre en dry-run (solo muestra qué haría).",
    )
    parser.add_argument(
        "--clip-id", default=None,
        help="Procesa solo este id de rayando_cda.clips (para probar contra un solo clip).",
    )
    args = parser.parse_args()

    supabase = publicar.get_supabase_client()
    filas = buscar_pendientes(supabase, args.clip_id)

    if not filas:
        if args.clip_id:
            print(f"El clip {args.clip_id} no tiene cambios pendientes (transcripcion == transcripcion_original).")
        else:
            print("No hay clips con cambios pendientes (transcripcion == transcripcion_original en todas las filas).")
        return

    print(f"{'[APPLY]' if args.apply else '[DRY-RUN]'} {len(filas)} clip(s) con cambios pendientes.")
    for row in filas:
        procesar_fila(row, apply=args.apply)


if __name__ == "__main__":
    main()
