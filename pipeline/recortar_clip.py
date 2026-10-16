"""Mueve el inicio y/o el fin de un clip ya subido (ej. "cortar los primeros 4 segundos")
sin crear una fila nueva: vuelve a cortar desde la grabación original, rehace los
subtítulos, el vertical y el plan del layout, reemplaza el video en Storage y actualiza
timestamp_inicio/fin y la transcripción de la fila existente.

Uso (PROGRAMA=spa):
    python recortar_clip.py 2026-10-15 candidato-05 --inicio 4        # 4 s más tarde el inicio
    python recortar_clip.py 2026-10-15 candidato-05 --fin -2.5        # 2,5 s antes el final
    python recortar_clip.py 2026-10-15 candidato-05 --inicio 4 --sin-subir

Si después se van a aplicar subtítulos corregidos (corregir_subtitulos.py), correr este
script ANTES: la corrección se alinea con los subtítulos del corte nuevo.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import config
import cortar_clip


def recortar(carpeta: Path, d_inicio: float, d_fin: float, subir: bool) -> bool:
    nombre = carpeta.name
    meta_path = carpeta / "metadata.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    fuente = Path(meta["video_fuente"])
    ini = cortar_clip.parse_time(meta["timestamp_inicio"]) + d_inicio
    fin = cortar_clip.parse_time(meta["timestamp_fin"]) + d_fin
    if fin - ini < 5:
        print(f"  {nombre}: el clip quedaría de {fin - ini:.1f} s; no se recorta.")
        return False
    print(f"  {nombre}: {meta['timestamp_inicio']} -> {cortar_clip.format_hhmmss(ini)} | "
          f"{meta['timestamp_fin']} -> {cortar_clip.format_hhmmss(fin)} ({fin - ini:.1f} s)")

    # respaldos de una corrección anterior ya no calzan con el corte nuevo
    for viejo in carpeta.glob("subtitulos_antes_correccion.*"):
        viejo.replace(viejo.with_name(viejo.name.replace("antes_correccion", "antes_recorte")))

    _m, ini_real, fin_real = cortar_clip.cut_horizontal(fuente, ini, fin, carpeta / "horizontal_original.mp4")
    segmentos = cortar_clip.load_master_segments(fuente) or []
    clipped = cortar_clip.clip_segments(segmentos, ini, fin) if segmentos else []
    pad = ini - ini_real
    if pad and clipped:
        clipped = [(a + pad, b + pad, t) for a, b, t in clipped]
    if clipped:
        captions = cortar_clip.split_into_captions(clipped)
        cortar_clip.build_clip_srt(captions, carpeta / "subtitulos.srt")
        cortar_clip.build_clip_ass(captions, carpeta / "subtitulos.ass")
    else:
        for f in ("subtitulos.srt", "subtitulos.ass"):
            (carpeta / f).unlink(missing_ok=True)
    texto = cortar_clip.join_transcripcion(clipped)

    meta.update({"timestamp_inicio": cortar_clip.format_hhmmss(ini), "timestamp_fin": cortar_clip.format_hhmmss(fin),
                 "duracion_segundos": round(fin - ini, 3), "transcripcion": texto})
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    cortar_clip.preparar_plan_layout(fuente, ini_real, fin_real, carpeta)

    import rehacer_vertical
    if not rehacer_vertical.rehacer(carpeta, subir=subir, replanificar=False):
        return False
    if subir:
        import publicar
        sb = publicar.get_supabase_client()
        ruta = f"{carpeta.parent.name}/{nombre}.mp4"
        filas = (sb.table(config.SUPABASE_TABLE).select("id").eq("semana", carpeta.parent.name)
                 .like("video_url", f"%/{ruta}%").execute().data)
        if len(filas) != 1:
            print(f"  {nombre}: OJO, no encontré una sola fila ({len(filas)}); video subido, datos sin actualizar.")
            return False
        sb.table(config.SUPABASE_TABLE).update({
            "timestamp_inicio": ini, "timestamp_fin": fin,
            "transcripcion": texto, "transcripcion_original": texto,
        }).eq("id", filas[0]["id"]).execute()
    print(f"  {nombre}: listo.")
    return True


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("fecha")
    ap.add_argument("clip")
    ap.add_argument("--inicio", type=float, default=0.0, help="segundos a mover el inicio (+ = más tarde)")
    ap.add_argument("--fin", type=float, default=0.0, help="segundos a mover el final (- = antes)")
    ap.add_argument("--sin-subir", action="store_true")
    a = ap.parse_args()
    if not a.inicio and not a.fin:
        sys.exit("Indica --inicio y/o --fin.")
    ok = recortar(config.CLIPS_DIR / a.fecha / a.clip, a.inicio, a.fin, subir=not a.sin_subir)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
