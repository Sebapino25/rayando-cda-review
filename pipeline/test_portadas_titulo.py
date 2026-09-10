"""Prueba AISLADA del ajuste de tamaño del título del vertical
(portadas._fit_title + render_video_titulo_png).

Regresión del incidente del 09/09: el título "Un regreso cargado de
simbolismo" wrapeaba a 3 líneas, pero _fit_title elegía el tamaño de fuente
mirando SOLO el ancho, así que el bloque de texto medía ~606px dentro de un
espacio libre de ~379px y la última línea ("SIMBOLISMO") se dibujaba sobre el
video real. Ahora _fit_title acepta max_total_height y render_video_titulo_png
clampea el borde inferior a la altura de la franja.

Uso:
    python test_portadas_titulo.py
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

import config
import portadas

# franja superior típica del vertical 1080x1920 con fuente 16:9 y logo arriba
BAND_H = 611
TOP_OFFSET = 232
USABLE = BAND_H - TOP_OFFSET


def _fit(titulo: str):
    canvas = Image.new("RGBA", (config.VERTICAL_WIDTH, BAND_H))
    draw = ImageDraw.Draw(canvas)
    margen = config.VIDEO_TITULO_MARGEN_PX
    max_width = config.VERTICAL_WIDTH - margen * 2
    max_size = max(24, int(USABLE * config.VIDEO_TITULO_FONT_SIZE_MAX_RATIO))
    min_size = max(14, int(USABLE * config.VIDEO_TITULO_FONT_SIZE_MIN_RATIO))
    font, lines = portadas._fit_title(
        draw, titulo.upper(), config.PORTADA_FONT_PATH, max_width,
        config.VIDEO_TITULO_MAX_LINEAS, max_size, min_size, max_total_height=USABLE,
    )
    bbox = font.getbbox("AÁÑQypg")
    line_height = int((bbox[3] - bbox[1]) * 1.28)
    return font, lines, line_height * len(lines)


def test_titulo_largo_entra_en_el_alto_disponible() -> None:
    _font, lines, total_h = _fit("Un regreso cargado de simbolismo")
    assert total_h <= USABLE, f"el bloque ({total_h}px) no entra en {USABLE}px: {lines}"
    assert len(lines) <= config.VIDEO_TITULO_MAX_LINEAS, lines


def test_titulo_corto_no_se_achica_de_mas() -> None:
    font, lines, _total_h = _fit("¡Solo a 14 puntos!")
    assert len(lines) == 1, lines
    # un título de una línea tiene que quedar razonablemente grande
    assert font.size >= int(USABLE * config.VIDEO_TITULO_FONT_SIZE_MIN_RATIO) + 6


def test_render_no_dibuja_por_debajo_de_la_franja() -> None:
    """El pixel más bajo con tinta del PNG generado tiene que quedar dentro de
    la franja (height), nunca sobre el video real."""
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "titulo.png"
        portadas.render_video_titulo_png(
            out, config.VERTICAL_WIDTH, BAND_H, "Un regreso cargado de simbolismo", TOP_OFFSET
        )
        img = Image.open(out)
        assert img.size == (config.VERTICAL_WIDTH, BAND_H)
        alpha = img.split()[-1]
        filas_con_tinta = [y for y in range(BAND_H) if alpha.crop((0, y, img.width, y + 1)).getbbox()]
        assert filas_con_tinta, "el PNG salió vacío"
        # margen de tolerancia por el stroke/borde del glifo
        assert max(filas_con_tinta) <= BAND_H - 1, max(filas_con_tinta)


def test_sin_max_total_height_el_comportamiento_no_cambia() -> None:
    """El default (max_total_height=None) tiene que seguir eligiendo solo por
    ancho + cantidad de líneas, para no alterar la portada."""
    canvas = Image.new("RGBA", (1080, 1350))
    draw = ImageDraw.Draw(canvas)
    font_a, lines_a = portadas._fit_title(draw, "TITULO DE PRUEBA CORTO", config.PORTADA_FONT_PATH, 960, 3, 120, 40)
    font_b, lines_b = portadas._fit_title(draw, "TITULO DE PRUEBA CORTO", config.PORTADA_FONT_PATH, 960, 3, 120, 40, max_total_height=None)
    assert font_a.size == font_b.size and lines_a == lines_b


def main() -> None:
    test_titulo_largo_entra_en_el_alto_disponible()
    test_titulo_corto_no_se_achica_de_mas()
    test_render_no_dibuja_por_debajo_de_la_franja()
    test_sin_max_total_height_el_comportamiento_no_cambia()
    print("OK: _fit_title respeta el alto disponible y el título no se dibuja sobre el video.")


if __name__ == "__main__":
    main()
