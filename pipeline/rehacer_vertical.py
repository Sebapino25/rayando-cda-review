"""Rehace el vertical.mp4 de clips ya subidos (sin volver a cortar ni a detectar) y
reemplaza el video en Supabase Storage. Sirve cuando cambia el diseño del vertical
(posición de subtítulos, zócalo, logo) y hay que aplicarlo a clips que ya están en
la app de revisión. No crea filas nuevas: actualiza video_url de la fila existente
(con ?v=<hora> para que el navegador no muestre la versión vieja). Si el clip tiene
video no listado en YouTube y no está publicado, sube el vertical nuevo y actualiza
youtube_video_id, porque la app reproduce desde YouTube. El video anterior no se
borra (queda no listado; se borra a mano desde YouTube Studio).

Uso (PROGRAMA=spa):
    python rehacer_vertical.py 2026-10-08                 # todos los clips de esa fecha
    python rehacer_vertical.py 2026-10-08 candidato-03 candidato-07
    python rehacer_vertical.py 2026-10-08 --sin-subir     # solo rehace los archivos locales
    python rehacer_vertical.py 2026-10-15 candidato-02 --titulo "¿Vidal DT de la Roja?"  # cambia el título

Por defecto vuelve a mirar la grabación original (metadata.json -> video_fuente) para
recalcular escena, quién habla y zócalo con el layout.json actual.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import programa_cli  # noqa: F401  (antes de config: fija PROGRAMA)
import config
import cortar_clip
import publicar


def cambiar_titulo_copys(carpeta: Path, titulo: str) -> None:
    """Reemplaza las líneas **Portada:** y **Título:** de copys.md por el título nuevo."""
    copys = carpeta / "copys.md"
    texto = copys.read_text(encoding="utf-8") if copys.exists() else ""
    for etiqueta in ("Portada", "Título"):
        patron = re.compile(rf"^\*\*{etiqueta}:\*\*.*$", re.M)
        linea = f"**{etiqueta}:** {titulo}"
        texto = patron.sub(lambda _m: linea, texto) if patron.search(texto) else texto.rstrip("\n") + f"\n{linea}\n"
    copys.write_text(texto, encoding="utf-8")


def rehacer(carpeta: Path, subir: bool, replanificar: bool = True, portadas_tambien: bool = False,
            titulo_nuevo: str | None = None) -> bool:
    nombre = carpeta.name
    if not (carpeta / "horizontal_original.mp4").exists():
        print(f"  {nombre}: sin horizontal_original.mp4, se omite.")
        return False
    if titulo_nuevo:
        cambiar_titulo_copys(carpeta, titulo_nuevo)
        portadas_tambien = True
    if replanificar and config.VERTICAL_LAYOUT == "split":
        # vuelve a mirar la grabación (escena, quién habla, zócalo) con el layout.json actual
        meta = json.loads((carpeta / "metadata.json").read_text(encoding="utf-8"))
        fuente = Path(meta["video_fuente"])
        ini = cortar_clip.parse_time(meta["timestamp_inicio"])
        fin = cortar_clip.parse_time(meta["timestamp_fin"])
        # mismos límites que cut_horizontal (margen de aire)
        ini_real = max(0.0, ini - config.CLIP_PAD_SECONDS)
        fin_real = min(cortar_clip.ffprobe_duration(fuente), fin + config.CLIP_PAD_SECONDS)
        cortar_clip.preparar_plan_layout(fuente, ini_real, fin_real, carpeta)
    titulo = cortar_clip.titulo_portada_de_copys(carpeta) or cortar_clip._cargar_overrides(nombre).get("titulo_portada")
    tiene_subs = (carpeta / "subtitulos.ass").exists()
    print(f"  {nombre}: rearmando vertical ({'con' if tiene_subs else 'sin'} subtítulos)...")
    cortar_clip.build_vertical(carpeta, tiene_subs, titulo)
    vertical = carpeta / "vertical.mp4"
    publicar.validar_clip(vertical)
    if portadas_tambien and titulo:
        import portadas
        print(f"  {nombre}: rearmando portadas...")
        portadas.build_portadas(carpeta, carpeta / "horizontal_original.mp4", titulo, cortar_clip._cargar_overrides(nombre))
    if not subir:
        return True

    fecha = carpeta.parent.name
    storage_path = f"{fecha}/{nombre}.mp4"
    url = publicar.subir_video_storage(vertical, storage_path)
    sb = publicar.get_supabase_client()
    filas = (
        sb.table(config.SUPABASE_TABLE)
        .select("*")  # SPA aún no tiene la columna capitulo
        .eq("semana", fecha)
        .like("video_url", f"%/{storage_path}%").execute().data
    )
    if len(filas) != 1:
        print(f"  {nombre}: OJO, se esperaba 1 fila en Supabase con ese video y hay {len(filas)}. Video subido, fila sin tocar.")
        return False
    nueva_url = f"{url.split('?')[0]}?v={int(time.time())}"
    cambios = {"video_url": nueva_url}
    if portadas_tambien and (carpeta / "portada_vertical.jpg").exists():
        purl = publicar.subir_portada_storage(carpeta / "portada_vertical.jpg", f"{fecha}/{nombre}.jpg")
        cambios["portada_url"] = f"{purl.split('?')[0]}?v={int(time.time())}"
    if titulo_nuevo:
        cambios["youtube_titulo"] = titulo_nuevo
    cambios.update(_reemplazo_youtube(filas[0], vertical, nombre, titulo_nuevo))
    sb.table(config.SUPABASE_TABLE).update(cambios).eq("id", filas[0]["id"]).execute()
    print(f"  {nombre}: listo ({nueva_url})")
    return True


def _reemplazo_youtube(fila: dict, vertical: Path, nombre: str, titulo_nuevo: str | None) -> dict:
    """Sube el vertical nuevo a YouTube si el clip ya tenía video ahí. Devuelve
    los cambios para la fila. Un clip publicado no se toca (su video es el
    público). Si la subida falla, el mp4 de Storage igual queda corregido."""
    anterior = fila.get("youtube_video_id")
    if not anterior or not config.SUBIR_YOUTUBE:
        return {}
    if fila.get("publicado"):
        print(f"  {nombre}: OJO, ya está publicado: el video de YouTube ({anterior}) no se reemplazó.")
        return {}
    descripcion = publicar.descripcion_con_capitulo(
        f"{titulo_nuevo or fila.get('youtube_titulo') or ''}\n\n{fila.get('youtube_descripcion') or ''}".strip(),
        fila.get("capitulo"),
    )
    try:
        nuevo = publicar.subir_youtube(vertical, fila.get("titulo") or config.PROGRAMA_NOMBRE, descripcion=descripcion)
    except Exception as e:  # noqa: BLE001 - la corrección en Storage no se pierde
        print(f"  {nombre}: OJO, no se pudo subir a YouTube ({e}). La app sigue mostrando el video anterior.")
        return {}
    print(f"  {nombre}: YouTube {anterior} -> {nuevo}. El anterior sigue no listado; bórralo a mano en YouTube Studio.")
    return {"youtube_video_id": nuevo}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("fecha", help="carpeta de la fecha del programa dentro de clips (ej. 2026-10-08)")
    ap.add_argument("clips", nargs="*", help="nombres de carpeta (default: todos los candidato-*)")
    ap.add_argument("--sin-subir", action="store_true", help="solo rehace los archivos locales")
    ap.add_argument("--portadas", action="store_true", help="también rehace las portadas y reemplaza la portada en la app")
    ap.add_argument("--titulo", help="cambia el título (portada, título del video y youtube_titulo en la app); usar con un solo clip")
    ap.add_argument("--sin-replanificar", action="store_true",
                    help="usa el layout.json guardado del clip en vez de volver a mirar la grabación")
    a = ap.parse_args()

    fecha_dir = config.CLIPS_DIR / a.fecha
    if not fecha_dir.is_dir():
        sys.exit(f"No existe {fecha_dir}")
    nombres = a.clips or sorted(p.name for p in fecha_dir.iterdir() if p.is_dir() and p.name.startswith("candidato-"))
    if a.titulo and len(nombres) != 1:
        sys.exit("--titulo se usa con un solo clip (ej. candidato-02)")
    ok = 0
    for n in nombres:
        try:
            ok += rehacer(fecha_dir / n, subir=not a.sin_subir, replanificar=not a.sin_replanificar, portadas_tambien=a.portadas,
                           titulo_nuevo=a.titulo)
        except Exception as e:  # sigue con el resto
            print(f"  {n}: ERROR {e}")
    print(f"\n{ok} de {len(nombres)} verticales rehechos{'' if a.sin_subir else ' y subidos'}.")


if __name__ == "__main__":
    main()
