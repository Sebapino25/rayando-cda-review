"""Prueba AISLADA de correlacionar_clip: verifica los casos 0/1/>1
coincidencias al buscar la carpeta local de una fila de Supabase. Usa una
carpeta temporal (monkeypatch de config.CLIPS_DIR), nunca clips reales.

Uso:
    python test_correlacionar_clip.py
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import config
import correlacionar_clip


def _crear_clip(base: Path, semana: str, nombre: str, srt_texto: str) -> None:
    carpeta = base / semana / nombre
    carpeta.mkdir(parents=True)
    srt = f"1\n00:00:00,000 --> 00:00:02,000\n{srt_texto}\n"
    (carpeta / "subtitulos.srt").write_text(srt, encoding="utf-8")


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="rayando_cda_test_"))
    try:
        with patch.object(config, "CLIPS_DIR", tmp):
            _crear_clip(tmp, "2026-07-27", "clip-a", "hola que tal")
            _crear_clip(tmp, "2026-07-27", "clip-b", "otro clip distinto")

            # Caso: 1 coincidencia exacta
            fila_ok = {"semana": "2026-07-27", "transcripcion_original": "hola que tal"}
            resultado = correlacionar_clip.encontrar_carpetas_candidatas(fila_ok)
            assert len(resultado) == 1, f"esperaba 1 coincidencia, hubo {len(resultado)}"
            assert resultado[0].name == "clip-a"

            # Caso: 0 coincidencias
            fila_sin_match = {"semana": "2026-07-27", "transcripcion_original": "esto no existe en ningun lado"}
            resultado = correlacionar_clip.encontrar_carpetas_candidatas(fila_sin_match)
            assert resultado == [], f"esperaba 0 coincidencias, hubo {len(resultado)}"

            # Caso: >1 coincidencias (mismo texto en dos carpetas)
            _crear_clip(tmp, "2026-07-27", "clip-c", "hola que tal")
            resultado = correlacionar_clip.encontrar_carpetas_candidatas(fila_ok)
            assert len(resultado) == 2, f"esperaba 2 coincidencias (ambigüedad), hubo {len(resultado)}"

            # candidata_mas_parecida nunca debe lanzar, solo informar
            pista = correlacionar_clip.candidata_mas_parecida(fila_sin_match)
            assert pista is not None
            assert pista[0].name in ("clip-a", "clip-b", "clip-c")

        print("OK: encontrar_carpetas_candidatas/candidata_mas_parecida cubren los casos 0/1/>1.")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
