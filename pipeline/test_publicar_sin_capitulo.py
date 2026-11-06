"""El insert no manda `capitulo` cuando el clip no tiene (SPA: su tabla no tiene esa columna).

No toca red ni disco real. Uso:
    python -m pytest test_publicar_sin_capitulo.py
"""
from __future__ import annotations

from pathlib import Path

import pytest

import config
import publicar


@pytest.fixture
def payload_capturado(monkeypatch):
    capturado = {}
    monkeypatch.setattr(config, "SUBIR_YOUTUBE", False)
    monkeypatch.setattr(publicar, "validar_clip", lambda *_: None)
    monkeypatch.setattr(publicar, "numero_clip", lambda *_: 1)
    monkeypatch.setattr(publicar, "subir_portada_storage", lambda *_: "portada")
    monkeypatch.setattr(publicar, "subir_video_storage", lambda *_: "video")

    def insertar(payload):
        capturado.update(payload)
        return "id-prueba"

    monkeypatch.setattr(publicar, "insertar_clip_supabase", insertar)
    return capturado


def _publicar(tmp_path: Path, capitulo):
    copys = publicar.Copys("seo", "portada", "ig", "titulo", "descripcion", "tiktok")
    return publicar.publicar_clip(
        tmp_path, "candidato-01", "2026-11-05", tmp_path / "vertical.mp4", copys,
        "razon", "transcripcion", 1.0, 2.0, capitulo=capitulo,
    )


def test_sin_capitulo_no_va_en_el_insert(tmp_path, payload_capturado):
    _publicar(tmp_path, None)
    assert "capitulo" not in payload_capturado


def test_con_capitulo_va_en_el_insert(tmp_path, payload_capturado):
    _publicar(tmp_path, 81)
    assert payload_capturado["capitulo"] == 81
