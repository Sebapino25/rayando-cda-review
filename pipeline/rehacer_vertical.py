"""Rehace el vertical.mp4 de clips ya subidos (sin volver a cortar ni a detectar) y
reemplaza el video en Supabase Storage. Sirve cuando cambia el diseño del vertical
(posición de subtítulos, zócalo, logo) y hay que aplicarlo a clips que ya están en
la app de revisión. No toca YouTube ni crea filas nuevas: actualiza video_url de la
fila existente (con ?v=<hora> para que el navegador no muestre la versión vieja).

Uso (PROGRAMA=spa):
    python rehacer_vertical.py 2026-10-08                 # todos los clips de esa fecha
    python rehacer_vertical.py 2026-10-08 candidato-03 candidato-07
    python rehacer_vertical.py 2026-10-08 --sin-subir     # solo rehace los archivos locales
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import config
import cortar_clip
import publicar


def rehacer(carpeta: Path, subir: bool) -> bool:
    nombre = carpeta.name
    if not (carpeta / "horizontal_original.mp4").exists():
        print(f"  {nombre}: sin horizontal_original.mp4, se omite.")
        return False
    titulo = cortar_clip.titulo_portada_de_copys(carpeta) or cortar_clip._cargar_overrides(nombre).get("titulo_portada")
    tiene_subs = (carpeta / "subtitulos.ass").exists()
    print(f"  {nombre}: rearmando vertical ({'con' if tiene_subs else 'sin'} subtítulos)...")
    cortar_clip.build_vertical(carpeta, tiene_subs, titulo)
    vertical = carpeta / "vertical.mp4"
    publicar.validar_clip(vertical)
    if not subir:
        return True

    fecha = carpeta.parent.name
    storage_path = f"{fecha}/{nombre}.mp4"
    url = publicar.subir_video_storage(vertical, storage_path)
    sb = publicar.get_supabase_client()
    filas = (
        sb.table(config.SUPABASE_TABLE).select("id, video_url").eq("semana", fecha)
        .like("video_url", f"%/{storage_path}%").execute().data
    )
    if len(filas) != 1:
        print(f"  {nombre}: OJO, se esperaba 1 fila en Supabase con ese video y hay {len(filas)}. Video subido, fila sin tocar.")
        return False
    nueva_url = f"{url.split('?')[0]}?v={int(time.time())}"
    sb.table(config.SUPABASE_TABLE).update({"video_url": nueva_url}).eq("id", filas[0]["id"]).execute()
    print(f"  {nombre}: listo ({nueva_url})")
    return True


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("fecha", help="carpeta de la fecha del programa dentro de clips (ej. 2026-10-08)")
    ap.add_argument("clips", nargs="*", help="nombres de carpeta (default: todos los candidato-*)")
    ap.add_argument("--sin-subir", action="store_true", help="solo rehace los archivos locales")
    a = ap.parse_args()

    fecha_dir = config.CLIPS_DIR / a.fecha
    if not fecha_dir.is_dir():
        sys.exit(f"No existe {fecha_dir}")
    nombres = a.clips or sorted(p.name for p in fecha_dir.iterdir() if p.is_dir() and p.name.startswith("candidato-"))
    ok = 0
    for n in nombres:
        try:
            ok += rehacer(fecha_dir / n, subir=not a.sin_subir)
        except Exception as e:  # sigue con el resto
            print(f"  {n}: ERROR {e}")
    print(f"\n{ok} de {len(nombres)} verticales rehechos{'' if a.sin_subir else ' y subidos'}.")


if __name__ == "__main__":
    main()
