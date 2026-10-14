"""Aplica subtítulos corregidos a mano (texto completo, sin tiempos) a clips ya cortados.

Los revisores escriben en la app el texto correcto del clip completo. Este script lo
alinea palabra por palabra con los subtítulos actuales (subtitulos.srt), conserva los
tiempos de cada línea, rehace el vertical y lo reemplaza en Supabase Storage. También
deja transcripcion = transcripcion_original = texto corregido en la fila, para que la
app no bloquee "Aprobar".

Uso (PROGRAMA=spa):
    python corregir_subtitulos.py 2026-10-08 correcciones.json             # aplica y sube
    python corregir_subtitulos.py 2026-10-08 correcciones.json --sin-subir # solo archivos locales
    python corregir_subtitulos.py 2026-10-08 correcciones.json --revisar   # solo muestra cómo quedaría

correcciones.json = {"candidato-01": "texto corregido completo", ...}
Antes de tocar nada, los subtítulos anteriores se copian a subtitulos_antes_correccion.srt/.ass.
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import shutil
import sys
import unicodedata
from pathlib import Path

import config
import cortar_clip

SIMILITUD_MINIMA = 0.45  # bajo esto, el texto corregido no parece ser de este clip: no se aplica


def _norm(palabra: str) -> str:
    p = unicodedata.normalize("NFD", palabra.lower())
    p = "".join(c for c in p if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9ñ]", "", p)


def leer_srt(ruta: Path) -> list[tuple[float, float, str]]:
    bloques = re.split(r"\n\s*\n", ruta.read_text(encoding="utf-8").strip())
    cues = []
    for b in bloques:
        lineas = b.strip().splitlines()
        if len(lineas) < 2 or "-->" not in lineas[1]:
            continue
        a, z = [x.strip().replace(",", ".") for x in lineas[1].split("-->")]
        cues.append((cortar_clip.parse_time(a), cortar_clip.parse_time(z), " ".join(lineas[2:]).strip()))
    return cues


def alinear(cues: list[tuple[float, float, str]], texto: str):
    """Reparte las palabras de `texto` en los tiempos de `cues`. Devuelve (nuevos_cues, similitud)."""
    orig = [(w, i) for i, (_, _, t) in enumerate(cues) for w in t.split()]
    nuevas = texto.split()
    a = [_norm(w) for w, _ in orig]
    b = [_norm(w) for w in nuevas]
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    destino: list[int | None] = [None] * len(nuevas)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            for k in range(j2 - j1):
                destino[j1 + k] = orig[i1 + k][1]
        elif op == "replace":
            for k in range(j2 - j1):  # reparto proporcional dentro del tramo reemplazado
                destino[j1 + k] = orig[i1 + min(i2 - i1 - 1, (k * (i2 - i1)) // (j2 - j1))][1]
    # palabras insertadas (que Whisper no escuchó): van con la línea de la palabra anterior
    ultimo = 0
    for j in range(len(destino)):
        if destino[j] is None:
            destino[j] = ultimo
        ultimo = destino[j]
    por_cue: dict[int, list[str]] = {}
    for w, i in zip(nuevas, destino):
        por_cue.setdefault(i, []).append(w)
    nuevos = [(cues[i][0], cues[i][1], " ".join(ws)) for i, ws in sorted(por_cue.items())]
    # una línea que quedó muy cargada se divide en el mismo tiempo
    nuevos = cortar_clip.split_into_captions(nuevos)
    return nuevos, sm.ratio()


def corregir(carpeta: Path, texto: str, subir: bool, solo_revisar: bool) -> bool:
    nombre = carpeta.name
    srt = carpeta / "subtitulos.srt"
    respaldo = carpeta / "subtitulos_antes_correccion.srt"
    base = respaldo if respaldo.exists() else srt  # si se corre dos veces, se alinea contra los originales
    if not base.exists():
        print(f"  {nombre}: no tiene subtitulos.srt, se omite.")
        return False
    cues = leer_srt(base)
    nuevos, sim = alinear(cues, texto)
    print(f"  {nombre}: similitud con el original {sim:.0%}, {len(cues)} -> {len(nuevos)} líneas")
    if sim < SIMILITUD_MINIMA:
        print(f"  {nombre}: OJO, el texto corregido se parece poco a lo que se dice en el clip. No se aplica.")
        return False
    if solo_revisar:
        for cs, ce, t in nuevos[:6]:
            print(f"      {cs:6.2f}-{ce:6.2f}  {t}")
        return True
    if not respaldo.exists():
        shutil.copy2(srt, respaldo)
        if (carpeta / "subtitulos.ass").exists():
            shutil.copy2(carpeta / "subtitulos.ass", carpeta / "subtitulos_antes_correccion.ass")
    cortar_clip.build_clip_srt(nuevos, srt)
    cortar_clip.build_clip_ass(nuevos, carpeta / "subtitulos.ass")

    import rehacer_vertical  # rehace el video con los subtítulos nuevos y lo sube
    if not rehacer_vertical.rehacer(carpeta, subir=subir, replanificar=False):
        return False
    if subir:
        import publicar
        sb = publicar.get_supabase_client()
        ruta = f"{carpeta.parent.name}/{nombre}.mp4"
        filas = (sb.table(config.SUPABASE_TABLE).select("id").eq("semana", carpeta.parent.name)
                 .like("video_url", f"%/{ruta}%").execute().data)
        if len(filas) == 1:
            sb.table(config.SUPABASE_TABLE).update(
                {"transcripcion": texto, "transcripcion_original": texto}).eq("id", filas[0]["id"]).execute()
        else:
            print(f"  {nombre}: OJO, no encontré una sola fila en Supabase ({len(filas)}); video subido, texto sin actualizar.")
    return True


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("fecha")
    ap.add_argument("correcciones", help="JSON {carpeta: texto corregido}")
    ap.add_argument("--sin-subir", action="store_true")
    ap.add_argument("--revisar", action="store_true", help="no cambia nada: muestra similitud y las primeras líneas")
    a = ap.parse_args()
    fecha_dir = config.CLIPS_DIR / a.fecha
    correcciones = json.loads(Path(a.correcciones).read_text(encoding="utf-8"))
    ok = 0
    for nombre, texto in correcciones.items():
        if nombre.startswith("_"):
            continue
        try:
            ok += corregir(fecha_dir / nombre, texto, subir=not a.sin_subir, solo_revisar=a.revisar)
        except Exception as e:
            print(f"  {nombre}: ERROR {e}")
    print(f"\n{ok} de {len([n for n in correcciones if not n.startswith('_')])} clips corregidos.")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
