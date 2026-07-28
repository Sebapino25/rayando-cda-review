"""Prueba AISLADA de que load_model_and_start() deja un mensaje claro si
tanto GPU como CPU fallan al cargar el modelo. No requiere GPU real ni
modelo de Whisper descargado: reemplaza WhisperModel por una función que
siempre lanza una excepción.

Uso:
    python test_transcribir_cpu_fallback.py
"""
from __future__ import annotations

import contextlib
import io
from pathlib import Path
from unittest.mock import patch

import transcribir


def fake_whisper_model(model_size, device, compute_type):
    raise RuntimeError(f"fake fail on {device}")


def main() -> None:
    buf = io.StringIO()
    excepcion_capturada = None

    with patch.object(transcribir, "WhisperModel", fake_whisper_model):
        with contextlib.redirect_stdout(buf):
            try:
                transcribir.load_model_and_start(Path("video-inexistente.mkv"), "medium")
            except RuntimeError as e:
                excepcion_capturada = e

    salida = buf.getvalue()
    print(salida)

    assert excepcion_capturada is not None, "Se esperaba que la excepción de CPU se relance"
    assert "fake fail on cpu" in str(excepcion_capturada), (
        f"La excepción relanzada debería ser la de CPU, fue: {excepcion_capturada}"
    )
    assert "No se pudo usar GPU" in salida, "Falta el mensaje de fallback GPU->CPU"
    assert "Falló también en CPU" in salida, (
        "Falta el mensaje claro de que el fallback a CPU también falló"
    )

    print("OK: el fallback a CPU deja un mensaje claro y relanza la excepción original.")


if __name__ == "__main__":
    main()
