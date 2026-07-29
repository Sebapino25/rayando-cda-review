"""Prueba AISLADA de la lógica de decisión de reprocesar_video.py
(decidir()): localizar la carpeta e interpretar el pedido, SIN tocar
ningún archivo ni llamar a la API real. Mockea correlacionar_clip e
interpretar_correccion.

Uso:
    python test_reprocesar_video_decision.py
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import interpretar_correccion as ic
import reprocesar_video as rv

FILA = {
    "id": "abc-123",
    "semana": "2026-07-27",
    "comentarios_video": "Empezá 2 segundos antes",
    "transcripcion_original": "hola que tal",
}


def test_decide_confiado_cuando_hay_una_carpeta_y_confianza() -> None:
    carpeta_falsa = Path("clips/2026-07-27/clip-a")
    interpretacion = ic.InterpretacionCorreccion(
        confianza=True, timestamp_inicio=10.0, timestamp_fin=20.0, motivo="ok"
    )
    with patch("reprocesar_video.encontrar_carpetas_candidatas", return_value=[carpeta_falsa]), \
         patch("reprocesar_video.interpretar_correccion", return_value=interpretacion), \
         patch("reprocesar_video.cargar_segments_de_carpeta", return_value=[{"start": 0, "end": 1, "text": "x"}]):
        decision = rv.decidir(FILA)
    assert decision.motivo_abort is None
    assert decision.carpeta == carpeta_falsa
    assert decision.nuevo_inicio == 10.0
    assert decision.nuevo_fin == 20.0


def test_aborta_si_no_hay_carpeta() -> None:
    with patch("reprocesar_video.encontrar_carpetas_candidatas", return_value=[]):
        decision = rv.decidir(FILA)
    assert decision.motivo_abort is not None
    assert "carpeta" in decision.motivo_abort.lower()


def test_aborta_si_hay_mas_de_una_carpeta() -> None:
    carpetas = [Path("clips/2026-07-27/clip-a"), Path("clips/2026-07-27/clip-c")]
    with patch("reprocesar_video.encontrar_carpetas_candidatas", return_value=carpetas):
        decision = rv.decidir(FILA)
    assert decision.motivo_abort is not None
    assert "ambig" in decision.motivo_abort.lower() or "más de una" in decision.motivo_abort.lower()


def test_aborta_si_la_ia_no_tiene_confianza() -> None:
    carpeta_falsa = Path("clips/2026-07-27/clip-a")
    interpretacion = ic.InterpretacionCorreccion(
        confianza=False, timestamp_inicio=None, timestamp_fin=None, motivo="frase no encontrada"
    )
    with patch("reprocesar_video.encontrar_carpetas_candidatas", return_value=[carpeta_falsa]), \
         patch("reprocesar_video.interpretar_correccion", return_value=interpretacion), \
         patch("reprocesar_video.cargar_segments_de_carpeta", return_value=[{"start": 0, "end": 1, "text": "x"}]):
        decision = rv.decidir(FILA)
    assert decision.motivo_abort is not None
    assert "frase no encontrada" in decision.motivo_abort


def main() -> None:
    test_decide_confiado_cuando_hay_una_carpeta_y_confianza()
    test_aborta_si_no_hay_carpeta()
    test_aborta_si_hay_mas_de_una_carpeta()
    test_aborta_si_la_ia_no_tiene_confianza()
    print("OK: reprocesar_video.decidir() cubre confiado / sin-carpeta / ambiguo / sin-confianza.")


if __name__ == "__main__":
    main()
