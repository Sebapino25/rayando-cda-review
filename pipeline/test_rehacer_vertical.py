"""Pruebas de rehacer_vertical._reemplazo_youtube: cuándo se reemplaza el video
de YouTube de un clip corregido (la app reproduce desde YouTube)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import rehacer_vertical as rv

VERTICAL = Path("vertical.mp4")


def _fila(**kw) -> dict:
    base = {"youtube_video_id": "viejo", "publicado": False, "titulo": "t",
            "youtube_titulo": "Título", "youtube_descripcion": "Desc", "capitulo": None}
    base.update(kw)
    return base


def _correr(fila, **patches):
    with patch.object(rv.publicar, "subir_youtube", **patches) as subir, \
         patch.object(rv.config, "SUBIR_YOUTUBE", True):
        return rv._reemplazo_youtube(fila, VERTICAL, "candidato-01", None), subir


def test_reemplaza_si_tiene_youtube_y_no_esta_publicado() -> None:
    cambios, subir = _correr(_fila(), return_value="nuevo")
    assert cambios == {"youtube_video_id": "nuevo"}
    assert subir.call_args.kwargs["descripcion"] == "Título\n\nDesc"


def test_no_toca_publicados_ni_clips_sin_youtube() -> None:
    cambios, subir = _correr(_fila(publicado=True), return_value="nuevo")
    assert cambios == {} and not subir.called
    cambios, subir = _correr(_fila(youtube_video_id=None), return_value="nuevo")
    assert cambios == {} and not subir.called


def test_si_falla_la_subida_no_cambia_la_fila() -> None:
    cambios, _ = _correr(_fila(), side_effect=RuntimeError("cuota"))
    assert cambios == {}


def main() -> None:
    test_reemplaza_si_tiene_youtube_y_no_esta_publicado()
    test_no_toca_publicados_ni_clips_sin_youtube()
    test_si_falla_la_subida_no_cambia_la_fila()
    print("OK: rehacer_vertical reemplaza YouTube solo en clips no publicados y sobrevive a un fallo.")


if __name__ == "__main__":
    main()
