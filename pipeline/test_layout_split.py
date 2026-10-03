"""Layout vertical dividido (SPA): escena, contenido, quien habla, filtro y render real con ffmpeg sintetico."""
import json
import os
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

import config  # noqa: E402
import layout_split as ls  # noqa: E402

LAYOUT_JSON = Path(__file__).parent / "programas" / "spa" / "layout.json"
pytestmark = [
    pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg no disponible"),
    pytest.mark.skipif(config.PROGRAMA != "spa", reason="se corre con PROGRAMA=spa"),
]


@pytest.fixture(scope="module")
def layout():
    return ls.cargar_layout(LAYOUT_JSON)


@pytest.fixture(scope="module")
def fondos(layout):
    return ls.cargar_fondos(layout)


def _frame(layout, fondos, escena, con_contenido):
    base = fondos.get(escena, fondos["reaccion_horizontal"]).copy()
    col = layout["deteccion_de_escena"]["colores"][escena]
    r = layout["deteccion_de_escena"]["region_marcador"]
    base[r["y"]:r["y"] + r["h"], r["x"]:r["x"] + r["w"]] = col
    if con_contenido:
        c = layout["escenas"][escena]["regiones"]["contenido"]
        base[c["y"]:c["y"] + c["h"], c["x"]:c["x"] + c["w"]] = (200, 40, 40)
    return base


def test_detectar_escena_por_color(layout, fondos):
    for esc in ("reaccion_horizontal", "reaccion_vertical", "conversacion", "sin_clip"):
        assert ls.detectar_escena(_marcar(layout, fondos, esc), layout) == esc


def _marcar(layout, fondos, esc):
    f = fondos["reaccion_horizontal"].copy()
    r = layout["deteccion_de_escena"]["region_marcador"]
    f[r["y"]:r["y"] + r["h"], r["x"]:r["x"] + r["w"]] = layout["deteccion_de_escena"]["colores"][esc]
    return f


def test_contenido_si_y_no(layout, fondos):
    sin = ls.clasificar([(0, _frame(layout, fondos, "reaccion_horizontal", False))], layout, fondos)
    con = ls.clasificar([(0, _frame(layout, fondos, "reaccion_horizontal", True))], layout, fondos)
    assert sin["escena"] == "reaccion_horizontal" and sin["con_contenido"] is False
    assert con["con_contenido"] is True


def test_conversacion_nunca_tiene_contenido(layout, fondos):
    r = ls.clasificar([(0, _marcar(layout, fondos, "conversacion"))], layout, fondos)
    assert r["escena"] == "conversacion" and r["con_contenido"] is False


def test_solo_intro_pausa_devuelve_none(layout, fondos):
    assert ls.clasificar([(0, _marcar(layout, fondos, "sin_clip"))], layout, fondos) is None


def test_escena_dominante_y_mezcla(layout, fondos):
    fr = [(0, _frame(layout, fondos, "reaccion_vertical", True)), (2, _frame(layout, fondos, "reaccion_vertical", True)),
          (4, _marcar(layout, fondos, "conversacion"))]
    r = ls.clasificar(fr, layout, fondos)
    assert r["escena"] == "reaccion_vertical" and r["mezcla_de_escenas"] is True


def _tono(sr, seg, amp):
    n = int(sr * seg)
    return (amp * np.sin(2 * np.pi * 220 * np.arange(n) / sr)).astype(np.float32)


def test_quien_habla_cambia_y_aguanta_rebote():
    sr = 16000
    sil = np.zeros(int(sr * 2), dtype=np.float32)
    p1 = np.concatenate([_tono(sr, 3, .3), sil, _tono(sr, 0.4, .3), sil])      # 1 habla, luego un "mm" corto
    p2 = np.concatenate([np.zeros(int(sr * 3), np.float32), _tono(sr, 2, .3), sil, sil[:0]])
    segs = ls.quien_habla(p1, np.concatenate([p2, np.zeros(len(p1) - len(p2), np.float32)]))
    hosts = [h for _, _, h in segs]
    assert hosts[0] == 1 and 2 in hosts


def test_quien_habla_vacio():
    assert ls.quien_habla(np.zeros(0, np.float32), np.zeros(0, np.float32)) == []


def _plan(escena, con):
    return {"version": 1, "escena": escena, "con_contenido": con, "mezcla_de_escenas": False, "duracion": 4.0,
            "segs": [[0, 2, 1], [2, 4, 2]], "muestras": []}


def test_banda_titulo(layout):
    assert ls.alto_banda_titulo(_plan("reaccion_horizontal", True), layout) > 120
    assert ls.alto_banda_titulo(_plan("reaccion_vertical", True), layout) == 0
    assert ls.alto_banda_titulo(_plan("conversacion", False), layout) == 0


def test_plan_ida_y_vuelta(tmp_path):
    p = _plan("conversacion", False)
    ls.guardar_plan(tmp_path, p)
    assert ls.cargar_plan(tmp_path) == p
    (tmp_path / ls.PLAN_NOMBRE).write_text("{roto", encoding="utf-8")
    assert ls.cargar_plan(tmp_path) is None


def _mkv_sintetico(ruta, layout, fondos, escena, con, dur=6, pistas=3):
    """MKV 1920x1080 con el frame de la escena, audio: mezcla, conductor 1 (0-3 s), conductor 2 (3-6 s)."""
    png = ruta.with_suffix(".png")
    Image.fromarray(_frame(layout, fondos, escena, con)).save(png)
    # tres pistas: mezcla, c1 habla 0-3 s, c2 habla 3-6 s
    cmd = ["ffmpeg", "-y", "-v", "error", "-loop", "1", "-framerate", "10", "-t", str(dur), "-i", str(png),
           "-f", "lavfi", "-t", str(dur), "-i", "sine=f=330",
           "-f", "lavfi", "-t", str(dur), "-i", "sine=f=220:d=3,apad=whole_dur=6",
           "-f", "lavfi", "-t", str(dur), "-i", "anullsrc=r=44100:cl=mono,atrim=0:3[s];sine=f=440:d=3[t];[s][t]concat=n=2:v=0:a=1",
           "-map", "0:v", "-map", "1:a", "-map", "2:a", "-map", "3:a",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(ruta)]
    if pistas == 1:
        cmd = ["ffmpeg", "-y", "-v", "error", "-loop", "1", "-framerate", "10", "-t", str(dur), "-i", str(png),
               "-f", "lavfi", "-t", str(dur), "-i", "sine=f=330", "-map", "0:v", "-map", "1:a",
               "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(ruta)]
    subprocess.run(cmd, check=True)


@pytest.fixture(autouse=True)
def _restaurar_logo():
    antes = config.LOGO_PATH
    yield
    config.LOGO_PATH = antes


def test_planificar_y_render_con_contenido(tmp_path, layout, fondos):
    mkv = tmp_path / "g.mkv"
    _mkv_sintetico(mkv, layout, fondos, "reaccion_horizontal", True)
    plan = ls.planificar(str(mkv), 0, 6, layout, fondos)
    assert plan and plan["escena"] == "reaccion_horizontal" and plan["con_contenido"] is True
    assert plan["segs"][0][2] == 1 and plan["segs"][-1][2] == 2
    assert plan["segs"][-1][1] == pytest.approx(6.0)
    _render_y_medir(tmp_path, mkv, plan, layout)


def test_planificar_y_render_conversacion(tmp_path, layout, fondos):
    mkv = tmp_path / "g.mkv"
    _mkv_sintetico(mkv, layout, fondos, "conversacion", False)
    plan = ls.planificar(str(mkv), 0, 6, layout, fondos)
    assert plan["escena"] == "conversacion" and plan["con_contenido"] is False
    _render_y_medir(tmp_path, mkv, plan, layout)


def test_sin_pistas_de_conductores_devuelve_none(tmp_path, layout, fondos):
    mkv = tmp_path / "g.mkv"
    _mkv_sintetico(mkv, layout, fondos, "reaccion_horizontal", True, pistas=1)
    logs = []
    assert ls.planificar(str(mkv), 0, 6, layout, fondos, log=logs.append) is None
    assert any("pistas" in l for l in logs)


def _render_y_medir(tmp_path, mkv, plan, layout):
    import cortar_clip
    _logo_falso(tmp_path)
    out = tmp_path / "clip"
    out.mkdir()
    # horizontal_original = copia del MKV (solo 1er video + 1er audio), como hace cut_horizontal
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(mkv), "-map", "0:v:0", "-map", "0:a:0",
                    "-c:v", "libx264", "-c:a", "aac", str(out / "horizontal_original.mp4")], check=True)
    ls.guardar_plan(out, plan)
    cortar_clip.build_vertical(out, has_subtitles=False, titulo_portada="Prueba de titulo")
    w, h = cortar_clip.ffprobe_dimensions(out / "vertical.mp4")
    assert (w, h) == (1080, 1920)
    assert abs(cortar_clip.ffprobe_duration(out / "vertical.mp4") - plan["duracion"]) < 0.5


def _logo_falso(tmp_path):
    ruta = tmp_path / "logo.png"
    Image.new("RGBA", (267, 233), (255, 255, 255, 200)).save(ruta)
    config.LOGO_PATH = ruta


def test_plan_desfasado_cae_a_blur(tmp_path, layout, fondos):
    import cortar_clip
    mkv = tmp_path / "g.mkv"
    _mkv_sintetico(mkv, layout, fondos, "conversacion", False)
    out = tmp_path / "clip"
    out.mkdir()
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(mkv), "-map", "0:v:0", "-map", "0:a:0",
                    "-c:v", "libx264", "-c:a", "aac", str(out / "horizontal_original.mp4")], check=True)
    p = _plan("conversacion", False)
    p["duracion"] = 40.0
    ls.guardar_plan(out, p)
    assert cortar_clip._plan_para_vertical(out) is None
