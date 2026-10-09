"""Formato vertical dividido (SPAreírse): contenido arriba, conductor que habla abajo.

Se activa con VERTICAL_LAYOUT="split" (perfil del programa). Rayando no lo usa.

Flujo:
  1. planificar(): mira la grabacion MKV multipista de OBS en el tramo del clip y decide
       - en que escena estaba (marcador de color en la esquina),
       - si habia contenido en pantalla (la region de contenido difiere del fondo limpio),
       - quien habla en cada momento (volumen de la pista de cada conductor).
     El resultado (el "plan") se guarda como layout.json junto al clip, para poder
     re-renderizar sin la grabacion original (reprocesar_subtitulos / reprocesar_video).
  2. filtro_split(): arma la parte de video del filter_complex de build_vertical.
     Los tiempos del plan son relativos al inicio de horizontal_original.mp4.

Si algo falla (faltan pistas, escena desconocida, ffmpeg no responde), planificar()
devuelve None y el llamador cae al layout clasico con fondo desenfocado.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np

OUT_W, OUT_H, MITAD = 1080, 1920, 960
ASPECTO_BLOQUE = OUT_W / MITAD  # 1.125: proporcion del bloque donde va cada camara
CIAN, MAGENTA = "0x22D0E8", "0xE432DC"
PLAN_NOMBRE = "layout.json"
TITULO_X, TITULO_W = 200, OUT_W - 200 - 20  # el titulo va a la derecha del logo, en la banda sobre el contenido
ESCENAS_CLIP = ("reaccion_horizontal", "reaccion_vertical", "conversacion")


# ------------------------------------------------------------------ carga de config / plan
def cargar_layout(ruta: Path) -> dict:
    lay = json.loads(Path(ruta).read_text(encoding="utf-8"))
    lay["_dir"] = str(Path(ruta).resolve().parent)
    return lay


def cargar_fondos(layout: dict) -> dict[str, np.ndarray]:
    from PIL import Image
    fondos = {}
    for escena, rel in layout.get("fondos", {}).items():
        ruta = Path(layout["_dir"]) / rel
        if ruta.exists():
            fondos[escena] = np.array(Image.open(ruta).convert("RGB"))
    return fondos


def guardar_plan(out_dir: Path, plan: dict) -> None:
    (Path(out_dir) / PLAN_NOMBRE).write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")


def cargar_plan(out_dir: Path) -> dict | None:
    ruta = Path(out_dir) / PLAN_NOMBRE
    if not ruta.exists():
        return None
    try:
        plan = json.loads(ruta.read_text(encoding="utf-8"))
        if plan.get("escena") in ESCENAS_CLIP and isinstance(plan.get("segs"), list):
            return plan
    except (ValueError, OSError):
        pass
    return None


# ------------------------------------------------------------------ 1. escena y contenido
def detectar_escena(frame: np.ndarray, layout: dict) -> str:
    """Escena segun el color del marcador (promedio del bloque interior, sin 4 px de borde).
    Devuelve una clave de deteccion_de_escena.colores ('sin_clip' si es intro/pausa/cierre)."""
    m = layout["deteccion_de_escena"]
    r = m["region_marcador"]
    zona = frame[r["y"] + 4:r["y"] + r["h"] - 4, r["x"] + 4:r["x"] + r["w"] - 4]
    px = zona.reshape(-1, 3).astype(float).mean(0)
    cols = m["colores"]
    return min(cols, key=lambda k: float(np.linalg.norm(px - np.array(cols[k]))))


def diferencia_contenido(frame: np.ndarray, fondo: np.ndarray, escena: str, layout: dict) -> float | None:
    """Diferencia media (0-255) entre la region de contenido y el fondo limpio. None si no aplica."""
    r = layout["escenas"][escena]["regiones"].get("contenido")
    if r is None:
        return None
    a = frame[r["y"]:r["y"] + r["h"], r["x"]:r["x"] + r["w"]].astype(float)
    b = fondo[r["y"]:r["y"] + r["h"], r["x"]:r["x"] + r["w"]].astype(float)
    return float(np.abs(a - b).mean())


def muestrear_frames(mkv: str, t0: float, dur: float, layout: dict, cada: float = 2.0):
    """Frames RGB a resolucion completa cada `cada` s -> [(t_relativo, ndarray HxWx3)]."""
    w, h = layout["lienzo"]
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{t0:.3f}", "-t", f"{dur:.3f}", "-i", str(mkv),
           "-map", "0:v:0", "-vf", f"fps=1/{cada}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    datos = subprocess.run(cmd, capture_output=True, check=True).stdout
    tam = w * h * 3
    n = len(datos) // tam
    return [(i * cada, np.frombuffer(datos[i * tam:(i + 1) * tam], dtype=np.uint8).reshape(h, w, 3)) for i in range(n)]


def clasificar(frames, layout: dict, fondos: dict) -> dict | None:
    """Escena dominante y si habia contenido. None si ningun cuadro es de una escena de clip."""
    muestras = []
    for t, fr in frames:
        esc = detectar_escena(fr, layout)
        dif = None
        if esc in fondos:
            dif = diferencia_contenido(fr, fondos[esc], esc, layout)
        muestras.append((t, esc, dif))
    conteo = {e: sum(1 for _, x, _ in muestras if x == e) for e in ESCENAS_CLIP}
    if not any(conteo.values()):
        return None
    dominante = max(conteo, key=lambda e: conteo[e])
    umbral = float(layout.get("umbral_contenido", 12.0))
    if dominante == "conversacion" or dominante not in fondos:
        con_contenido = False
    else:
        difs = [d for _, e, d in muestras if e == dominante and d is not None]
        con_contenido = bool(difs) and sum(1 for d in difs if d > umbral) / len(difs) > 0.5
    return {
        "escena": dominante,
        "con_contenido": con_contenido,
        "mezcla_de_escenas": sum(1 for v in conteo.values() if v) > 1,
        "muestras": [[round(t, 1), e, None if d is None else round(d, 1)] for t, e, d in muestras],
    }


# ------------------------------------------------------------------ 2. quien habla
def contar_pistas_audio(mkv: str) -> int:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
                          "-of", "csv=p=0", str(mkv)], capture_output=True, text=True, check=True).stdout
    return len([l for l in out.splitlines() if l.strip()])


def cargar_pista(mkv: str, pista: int, t0: float, dur: float, sr: int = 16000) -> np.ndarray:
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{t0:.3f}", "-t", f"{dur:.3f}", "-i", str(mkv),
           "-map", f"0:a:{pista - 1}", "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"]
    return np.frombuffer(subprocess.run(cmd, capture_output=True, check=True).stdout, dtype=np.float32)


def quien_habla(p1: np.ndarray, p2: np.ndarray, sr: int = 16000, ventana: float = 0.25,
                piso_db: float = -45.0, margen_db: float = 3.0, min_seg: float = 1.0):
    """[(t0, t1, 1|2), ...] en segundos.
    piso_db: bajo esto nadie habla (se mantiene el ultimo). margen_db: el otro debe superar al actual
    por este margen (evita el rebote del mic). min_seg: el candidato debe sostenerse antes de cambiar."""
    w = int(sr * ventana)
    n = min(len(p1), len(p2)) // w
    if n == 0:
        return []
    db = lambda x: 20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-9)
    e1 = np.array([db(p1[i * w:(i + 1) * w]) for i in range(n)])
    e2 = np.array([db(p2[i * w:(i + 1) * w]) for i in range(n)])
    est = [1] * n
    actual, cand, cand_desde = 1, None, 0
    for i in range(n):
        if max(e1[i], e2[i]) < piso_db:
            propuesto = actual
        elif e1[i] > e2[i] + margen_db:
            propuesto = 1
        elif e2[i] > e1[i] + margen_db:
            propuesto = 2
        else:
            propuesto = actual
        if propuesto != actual:
            if cand != propuesto:
                cand, cand_desde = propuesto, i
            if (i - cand_desde + 1) * ventana >= min_seg:
                for j in range(cand_desde, i + 1):  # el cambio parte desde que empezo a hablar
                    est[j] = propuesto
                actual, cand = propuesto, None
                continue
        else:
            cand = None
        est[i] = actual
    segs, ini = [], 0
    for i in range(1, len(est) + 1):
        if i == len(est) or est[i] != est[ini]:
            segs.append((round(ini * ventana, 3), round(i * ventana, 3), est[ini]))
            ini = i
    return segs


# ------------------------------------------------------------------ plan completo
def planificar(mkv: str, t0: float, t1: float, layout: dict, fondos: dict | None = None,
               log=print) -> dict | None:
    """Plan del clip [t0, t1] (segundos de la grabacion; usar los limites REALES del corte, con margen).
    Tiempos de `segs` relativos a t0. None si no se puede (el llamador usa el layout clasico)."""
    dur = t1 - t0
    try:
        fondos = fondos if fondos is not None else cargar_fondos(layout)
        frames = muestrear_frames(mkv, t0, dur, layout)
        info = clasificar(frames, layout, fondos)
        if info is None:
            log("  Layout dividido: ningun cuadro es de una escena de clip (intro/pausa/cierre). Uso fondo desenfocado.")
            return None
        esc = info["escena"]
        if esc != "conversacion" and esc not in fondos:
            log(f"  Layout dividido: falta el fondo limpio de '{esc}'. Uso fondo desenfocado.")
            return None
        pistas = layout["pistas"]
        if contar_pistas_audio(mkv) < max(pistas.values()):
            log("  Layout dividido: la grabacion no tiene las pistas de cada conductor. Uso fondo desenfocado.")
            return None
        p1 = cargar_pista(mkv, pistas["conductor1"], t0, dur)
        p2 = cargar_pista(mkv, pistas["conductor2"], t0, dur)
        segs = quien_habla(p1, p2)
        if not segs:
            segs = [(0.0, round(dur, 3), 1)]
        # el ultimo segmento llega hasta el final real del clip
        a, _, h = segs[-1]
        segs[-1] = (a, round(dur, 3), h)
    except (subprocess.CalledProcessError, OSError, ValueError, KeyError) as exc:
        log(f"  Layout dividido: no se pudo planificar ({type(exc).__name__}: {exc}). Uso fondo desenfocado.")
        return None
    return {"version": 1, "escena": esc, "con_contenido": info["con_contenido"],
            "mezcla_de_escenas": info["mezcla_de_escenas"], "duracion": round(dur, 3),
            "segs": [list(s) for s in segs], "muestras": info["muestras"]}


# ------------------------------------------------------------------ 3. filtro ffmpeg
def _enable(segs, host: int) -> str:
    tr = [f"between(t,{a:.3f},{b:.3f})" for a, b, h in segs if h == host]
    return "+".join(tr) if tr else "0"


def _recorte_cam(cam: dict) -> str:
    """Recorta la camara a la proporcion 1.125 del bloque y escala a 1080x960."""
    cw = min(int(cam["h"] * ASPECTO_BLOQUE) // 2 * 2, cam["w"])
    cx = cam["x"] + int((cam["w"] - cw) * cam.get("encuadre_x", 0.5))
    return f"crop={cw}:{cam['h']}:{cx}:{cam['y']},scale={OUT_W}:{MITAD}:flags=lanczos,setsar=1"


def alto_banda_titulo(plan: dict, layout: dict) -> int:
    """Alto libre arriba del contenido (donde cabe el titulo). 0 si no hay banda (9:16 o sin contenido)."""
    if not plan["con_contenido"] or plan["escena"] != "reaccion_horizontal":
        return 0
    c = layout["escenas"][plan["escena"]]["regiones"]["contenido"]
    alto = min(MITAD, int(OUT_W * c["h"] / c["w"]))
    return (MITAD - alto) // 2


def filtro_split(plan: dict, layout: dict, con_titulo: bool, logo_opacidad: float = 0.9) -> str:
    """Parte de video del filter_complex. Entradas: [0:v] horizontal_original (1920x1080),
    [1:v] logo, [2:v] PNG del titulo (solo si con_titulo). Salida: [withlogo] a 1080x1920."""
    lw, lh = layout["lienzo"]
    reg = layout["escenas"][plan["escena"]]["regiones"]
    c, c1, c2 = reg.get("contenido"), reg["conductor1"], reg["conductor2"]
    segs = plan["segs"]
    base = f"[0:v]scale={lw}:{lh},setsar=1"
    logo = f"format=rgba,colorchannelmixer=aa={logo_opacidad}"
    if plan["con_contenido"] and c is not None:
        cont = f"crop={c['w']}:{c['h']}:{c['x']}:{c['y']}"
        g = [
            f"{base},split=4[s1][s2][s3][s4]",
            f"[s1]{cont},scale={OUT_W}:{MITAD}:force_original_aspect_ratio=increase,crop={OUT_W}:{MITAD},gblur=sigma=30[bg]",
            f"[s2]{cont},scale={OUT_W}:{MITAD}:force_original_aspect_ratio=decrease,setsar=1[fg]",
            "[bg][fg]overlay=(W-w)/2:(H-h)/2[top]",
            f"[s3]{_recorte_cam(c1)}[cam1]",
            f"[s4]{_recorte_cam(c2)}[cam2]",
            f"[cam1][cam2]overlay=0:0:enable='{_enable(segs, 2)}'[bot]",
            f"[top][bot]vstack,drawbox=x=0:y={MITAD - 5}:w={OUT_W}:h=10:color={CIAN}:t=fill[st]",
        ]
        ultimo = "st"
        if con_titulo:
            g.append(f"[st][2:v]overlay={TITULO_X}:0[stt]")
            ultimo = "stt"
        if plan["escena"] == "reaccion_horizontal":
            g.append(f"[1:v]scale=-2:140,{logo}[lg]")
            g.append(f"[{ultimo}][lg]overlay=30:18[withlogo]")
        else:  # contenido 9:16: el logo va en la franja desenfocada de la izquierda
            g.append(f"[1:v]scale=230:-2,{logo}[lg]")
            g.append(f"[{ultimo}][lg]overlay=20:20[withlogo]")
    else:
        g = [
            f"{base},split=2[s3][s4]",
            f"[s3]{_recorte_cam(c1)}[cam1]",
            f"[s4]{_recorte_cam(c2)}[cam2]",
            f"[cam1][cam2]vstack,drawbox=x=0:y=0:w={OUT_W}:h={MITAD}:color={CIAN}:t=10:enable='{_enable(segs, 1)}',"
            f"drawbox=x=0:y={MITAD}:w={OUT_W}:h={MITAD}:color={MAGENTA}:t=10:enable='{_enable(segs, 2)}'[st]",
            f"[1:v]scale=-2:110,{logo}[lg]",
            "[st][lg]overlay=(W-w)/2:(H-h)/2[withlogo]",
        ]
    return ";".join(g)


# ------------------------------------------------------------------ diagnostico (CLI)
def _main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Diagnostico del layout dividido sobre un tramo de la grabacion.")
    ap.add_argument("mkv")
    ap.add_argument("inicio", help="segundos, MM:SS o HH:MM:SS")
    ap.add_argument("fin")
    ap.add_argument("--layout", help="ruta al layout.json (default: el del programa activo)")
    ap.add_argument("--frame", help="guarda un PNG de prueba del 9:16 resultante en esta ruta")
    a = ap.parse_args()

    def tiempo(s: str) -> float:
        p = [float(x) for x in s.split(":")]
        return sum(v * 60 ** i for i, v in enumerate(reversed(p)))

    import config
    ruta = Path(a.layout) if a.layout else config.LAYOUT_SPLIT_JSON
    if not ruta:
        raise SystemExit("Este programa no tiene layout dividido (usa --layout o PROGRAMA=spa).")
    layout = cargar_layout(ruta)
    t0, t1 = tiempo(a.inicio), tiempo(a.fin)
    plan = planificar(a.mkv, t0, t1, layout)
    if plan is None:
        raise SystemExit("No se pudo planificar (ver mensajes arriba).")
    print(f"Escena dominante: {plan['escena']}  | contenido: {plan['con_contenido']}  | mezcla de escenas: {plan['mezcla_de_escenas']}")
    print("Muestras (t, escena, diferencia con fondo; umbral %.1f):" % layout.get("umbral_contenido", 12.0))
    for t, e, d in plan["muestras"]:
        print(f"  {t:6.1f}s  {e:20s} {'' if d is None else d}")
    print("Quien habla (s relativos al inicio):")
    for s0, s1, h in plan["segs"]:
        nombre = layout.get("nombres", {}).get(f"conductor{h}", f"conductor {h}")
        print(f"  {s0:6.2f} - {s1:6.2f}  {nombre}")
    if a.frame:
        logo = str(config.LOGO_PATH)
        fc = filtro_split(plan, layout, False, config.LOGO_OPACIDAD).replace("[withlogo]", "[v]")
        mitad = min(plan["duracion"] / 2, 20)
        cmd = ["ffmpeg", "-y", "-v", "error", "-ss", f"{t0 + mitad:.3f}", "-i", a.mkv, "-i", logo,
               "-filter_complex", fc.replace("between(t,", "between(t+%.3f," % mitad), "-map", "[v]",
               "-frames:v", "1", a.frame]
        subprocess.run(cmd, check=True)
        print(f"PNG de prueba: {a.frame}")


if __name__ == "__main__":
    _main()
