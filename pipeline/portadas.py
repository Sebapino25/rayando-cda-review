"""Sistema de portadas v2.

Reglas de diseño (ver README.md, sección "Portadas automáticas"):
- Título corto y gritado, con la palabra clave destacada en amarillo.
- Tipografía Anton (Google Fonts, condensada e impactante).
- Franja diagonal azul marino semitransparente detrás del título, para legibilidad.
- Selección de fotograma con criterio: candidatos distribuidos en el clip,
  puntuados por nitidez (varianza de Laplaciano) y detección de rostro/ojos
  abiertos (Haar cascades de OpenCV), con contact sheet para elegir a mano.
- Composición "VS" (dos fotogramas separados por una línea diagonal) cuando el
  titular es un enfrentamiento.
- Soporte para imagen propia de fondo (recursos-portadas\\) en vez del fotograma.
- Logo arriba (misma posición que en los videos) + franja inferior de marca.
"""

import re
import shutil
import textwrap
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

import config
from ffmpeg_utils import ffprobe_duration, extract_frame

_FACE_CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
_EYE_CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_eye.xml")

_PUNCT_RE = re.compile(r"[¿?¡!.,:;\"'()]")
_PALABRA_RE = re.compile(r"[A-Za-zÁÉÍÓÚÑÜáéíóúñü]+")


# ---------------------------------------------------------------------------
# Selección de fotograma con criterio
# ---------------------------------------------------------------------------

def _score_frame(img: Image.Image) -> dict:
    """Heurísticas simples: nitidez (varianza de Laplaciano) + bonus/penalización
    por rostro detectado con ojos abiertos (Haar cascades de OpenCV)."""
    arr = np.array(img.convert("RGB"))
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())

    # minNeighbors alto y minSize proporcional al ancho del frame para evitar
    # falsos positivos en texturas/fondos (más estricto que el default de OpenCV).
    min_size = max(60, int(gray.shape[1] * 0.045))
    faces = _FACE_CASCADE.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=8, minSize=(min_size, min_size))
    has_face = len(faces) > 0
    eyes_open = 0
    face_bbox = None
    if has_face:
        face_bbox = tuple(int(v) for v in max(faces, key=lambda f: f[2] * f[3]))
        x, y, w, h = face_bbox
        roi = gray[y:y + h // 2, x:x + w]  # mitad superior de la cara, donde están los ojos
        eyes = _EYE_CASCADE.detectMultiScale(roi, scaleFactor=1.1, minNeighbors=6, minSize=(15, 15))
        eyes_open = len(eyes)

    score = min(sharpness / 300.0, 5.0)  # nitidez normalizada, con techo
    if has_face:
        score += 2.0
        if eyes_open >= 2:
            score += 3.0  # rostro con ambos ojos visibles: candidato ideal
        elif eyes_open == 1:
            score += 1.0
        else:
            score -= 2.0  # rostro sin ojos visibles: probable pestañeo/perfil cerrado

    return {
        "sharpness": round(sharpness, 1),
        "has_face": has_face,
        "eyes_open": eyes_open,
        "score": round(score, 2),
        "face_bbox": face_bbox,
        "frame_size": img.size,
    }


def extract_candidates(video_path: Path, duration: float, tmp_dir: Path) -> list[dict]:
    """Extrae PORTADA_CANDIDATOS_N fotogramas distribuidos en el clip y los
    puntúa. Devuelve la lista ordenada de mejor a peor (score descendente);
    cada dict conserva su "indice" original (orden temporal, 1..N)."""
    tmp_dir.mkdir(parents=True, exist_ok=True)
    n = config.PORTADA_CANDIDATOS_N
    start_frac = config.PORTADA_CANDIDATOS_MARGEN_INICIO
    end_frac = 1 - config.PORTADA_CANDIDATOS_MARGEN_FIN
    fracs = [start_frac + (end_frac - start_frac) * i / (n - 1) for i in range(n)] if n > 1 else [0.5]

    candidatos = []
    for i, frac in enumerate(fracs, start=1):
        ts = duration * frac
        png_path = tmp_dir / f"candidato_{i:02d}.png"
        extract_frame(video_path, ts, png_path)
        img = Image.open(png_path).convert("RGB")
        info = _score_frame(img)
        info.update({"indice": i, "timestamp": ts, "path": png_path})
        candidatos.append(info)

    candidatos.sort(key=lambda c: c["score"], reverse=True)
    return candidatos


# ---------------------------------------------------------------------------
# Helpers de composición
# ---------------------------------------------------------------------------

def _crop_to_cover(img: Image.Image, w: int, h: int, focus_x_ratio: float | None = None) -> Image.Image:
    """Recorta cubriendo (w, h). Si se da focus_x_ratio (0-1, posición horizontal
    del sujeto de interés en la imagen original, ej. el centro de un rostro
    detectado), centra el recorte ahí en vez de en el centro geométrico — evita
    cortar al sujeto cuando no está centrado en el fotograma original."""
    fw, fh = img.size
    scale = max(w / fw, h / fh)
    img = img.resize((int(fw * scale) + 1, int(fh * scale) + 1), Image.LANCZOS)
    fw, fh = img.size
    if focus_x_ratio is not None:
        left = int(fw * focus_x_ratio - w / 2)
        left = max(0, min(left, fw - w))
    else:
        left = (fw - w) // 2
    top = (fh - h) // 2
    return img.crop((left, top, left + w, top + h)).convert("RGB")


def _detectar_palabra_clave(titulo: str, override: str | None) -> str | None:
    if override:
        return override
    palabras = _PALABRA_RE.findall(titulo)
    candidatas = [p for p in palabras if len(p) >= 4 and p.lower() not in config.PORTADA_STOPWORDS_CLAVE]
    if not candidatas:
        candidatas = palabras
    if not candidatas:
        return None
    return max(candidatas, key=len)


def _es_composicion_vs(titulo: str, override: bool | None) -> bool:
    if override is not None:
        return bool(override)
    return bool(re.search(r"\bvs\b", titulo, flags=re.IGNORECASE))


def _fit_title(
    draw: ImageDraw.ImageDraw, titulo: str, font_path: str, max_width: int,
    max_lines: int, max_size: int, min_size: int,
) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    size = max_size
    while size >= min_size:
        font = ImageFont.truetype(font_path, size)
        avg_char_w = font.getlength("OA") / 2 or 1
        wrap_width = max(3, int(max_width / avg_char_w * 1.12))
        lines = textwrap.wrap(titulo, width=wrap_width) or [titulo]
        widths = [draw.textlength(line, font=font) for line in lines]
        if (not widths or max(widths) <= max_width) and len(lines) <= max_lines:
            return font, lines
        size -= 6
    font = ImageFont.truetype(font_path, min_size)
    avg_char_w = font.getlength("OA") / 2 or 1
    lines = textwrap.wrap(titulo, width=max(3, int(max_width / avg_char_w))) or [titulo]
    return font, lines


def _draw_title_lines(
    draw: ImageDraw.ImageDraw, lines: list[str], font: ImageFont.FreeTypeFont,
    palabra_clave: str | None, start_y: float, line_height: float, w: int, stroke_width: int,
) -> None:
    clave_norm = _PUNCT_RE.sub("", palabra_clave).strip().lower() if palabra_clave else None
    y = start_y
    for line in lines:
        words = line.split(" ")
        word_widths = [draw.textlength(word, font=font) for word in words]
        space_w = draw.textlength(" ", font=font)
        total_w = sum(word_widths) + space_w * max(0, len(words) - 1)
        x = (w - total_w) / 2
        for word, ww in zip(words, word_widths):
            norm = _PUNCT_RE.sub("", word).strip().lower()
            fill = config.PORTADA_COLOR_DESTACADO if clave_norm and norm == clave_norm else config.PORTADA_TEXTO_COLOR
            draw.text(
                (x, y), word, font=font, fill=fill,
                stroke_width=stroke_width, stroke_fill=config.PORTADA_TEXTO_SOMBRA_COLOR,
            )
            x += ww + space_w
        y += line_height


def _draw_diagonal_band(canvas: Image.Image, y_top: float, y_bottom: float, w: int) -> Image.Image:
    slant = int(w * config.PORTADA_FRANJA_SLANT_RATIO)
    overshoot = slant + 20
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    points = [
        (-overshoot, y_top + slant),
        (w + overshoot, y_top - slant),
        (w + overshoot, y_bottom - slant),
        (-overshoot, y_bottom + slant),
    ]
    odraw.polygon(points, fill=(*config.PORTADA_COLOR_FRANJA, config.PORTADA_FRANJA_OPACIDAD))
    return Image.alpha_composite(canvas, overlay)


def _logo_position(w: int, logo_w: int, logo_h: int, margen: int) -> tuple[int, int]:
    # Siempre arriba (regla de marca), en el mismo lado que en los videos.
    x = margen if "left" in config.LOGO_POSICION else w - logo_w - margen
    return x, margen


def _compose_vs_background(img_left: Image.Image, img_right: Image.Image, w: int, h: int) -> Image.Image:
    left = _crop_to_cover(img_left, w, h)
    right = _crop_to_cover(img_right, w, h)
    slant = int(w * config.PORTADA_VS_SLANT_RATIO)

    mask = Image.new("L", (w, h), 0)
    mdraw = ImageDraw.Draw(mask)
    mdraw.polygon([(0, 0), (w // 2 + slant, 0), (w // 2 - slant, h), (0, h)], fill=255)
    combined = Image.composite(left, right, mask).convert("RGBA")

    draw = ImageDraw.Draw(combined)
    top_pt = (w // 2 + slant, 0)
    bot_pt = (w // 2 - slant, h)
    draw.line([top_pt, bot_pt], fill=(*config.PORTADA_VS_LINEA_COLOR, 255), width=config.PORTADA_VS_LINEA_GROSOR)

    cx, cy = w // 2, h // 2
    radius = int(w * 0.075)
    draw.ellipse(
        [cx - radius, cy - radius, cx + radius, cy + radius],
        fill=(*config.PORTADA_VS_BADGE_COLOR, 255), outline=(255, 255, 255, 255), width=max(3, radius // 12),
    )
    badge_font = ImageFont.truetype(config.PORTADA_FONT_PATH, int(radius * 1.1))
    bbox = draw.textbbox((0, 0), "VS", font=badge_font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        (cx - tw / 2 - bbox[0], cy - th / 2 - bbox[1]), "VS", font=badge_font,
        fill=(*config.PORTADA_VS_BADGE_TEXTO_COLOR, 255),
    )
    return combined


# ---------------------------------------------------------------------------
# Composición principal
# ---------------------------------------------------------------------------

def compose_cover(
    w: int, h: int, titulo: str, palabra_clave: str | None, background: Image.Image,
    out_path: Path | None = None, vs_background: tuple[Image.Image, Image.Image] | None = None,
    focus_x_ratio: float | None = None,
) -> Image.Image:
    if vs_background is not None:
        canvas = _compose_vs_background(vs_background[0], vs_background[1], w, h)
    else:
        canvas = _crop_to_cover(background, w, h, focus_x_ratio).convert("RGBA")

    # Oscurecido general uniforme, para que el fotograma no compita con el texto.
    dark = Image.new("RGBA", (w, h), (0, 0, 0, config.PORTADA_OSCURECIDO_OPACIDAD))
    canvas = Image.alpha_composite(canvas, dark)

    draw = ImageDraw.Draw(canvas)
    margen = config.PORTADA_MARGEN_PX
    max_width = w - margen * 2
    marca_h = int(h * config.PORTADA_MARCA_ALTURA_RATIO)

    max_size = max(24, int(h * config.PORTADA_FONT_SIZE_MAX_RATIO))
    min_size = max(14, int(h * config.PORTADA_FONT_SIZE_MIN_RATIO))
    font, lines = _fit_title(
        draw, titulo.upper(), config.PORTADA_FONT_PATH, max_width,
        config.PORTADA_MAX_LINEAS, max_size, min_size,
    )
    bbox = font.getbbox("AÁÑQypg")
    line_height = int((bbox[3] - bbox[1]) * 1.28)
    total_text_h = line_height * len(lines)
    stroke_width = max(2, int(font.size * config.PORTADA_TEXTO_STROKE_RATIO))

    text_bottom = h - marca_h - int(h * 0.06)
    text_top = text_bottom - total_text_h
    pad = int(line_height * config.PORTADA_FRANJA_PADDING_RATIO)

    canvas = _draw_diagonal_band(canvas, text_top - pad, text_bottom + pad, w)
    draw = ImageDraw.Draw(canvas)
    _draw_title_lines(draw, lines, font, palabra_clave, text_top, line_height, w, stroke_width)

    # Logo arriba (misma posición que en los videos).
    logo = Image.open(config.LOGO_PATH).convert("RGBA")
    logo_w = int(w * config.PORTADA_LOGO_ANCHO_RATIO)
    logo_h = int(logo.height * logo_w / logo.width)
    logo = logo.resize((logo_w, logo_h), Image.LANCZOS)
    lx, ly = _logo_position(w, logo_w, logo_h, margen)
    canvas.paste(logo, (lx, ly), logo)

    # Franja inferior de marca.
    draw = ImageDraw.Draw(canvas)
    draw.rectangle([0, h - marca_h, w, h], fill=(*config.PORTADA_MARCA_COLOR_FONDO, 255))
    acento_h = max(2, marca_h // 12)
    draw.rectangle([0, h - marca_h, w, h - marca_h + acento_h], fill=(*config.PORTADA_MARCA_COLOR_ACENTO, 255))
    marca_font = ImageFont.truetype(config.PORTADA_FONT_PATH, max(14, int(marca_h * 0.5)))
    marca_texto = config.PORTADA_MARCA_TEXTO
    mbbox = draw.textbbox((0, 0), marca_texto, font=marca_font)
    mw, mh = mbbox[2] - mbbox[0], mbbox[3] - mbbox[1]
    draw.text(
        ((w - mw) / 2 - mbbox[0], h - marca_h + (marca_h - mh) / 2 - mbbox[1]),
        marca_texto, font=marca_font, fill=(*config.PORTADA_MARCA_COLOR_TEXTO, 255),
    )

    result = canvas.convert("RGB")
    if out_path:
        result.save(out_path, quality=92)
    return result


# ---------------------------------------------------------------------------
# Contact sheet de candidatos
# ---------------------------------------------------------------------------

def build_contact_sheet(candidatos: list[dict], titulo: str, palabra_clave: str | None, out_path: Path) -> None:
    top_n = min(config.PORTADA_CANDIDATOS_TOP_N, len(candidatos))
    top = candidatos[:top_n]

    cell_w, cell_h = 480, 270
    cols = 2
    rows = (top_n + cols - 1) // cols
    pad = 24
    info_h = 66

    grid_w = cols * cell_w + (cols + 1) * pad
    grid_h = rows * (cell_h + info_h) + (rows + 1) * pad

    mini_w = int(config.PORTADA_VERTICAL_SIZE[0] * config.PORTADA_MINIATURA_ESCALA)
    mini_h = int(config.PORTADA_VERTICAL_SIZE[1] * config.PORTADA_MINIATURA_ESCALA)
    mini_n = min(3, top_n)
    mini_section_h = mini_h + 70
    mini_section_w = mini_n * mini_w + (mini_n + 1) * pad

    sheet_w = max(grid_w, mini_section_w) + pad * 2
    sheet_h = grid_h + mini_section_h + 80

    sheet = Image.new("RGB", (sheet_w, sheet_h), (16, 16, 20))
    draw = ImageDraw.Draw(sheet)
    label_font = ImageFont.truetype(config.PORTADA_FONT_PATH, 28)
    small_font = ImageFont.truetype(config.PORTADA_FONT_PATH, 20)
    num_font = ImageFont.truetype(config.PORTADA_FONT_PATH, 44)

    for idx, cand in enumerate(top):
        col, row = idx % cols, idx // cols
        x = pad + col * (cell_w + pad)
        y = pad + row * (cell_h + info_h + pad)
        frame = Image.open(cand["path"]).convert("RGB")
        thumb = _crop_to_cover(frame, cell_w, cell_h)
        sheet.paste(thumb, (x, y))
        outline = tuple(config.PORTADA_COLOR_DESTACADO) if idx == 0 else (90, 90, 90)
        draw.rectangle([x, y, x + cell_w, y + cell_h], outline=outline, width=4)
        draw.ellipse([x + 8, y + 8, x + 58, y + 58], fill=config.PORTADA_VS_BADGE_COLOR)
        draw.text((x + 33, y + 33), str(idx + 1), font=num_font, fill=(255, 255, 255), anchor="mm")
        etiqueta = f"#{idx + 1}  t={cand['timestamp']:.1f}s  {'MEJOR' if idx == 0 else ''}"
        info = f"nitidez {cand['sharpness']:.0f} · rostro {'si' if cand['has_face'] else 'no'} · ojos {cand['eyes_open']} · score {cand['score']}"
        draw.text((x, y + cell_h + 6), etiqueta.strip(), font=label_font, fill=(255, 255, 255))
        draw.text((x, y + cell_h + 38), info, font=small_font, fill=(180, 180, 180))

    my = grid_h + 30
    draw.text(
        (pad, my), "VISTA PREVIA MINIATURA (20%) - asi se lee en el feed",
        font=label_font, fill=tuple(config.PORTADA_COLOR_DESTACADO),
    )
    my += 44
    for i in range(mini_n):
        cand = top[i]
        frame = Image.open(cand["path"]).convert("RGB")
        cand_focus = None
        if cand["face_bbox"]:
            fx, fy, fbw, fbh = cand["face_bbox"]
            cand_focus = (fx + fbw / 2) / cand["frame_size"][0]
        mini_full = compose_cover(
            config.PORTADA_VERTICAL_SIZE[0], config.PORTADA_VERTICAL_SIZE[1], titulo, palabra_clave, frame,
            focus_x_ratio=cand_focus,
        )
        mini = mini_full.resize((mini_w, mini_h), Image.LANCZOS)
        mx = pad + i * (mini_w + pad)
        sheet.paste(mini, (mx, my))
        draw.rectangle([mx, my, mx + mini_w, my + mini_h], outline=(90, 90, 90), width=2)
        draw.text((mx, my + mini_h + 6), f"candidato #{i + 1}", font=small_font, fill=(200, 200, 200))

    sheet.save(out_path, quality=90)


# ---------------------------------------------------------------------------
# Orquestador
# ---------------------------------------------------------------------------

def build_portadas(out_dir: Path, horizontal_path: Path, titulo_portada: str, overrides: dict) -> None:
    palabra_clave = _detectar_palabra_clave(titulo_portada, overrides.get("palabra_clave"))
    vs = _es_composicion_vs(titulo_portada, overrides.get("vs_composicion"))
    imagen_fondo_nombre = overrides.get("imagen_fondo")
    tmp_dir = out_dir / "_candidatos_tmp"
    vs_bg = None
    focus_x_ratio = None

    try:
        if imagen_fondo_nombre:
            img_path = config.RECURSOS_PORTADAS_DIR / imagen_fondo_nombre
            if not img_path.exists():
                raise FileNotFoundError(
                    f"imagen_fondo '{imagen_fondo_nombre}' no existe en {config.RECURSOS_PORTADAS_DIR}"
                )
            fondo = Image.open(img_path).convert("RGB")
            print(f"  Usando imagen propia de fondo: {img_path.name}")
        else:
            duracion = ffprobe_duration(horizontal_path)
            candidatos = extract_candidates(horizontal_path, duracion, tmp_dir)

            elegido_idx = overrides.get("frame_portada")
            if isinstance(elegido_idx, int) and 1 <= elegido_idx <= len(candidatos):
                elegido = candidatos[elegido_idx - 1]
                print(f"  Fotograma elegido a mano: candidato #{elegido_idx} (t={elegido['timestamp']:.1f}s)")
            else:
                elegido = candidatos[0]
                print(
                    f"  Mejor fotograma automatico: t={elegido['timestamp']:.1f}s "
                    f"(nitidez={elegido['sharpness']:.0f}, rostro={'si' if elegido['has_face'] else 'no'}, "
                    f"ojos={elegido['eyes_open']}, score={elegido['score']})"
                )
            fondo = Image.open(elegido["path"]).convert("RGB")
            if elegido["face_bbox"]:
                fx, fy, fbw, fbh = elegido["face_bbox"]
                frame_w = elegido["frame_size"][0]
                focus_x_ratio = (fx + fbw / 2) / frame_w

            if vs:
                por_tiempo = sorted(candidatos, key=lambda c: c["indice"])
                mitad = max(1, len(por_tiempo) // 2)
                primera_mitad, segunda_mitad = por_tiempo[:mitad], por_tiempo[mitad:] or por_tiempo
                izq = max(primera_mitad, key=lambda c: c["score"])
                der = max(segunda_mitad, key=lambda c: c["score"])
                vs_bg = (Image.open(izq["path"]).convert("RGB"), Image.open(der["path"]).convert("RGB"))
                print(f"  Composicion VS: izquierda t={izq['timestamp']:.1f}s / derecha t={der['timestamp']:.1f}s")

            build_contact_sheet(candidatos, titulo_portada, palabra_clave, out_dir / "portada_candidatas.jpg")
            print(f"  Contact sheet: {out_dir / 'portada_candidatas.jpg'}")

        for nombre, size in (("vertical", config.PORTADA_VERTICAL_SIZE), ("horizontal", config.PORTADA_HORIZONTAL_SIZE)):
            compose_cover(
                size[0], size[1], titulo_portada, palabra_clave, fondo,
                out_path=out_dir / f"portada_{nombre}.jpg", vs_background=vs_bg,
                focus_x_ratio=focus_x_ratio,
            )
    finally:
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)
