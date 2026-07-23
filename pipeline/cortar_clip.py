import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import config
import copys_ia
import corregir_nombres
import portadas
import publicar

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


TIME_RE = re.compile(r"^(\d{1,2}):(\d{2}):(\d{2})(?:\.(\d{1,3}))?$")


def parse_time(value: str) -> float:
    m = TIME_RE.match(value.strip())
    if not m:
        raise ValueError(f"Formato de tiempo inválido: '{value}' (usa hh:mm:ss)")
    hh, mm, ss, frac = m.groups()
    total = int(hh) * 3600 + int(mm) * 60 + int(ss)
    if frac:
        total += int(frac) / (10 ** len(frac))
    return total


def format_hhmmss(seconds: float) -> str:
    ms = round(seconds * 1000)
    hh, ms = divmod(ms, 3_600_000)
    mm, ms = divmod(ms, 60_000)
    ss, ms = divmod(ms, 1000)
    if ms:
        return f"{hh:02d}:{mm:02d}:{ss:02d}.{ms:03d}"
    return f"{hh:02d}:{mm:02d}:{ss:02d}"


def format_srt_timestamp(seconds: float) -> str:
    if seconds < 0:
        seconds = 0
    ms = int(round(seconds * 1000))
    hh, ms = divmod(ms, 3_600_000)
    mm, ms = divmod(ms, 60_000)
    ss, ms = divmod(ms, 1000)
    return f"{hh:02d}:{mm:02d}:{ss:02d},{ms:03d}"


def resolve_video(video_arg: str) -> Path:
    p = Path(video_arg)
    if p.is_absolute():
        if not p.exists():
            raise FileNotFoundError(f"No existe el archivo: {p}")
        return p
    candidate = config.RECORDINGS_DIR / video_arg
    if candidate.exists():
        return candidate
    if p.exists():
        return p
    raise FileNotFoundError(
        f"No se encontró '{video_arg}' ni en {config.RECORDINGS_DIR} ni como ruta relativa"
    )


def program_date_from_name(video_path: Path) -> str:
    stem = video_path.stem
    first_token = stem.split(" ")[0]
    if re.match(r"^\d{4}-\d{2}-\d{2}$", first_token):
        return first_token
    return datetime.fromtimestamp(video_path.stat().st_mtime).strftime("%Y-%m-%d")


def run_ffmpeg(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    result = subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg falló (código {result.returncode}):\n"
            f"cmd: {' '.join(cmd)}\n{result.stderr[-3000:]}"
        )
    return result


def ffprobe_duration(path: Path) -> float:
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe falló para {path}: {result.stderr}")
    return float(result.stdout.strip())


def ffprobe_dimensions(path: Path) -> tuple[int, int]:
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=s=x:p=0", str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe falló para {path}: {result.stderr}")
    w_str, h_str = result.stdout.strip().split("x")
    return int(w_str), int(h_str)


def _foreground_height(src_w: int, src_h: int, fg_w: int) -> int:
    """Replica el cálculo de altura que hace ffmpeg en `scale={fg_w}:-2`
    (mantiene el aspect ratio de la fuente, redondea al par más cercano hacia
    abajo). Se usa para saber cuánto blur queda arriba/abajo del video real
    en el vertical, sin tener que correr ffmpeg dos veces."""
    scaled_h = int(fg_w * src_h / src_w)
    if scaled_h % 2:
        scaled_h -= 1
    return scaled_h


def cut_recode(src: Path, start: float, end: float, dst: Path, fade_seconds: float = 0.0) -> None:
    duration = end - start
    cmd = [
        "ffmpeg", "-y",
        "-ss", format_hhmmss(start), "-to", format_hhmmss(end),
        "-i", str(src),
    ]
    if fade_seconds > 0:
        fade_out_start = max(0.0, duration - fade_seconds)
        cmd += [
            "-vf",
            f"fade=t=in:st=0:d={fade_seconds},fade=t=out:st={fade_out_start:.3f}:d={fade_seconds}",
            "-af",
            f"afade=t=in:st=0:d={fade_seconds},afade=t=out:st={fade_out_start:.3f}:d={fade_seconds}",
        ]
    cmd += [
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        str(dst),
    ]
    run_ffmpeg(cmd)


def cut_horizontal(src: Path, start: float, end: float, dst: Path) -> tuple[str, float, float]:
    """Corta con un margen de aire (config.CLIP_PAD_SECONDS) antes/después y
    un fade-in/fade-out corto (config.CLIP_FADE_SECONDS) en vez de un corte
    seco. Requiere recodificar (los fades son un filtro, no se pueden aplicar
    con stream copy). Devuelve (método, inicio_real, fin_real) — inicio_real/
    fin_real son los límites efectivamente usados (el margen se recorta si
    cae fuera de la duración de la grabación), para que quien llama pueda
    reajustar el offset de los subtítulos."""
    src_duration = ffprobe_duration(src)
    padded_start = max(0.0, start - config.CLIP_PAD_SECONDS)
    padded_end = min(src_duration, end + config.CLIP_PAD_SECONDS)
    cut_recode(src, padded_start, padded_end, dst, fade_seconds=config.CLIP_FADE_SECONDS)
    return "recode", padded_start, padded_end


def load_master_segments(video_path: Path) -> list[dict] | None:
    json_path = config.TRANSCRIPTS_DIR / video_path.stem / f"{video_path.stem}.json"
    if not json_path.exists():
        return None
    data = json.loads(json_path.read_text(encoding="utf-8"))
    return data["segments"]


def clip_segments(segments: list[dict], start: float, end: float) -> list[tuple[float, float, str]]:
    diccionario = corregir_nombres.cargar_diccionario()
    clipped = []
    for seg in segments:
        s, e, text = seg["start"], seg["end"], seg["text"].strip()
        if e <= start or s >= end or not text:
            continue
        cs = max(s, start) - start
        ce = min(e, end) - start
        if ce <= cs:
            continue
        text = corregir_nombres.corregir_texto(text, diccionario)
        clipped.append((cs, ce, text))
    return clipped


def build_clip_srt(clipped: list[tuple[float, float, str]], out_srt: Path) -> None:
    lines = []
    for idx, (cs, ce, text) in enumerate(clipped, start=1):
        lines.append(
            f"{idx}\n{format_srt_timestamp(cs)} --> {format_srt_timestamp(ce)}\n{text}\n"
        )
    out_srt.write_text("\n".join(lines), encoding="utf-8")


def format_ass_timestamp(seconds: float) -> str:
    if seconds < 0:
        seconds = 0
    cs = int(round(seconds * 100))
    hh, cs = divmod(cs, 360_000)
    mm, cs = divmod(cs, 6_000)
    ss, cs = divmod(cs, 100)
    return f"{hh:01d}:{mm:02d}:{ss:02d}.{cs:02d}"


def build_clip_ass(clipped: list[tuple[float, float, str]], out_ass: Path) -> None:
    w, h = config.VERTICAL_WIDTH, config.VERTICAL_HEIGHT
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: None

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{config.SUBTITLE_FONT_NAME},{config.SUBTITLE_FONT_SIZE},&H00FFFFFF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,{config.SUBTITLE_OUTLINE},{config.SUBTITLE_SHADOW},2,{config.SUBTITLE_MARGIN_L},{config.SUBTITLE_MARGIN_R},{config.SUBTITLE_MARGIN_V},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    for cs, ce, text in clipped:
        ass_text = text.replace("\n", "\\N")
        lines.append(
            f"Dialogue: 0,{format_ass_timestamp(cs)},{format_ass_timestamp(ce)},"
            f"Default,,0,0,0,,{ass_text}\n"
        )
    out_ass.write_text("".join(lines), encoding="utf-8")


def _logo_overlay_xy() -> tuple[str, str]:
    margen = config.LOGO_MARGEN_PX
    posiciones = {
        "top-left": (f"{margen}", f"{margen}"),
        "top-right": (f"W-w-{margen}", f"{margen}"),
        "bottom-left": (f"{margen}", f"H-h-{margen}"),
        "bottom-right": (f"W-w-{margen}", f"H-h-{margen}"),
    }
    if config.LOGO_POSICION not in posiciones:
        raise ValueError(f"LOGO_POSICION inválida: {config.LOGO_POSICION}")
    return posiciones[config.LOGO_POSICION]


def build_vertical(out_dir: Path, has_subtitles: bool, titulo_portada: str | None = None) -> None:
    w, h = config.VERTICAL_WIDTH, config.VERTICAL_HEIGHT
    fg_w = int(w * config.VERTICAL_FOREGROUND_SCALE)
    logo_w = max(2, int(w * config.LOGO_ANCHO_RATIO) // 2 * 2)
    x_expr, y_expr = _logo_overlay_xy()

    src_w, src_h = ffprobe_dimensions(out_dir / "horizontal_original.mp4")
    fg_h = _foreground_height(src_w, src_h, fg_w)
    band_h = (h - fg_h) // 2

    top_offset = 0
    if config.LOGO_POSICION.startswith("top"):
        _, logo_h = portadas.logo_footprint_px(w)
        top_offset = config.LOGO_MARGEN_PX + logo_h + config.VIDEO_TITULO_LOGO_GAP_PX

    titulo_png = None
    if titulo_portada and band_h - top_offset >= config.VIDEO_TITULO_MIN_USABLE_PX:
        titulo_png = out_dir / "titulo_video.png"
        portadas.render_video_titulo_png(titulo_png, w, band_h, titulo_portada, top_offset)

    filter_complex = (
        f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
        f"crop={w}:{h},gblur=sigma=20[bg];"
        f"[0:v]scale={fg_w}:-2:force_original_aspect_ratio=decrease,crop={w}:ih[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2[base];"
    )
    cmd = ["ffmpeg", "-y", "-i", "horizontal_original.mp4", "-i", str(config.LOGO_PATH)]
    if titulo_png:
        filter_complex += "[base][2:v]overlay=0:0[basetitle];"
        cmd += ["-i", str(titulo_png)]
        base_label = "basetitle"
    else:
        base_label = "base"

    logo_w_expr = f"scale={logo_w}:-2,format=rgba,colorchannelmixer=aa={config.LOGO_OPACIDAD}[logo]"
    filter_complex += (
        f"[1:v]{logo_w_expr};"
        f"[{base_label}][logo]overlay={x_expr}:{y_expr}[withlogo]"
    )
    if has_subtitles:
        filter_complex += ";[withlogo]subtitles=subtitulos.ass[outv]"
    else:
        filter_complex += ";[withlogo]null[outv]"

    cmd += [
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "0:a",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        "vertical.mp4",
    ]
    run_ffmpeg(cmd, cwd=out_dir)


def _cargar_overrides(nombre_clip: str) -> dict:
    path = Path(__file__).parent / "clip_overrides.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get(nombre_clip, {})


def _prettify_nombre(nombre_clip: str) -> str:
    return " ".join(w.capitalize() for w in nombre_clip.split("-"))


def _titulo_portada_auto(titulo_seo: str) -> str:
    """Fallback simple para clips sin 'titulo_portada' curado a mano en
    clip_overrides.json: recorta el título SEO a las primeras 6 palabras
    (hasta el primer separador fuerte) y lo deja en MAYÚSCULAS."""
    limpio = re.split(r"[:\-–—]", titulo_seo)[0].strip()
    palabras = limpio.split()[:6]
    return " ".join(palabras).upper()


def join_transcripcion(clipped: list[tuple[float, float, str]]) -> str:
    return " ".join(text for _, _, text in clipped).strip()


def build_copys(out_dir: Path, nombre_clip: str, clipped: list[tuple[float, float, str]]) -> publicar.Copys:
    """Genera copys.md (título SEO + título de portada + copys IG/YouTube/TikTok).
    Devuelve un publicar.Copys con los campos por separado (se usan también
    para el registro en Supabase)."""
    transcripcion = join_transcripcion(clipped)
    overrides = _cargar_overrides(nombre_clip)

    titulo_seo = overrides.get("titulo_seo") or _prettify_nombre(nombre_clip)

    campos_ia = ("copy_instagram", "youtube_titulo", "youtube_descripcion", "copy_tiktok", "titulo_portada")
    faltan_campos = [c for c in campos_ia if not overrides.get(c)]

    generado_ia = None
    if faltan_campos and transcripcion:
        try:
            generado_ia = copys_ia.generar_copys(nombre_clip, transcripcion)
            print(f"  Copys generados con IA (Anthropic) para: {', '.join(faltan_campos)}")
        except copys_ia.CopyIAError as e:
            print(f"  ADVERTENCIA: no se pudo generar copys con IA ({e}). Usando fallback de texto plano.")

    # Fallback de texto plano: solo se usa si un campo no está en overrides
    # Y la IA no generó nada (sin API key, sin transcripción, o falló la llamada).
    contexto = overrides.get("contexto")
    if not contexto:
        oraciones = re.split(r"(?<=[.!?])\s+", transcripcion)
        contexto = " ".join(oraciones[:3]).strip() or transcripcion[:220] or titulo_seo

    hashtags = list(config.COPYS_HASHTAGS_BASE) + list(overrides.get("hashtags_extra", []))
    hashtags_str = " ".join(hashtags)

    if overrides.get("copy_instagram"):
        copy_instagram = overrides["copy_instagram"]
    elif generado_ia:
        copy_instagram = f"{generado_ia.copy_instagram_cuerpo}\n\n{hashtags_str}"
    else:
        copy_instagram = f"{contexto}\n\n{hashtags_str}"

    if overrides.get("youtube_titulo"):
        youtube_titulo = overrides["youtube_titulo"]
    elif generado_ia:
        youtube_titulo = generado_ia.youtube_titulo
    else:
        youtube_titulo = titulo_seo

    if overrides.get("youtube_descripcion"):
        youtube_descripcion = overrides["youtube_descripcion"]
    elif generado_ia:
        youtube_descripcion = generado_ia.youtube_descripcion
    else:
        youtube_descripcion = contexto

    if overrides.get("copy_tiktok"):
        copy_tiktok = overrides["copy_tiktok"]
    elif generado_ia:
        copy_tiktok = f"{generado_ia.copy_tiktok_cuerpo}\n\n{hashtags_str}"
    else:
        copy_tiktok = f"{contexto}\n\n{hashtags_str}"

    if overrides.get("titulo_portada"):
        titulo_portada = overrides["titulo_portada"]
    elif generado_ia:
        titulo_portada = generado_ia.titulo_portada
    else:
        titulo_portada = _titulo_portada_auto(titulo_seo)

    contenido = f"""# {titulo_seo}

**Portada:** {titulo_portada}

## Instagram (Reel)
{copy_instagram}

## YouTube Shorts
**Título:** {youtube_titulo}
**Descripción:** {youtube_descripcion}

## TikTok
{copy_tiktok}
"""
    (out_dir / "copys.md").write_text(contenido, encoding="utf-8")

    return publicar.Copys(
        titulo_seo=titulo_seo,
        titulo_portada=titulo_portada,
        copy_instagram=copy_instagram,
        youtube_titulo=youtube_titulo,
        youtube_descripcion=youtube_descripcion,
        copy_tiktok=copy_tiktok,
    )


def cortar_y_publicar(
    video_path: Path,
    start: float,
    end: float,
    nombre: str,
    razon: str | None = None,
) -> dict | None:
    """Corta el clip (horizontal + vertical con subtítulos/logo), genera
    copys/portadas, escribe metadata.json y publica (YouTube no listado +
    Supabase). Es el núcleo reusado tanto por main() (CLI, un clip a mano)
    como por procesar_programa.py (orquestación automática de N
    candidatos). Devuelve el resultado de publicar.publicar_clip() (dict
    con youtube_video_id/youtube_url/supabase_id), o None si el clip no
    pasó la validación técnica."""
    if end <= start:
        raise ValueError("el tiempo de fin debe ser mayor que el de inicio")

    clip_duration = end - start
    if clip_duration > config.REEL_MAX_SECONDS:
        print(
            f"ADVERTENCIA: el clip dura {clip_duration:.1f}s, supera el límite de "
            f"{config.REEL_MAX_SECONDS}s para Reels/Shorts/TikTok. Se generará igual."
        )

    program_date = program_date_from_name(video_path)
    out_dir = config.CLIPS_DIR / program_date / nombre
    out_dir.mkdir(parents=True, exist_ok=True)

    horizontal_path = out_dir / "horizontal_original.mp4"
    print(f"Cortando versión horizontal ({format_hhmmss(start)} -> {format_hhmmss(end)})...")
    method, actual_start, actual_end = cut_horizontal(video_path, start, end, horizontal_path)
    pad_offset = start - actual_start
    print(
        f"  Horizontal listo ({method}, margen -{pad_offset:.2f}s/+{actual_end - end:.2f}s, "
        f"fade {config.CLIP_FADE_SECONDS}s): {horizontal_path}"
    )

    segments = load_master_segments(video_path)
    has_subtitles = False
    clipped: list[tuple[float, float, str]] = []
    if segments is None:
        print(
            "  No se encontró transcripción para esta grabación en "
            f"{config.TRANSCRIPTS_DIR / video_path.stem}. El vertical se generará sin subtítulos."
        )
    else:
        clipped = clip_segments(segments, start, end)
        if pad_offset:
            # Los subtítulos se calcularon relativos al inicio "de contenido"
            # (start); el video ahora arranca antes por el margen de aire, así
            # que hay que correr los timestamps para que sigan calzando.
            clipped = [(cs + pad_offset, ce + pad_offset, text) for cs, ce, text in clipped]
        has_subtitles = bool(clipped)
        if has_subtitles:
            build_clip_srt(clipped, out_dir / "subtitulos.srt")
            build_clip_ass(clipped, out_dir / "subtitulos.ass")
        else:
            print("  La transcripción no tiene texto en este rango. Vertical sin subtítulos.")

    print("Generando copys (con IA si hay API key)...")
    copys = build_copys(out_dir, nombre, clipped)
    overrides = _cargar_overrides(nombre)
    print(f"  Copys.md listo, titulo_portada: {copys.titulo_portada!r}")

    print("Generando versión vertical 9:16 con fondo desenfocado, titulo_portada, logo" + (" y subtítulos..." if has_subtitles else "..."))
    build_vertical(out_dir, has_subtitles, copys.titulo_portada)
    vertical_path = out_dir / "vertical.mp4"
    print(f"  Vertical listo: {vertical_path}")

    print("Generando portadas...")
    portadas.build_portadas(out_dir, horizontal_path, copys.titulo_portada, overrides)
    print(f"  Portadas listas en: {out_dir}")

    transcripcion_texto = join_transcripcion(clipped)
    metadata = {
        "nombre": nombre,
        "programa_fecha": program_date,
        "video_fuente": str(video_path),
        "timestamp_inicio": format_hhmmss(start),
        "timestamp_fin": format_hhmmss(end),
        "duracion_segundos": round(clip_duration, 3),
        "razon": razon,
        "transcripcion": transcripcion_texto,
        "generado_en": datetime.now().isoformat(timespec="seconds"),
    }
    (out_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\nClip '{nombre}' generado en: {out_dir}")

    print("\nPublicando a YouTube (no listado) y registrando en Supabase...")
    resultado = publicar.publicar_clip(
        out_dir=out_dir,
        nombre_clip=nombre,
        program_date=program_date,
        video_path=vertical_path,
        copys=copys,
        razon=razon,
        transcripcion=transcripcion_texto,
        timestamp_inicio=start,
        timestamp_fin=end,
    )
    return resultado


def main():
    parser = argparse.ArgumentParser(
        description="Corta un clip horizontal y vertical (con subtítulos) de una grabación."
    )
    parser.add_argument("video", help="Ruta o nombre de archivo en la carpeta de grabaciones")
    parser.add_argument("inicio", help="Tiempo de inicio, formato hh:mm:ss")
    parser.add_argument("fin", help="Tiempo de fin, formato hh:mm:ss")
    parser.add_argument("nombre", help="Nombre del clip (se usa como nombre de carpeta)")
    parser.add_argument(
        "--razon",
        default=None,
        help=(
            "Por qué se eligió este momento (opcional). Queda en metadata.json "
            "y en el campo 'razon' de Supabase; si no se pasa, queda NULL."
        ),
    )
    args = parser.parse_args()

    video_path = resolve_video(args.video)
    start = parse_time(args.inicio)
    end = parse_time(args.fin)
    if end <= start:
        sys.exit("Error: el tiempo de fin debe ser mayor que el de inicio.")

    resultado = cortar_y_publicar(video_path, start, end, args.nombre, razon=args.razon)

    if resultado:
        print(
            "\n1 clip subido y listo para revisión de René:\n"
            f"  - {args.nombre}: YouTube {resultado['youtube_video_id']} "
            f"({resultado['youtube_url']}) — Supabase id {resultado['supabase_id']}"
        )
    else:
        print(
            f"\n0 clips subidos. '{args.nombre}' no pasó la validación técnica; "
            f"revisa {config.PUBLICAR_ERROR_LOG}"
        )


if __name__ == "__main__":
    main()
