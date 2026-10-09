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


def test_cortar_y_publicar_sin_publicar_no_sube(tmp_path, layout, fondos, monkeypatch):
    import cortar_clip, publicar
    mkv = tmp_path / "2026-09-30 21-32-08.mkv"
    _mkv_sintetico(mkv, layout, fondos, "reaccion_horizontal", True)
    _logo_falso(tmp_path)
    monkeypatch.setattr(config, "CLIPS_DIR", tmp_path / "clips")
    monkeypatch.setattr(config, "TRANSCRIPTS_DIR", tmp_path / "tr")
    monkeypatch.setattr(config, "CLIP_PAD_SECONDS", 0.0)
    llamadas = []
    monkeypatch.setattr(publicar, "publicar_clip", lambda **k: llamadas.append(k))
    res = cortar_clip.cortar_y_publicar(mkv, 0.5, 5.5, "prueba", publicar_clip=False)
    assert res["sin_publicar"] and not llamadas
    out = Path(res["out_dir"])
    assert (out / "vertical.mp4").exists() and (out / "layout.json").exists()


def test_spa_no_sube_a_youtube():
    assert config.SUBIR_YOUTUBE is False


def test_publicar_clip_sin_youtube_registra_en_supabase(tmp_path, monkeypatch):
    import publicar
    monkeypatch.setattr(config, "CLIPS_DIR", tmp_path)
    out = tmp_path / "2026-10-08" / "candidato-01"
    out.mkdir(parents=True)
    (out / "vertical.mp4").write_bytes(b"x")
    monkeypatch.setattr(publicar, "validar_clip", lambda p: None)
    monkeypatch.setattr(publicar, "subir_youtube", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no debia subir a YouTube")))
    monkeypatch.setattr(publicar, "subir_portada_storage", lambda *a: "https://x/portada.jpg")
    monkeypatch.setattr(publicar, "subir_video_storage", lambda *a: "https://x/video.mp4")
    payloads = []
    monkeypatch.setattr(publicar, "insertar_clip_supabase", lambda p: payloads.append(p) or 42)
    copys = publicar.Copys(**{f: "t" for f in publicar.Copys.__dataclass_fields__}) if hasattr(publicar.Copys, "__dataclass_fields__") else None
    if copys is None:
        pytest.skip("Copys no es dataclass")
    r = publicar.publicar_clip(out, "candidato-01", "2026-10-08", out / "vertical.mp4", copys, "razon", "texto", 1.0, 20.0)
    assert r == {"youtube_video_id": None, "youtube_url": None, "supabase_id": 42}
    assert payloads[0]["youtube_video_id"] is None and payloads[0]["video_url"] == "https://x/video.mp4"


def test_spa_usa_sus_propios_overrides(monkeypatch):
    import cortar_clip
    assert config.CLIP_OVERRIDES_PATH.name == "clip_overrides.json"
    assert config.CLIP_OVERRIDES_PATH.parent.name == "spa"
    # los ajustes de Rayando (ej. candidato-09 con imagen de fondo) no aplican a SPA
    assert cortar_clip._cargar_overrides("candidato-09") == {}


def test_subtitulos_suben_a_la_linea_divisoria(tmp_path, layout):
    import cortar_clip
    ass = tmp_path / "subtitulos.ass"
    cortar_clip.build_clip_ass([(0.0, 1.0, "hola")], ass)
    assert ls.ajustar_subtitulos(ass, layout) is True
    estilo = [l for l in ass.read_text(encoding="utf-8").splitlines() if l.startswith("Style: Default,")][0]
    campos = estilo[len("Style: "):].split(",")
    assert campos[18] == "8" and campos[21] == "985"
    assert ls.ajustar_subtitulos(ass, layout) is False  # idempotente


def test_rehacer_vertical_sin_subir(tmp_path, layout, fondos, monkeypatch):
    import rehacer_vertical
    mkv = tmp_path / "g.mkv"
    _mkv_sintetico(mkv, layout, fondos, "reaccion_vertical", True)
    _logo_falso(tmp_path)
    monkeypatch.setattr(config, "CLIPS_DIR", tmp_path / "clips")
    out = tmp_path / "clips" / "2026-10-08" / "candidato-01"
    out.mkdir(parents=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(mkv), "-map", "0:v:0", "-map", "0:a:0",
                    "-c:v", "libx264", "-c:a", "aac", str(out / "horizontal_original.mp4")], check=True)
    ls.guardar_plan(out, ls.planificar(str(mkv), 0, 6, layout, fondos))
    import cortar_clip
    cortar_clip.build_clip_ass([(0.5, 2.0, "prueba de subtitulo")], out / "subtitulos.ass")
    assert rehacer_vertical.rehacer(out, subir=False, replanificar=False) is True
    assert (out / "vertical.mp4").exists()
    assert "Default" in (out / "subtitulos.ass").read_text(encoding="utf-8")


def _con_zocalo(frame, layout):
    f = frame.copy()
    r, b = layout["zocalo"]["region"], layout["zocalo"]["barra"]
    f[r["y"]:r["y"] + r["h"], r["x"]:r["x"] + r["w"]] = (8, 15, 48)
    f[b["y"] - 8:b["y"] + b["h"] + 8, b["x"] - 1:b["x"] + b["w"] + 1] = layout["zocalo"]["color_barra"]
    return f


def test_zocalo_detectado_por_tramos_y_renderizado(tmp_path, layout, fondos):
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    base = _frame(layout, fondos, "reaccion_vertical", True)
    Image.fromarray(_con_zocalo(base, layout)).save(a)
    Image.fromarray(base).save(b)
    mkv = tmp_path / "z.mkv"
    subprocess.run(["ffmpeg", "-y", "-v", "error",
                    "-loop", "1", "-framerate", "10", "-t", "3", "-i", str(a),
                    "-loop", "1", "-framerate", "10", "-t", "3", "-i", str(b),
                    "-f", "lavfi", "-t", "6", "-i", "sine=f=330",
                    "-f", "lavfi", "-t", "6", "-i", "sine=f=220:d=3,apad=whole_dur=6",
                    "-f", "lavfi", "-t", "6", "-i", "anullsrc=r=44100:cl=mono,atrim=0:3[s];sine=f=440:d=3[t];[s][t]concat=n=2:v=0:a=1",
                    "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]",
                    "-map", "[v]", "-map", "2:a", "-map", "3:a", "-map", "4:a",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(mkv)], check=True)
    plan = ls.planificar(str(mkv), 0, 6, layout, fondos)
    assert len(plan["zocalo"]) == 1
    z0, z1 = plan["zocalo"][0]
    assert z0 == 0 and 2.5 <= z1 <= 3.5
    fc = ls.filtro_split(plan, layout, False)
    assert "[zoc]" in fc and "[1:v]" not in fc  # sin logo propio cuando hay contenido
    _render_y_medir(tmp_path, mkv, plan, layout)


def test_tramos_presentes_descarta_parpadeos():
    assert ls.tramos_presentes([True, False, True, True, True, True, False], 0.25, 2.0) == [(0.5, 1.5)]
