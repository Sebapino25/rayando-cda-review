"""Prueba AISLADA del reintento ante errores transitorios de Supabase que
usa publicar.py (y, vía publicar.reintentar_transitorio, reprocesar_subtitulos
/ reprocesar_video / limpiar_clips en su primer query).

No toca red ni disco. Uso:
    python test_publicar_reintentos.py
"""
from __future__ import annotations

import httpx
import pytest

import publicar


class _FakeAPIError(Exception):
    """Imita postgrest.exceptions.APIError: expone .code como el 522 real."""

    def __init__(self, code):
        super().__init__({"message": "JSON could not be generated", "code": code})
        self.code = code


def test_es_transitorio_reconoce_errores_de_red_y_5xx() -> None:
    assert publicar._es_error_transitorio(httpx.ConnectError("boom"))
    assert publicar._es_error_transitorio(httpx.ReadTimeout("boom"))
    assert publicar._es_error_transitorio(_FakeAPIError(522))
    assert publicar._es_error_transitorio(_FakeAPIError("503"))
    assert publicar._es_error_transitorio(RuntimeError("[Errno 11001] getaddrinfo failed"))


def test_es_transitorio_ignora_errores_permanentes() -> None:
    assert not publicar._es_error_transitorio(_FakeAPIError("PGRST106"))
    assert not publicar._es_error_transitorio(_FakeAPIError(400))
    assert not publicar._es_error_transitorio(ValueError("payload inválido"))
    assert not publicar._es_error_transitorio(KeyError("id"))


def test_reintenta_y_termina_devolviendo_el_resultado(monkeypatch) -> None:
    monkeypatch.setattr(publicar.time, "sleep", lambda _s: None)
    intentos = {"n": 0}

    def fn():
        intentos["n"] += 1
        if intentos["n"] < 3:
            raise _FakeAPIError(522)
        return "ok"

    assert publicar.reintentar_transitorio(fn, espera_inicial=0.0) == "ok"
    assert intentos["n"] == 3


def test_error_permanente_no_se_reintenta(monkeypatch) -> None:
    monkeypatch.setattr(publicar.time, "sleep", lambda _s: None)
    intentos = {"n": 0}

    def fn():
        intentos["n"] += 1
        raise _FakeAPIError("PGRST106")

    with pytest.raises(_FakeAPIError):
        publicar.reintentar_transitorio(fn)
    assert intentos["n"] == 1


def test_agota_los_intentos_y_relanza_la_ultima_excepcion(monkeypatch) -> None:
    monkeypatch.setattr(publicar.time, "sleep", lambda _s: None)
    intentos = {"n": 0}

    def fn():
        intentos["n"] += 1
        raise httpx.ConnectError("sin red")

    with pytest.raises(httpx.ConnectError):
        publicar.reintentar_transitorio(fn, intentos=4, espera_inicial=0.0)
    assert intentos["n"] == 4


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
