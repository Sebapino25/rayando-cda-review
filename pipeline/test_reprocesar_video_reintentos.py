"""Prueba AISLADA del marcador de intentos fallidos de reprocesar_video:
evita que una fila trabada gaste una llamada a la API de Anthropic (con la
transcripción completa) y un mail de alerta cada 5 minutos para siempre, y
evita que bloquee al resto de los pedidos pendientes (head-of-line blocking
de --uno + orden por created_at).

Usa un archivo de marcador temporal: no toca pipeline\\logs_auto\\ real, ni
Supabase, ni la API.

Uso:
    python test_reprocesar_video_reintentos.py
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import reprocesar_video as rv

FILA_A = {"id": "aaa", "comentarios_video": "Cortá antes de que diga tal cosa"}
FILA_B = {"id": "bbb", "comentarios_video": "Empezá 2 segundos antes"}


def test_sin_marcador_no_hay_fallo_reciente() -> None:
    assert rv.fallo_reciente(FILA_A) is False


def test_registrar_marca_solo_esa_fila() -> None:
    rv.registrar_fallo(FILA_A, "La IA no tiene confianza")
    assert rv.fallo_reciente(FILA_A) is True
    assert rv.fallo_reciente(FILA_B) is False


def test_cambiar_el_texto_del_pedido_habilita_el_reintento() -> None:
    fila_editada = {**FILA_A, "comentarios_video": "Cortá justo cuando dice OTRA cosa"}
    assert rv.fallo_reciente(fila_editada) is False
    # Espacios/saltos de línea de más no cuentan como un pedido distinto.
    fila_igual = {**FILA_A, "comentarios_video": "  Cortá antes de que  diga tal cosa \n"}
    assert rv.fallo_reciente(fila_igual) is True


def test_limpiar_tras_exito_permite_reintentar() -> None:
    rv.limpiar_fallo(FILA_A)
    assert rv.fallo_reciente(FILA_A) is False


def test_uno_saltea_la_fila_trabada_y_toma_la_siguiente() -> None:
    """El caso del head-of-line blocking: A es la más antigua y está trabada,
    así que --uno tiene que procesar B en vez de quedarse pegado en A."""
    rv.registrar_fallo(FILA_A, "La IA no tiene confianza")
    assert rv.seleccionar_para_uno([FILA_A, FILA_B]) == [FILA_B]


def test_todas_trabadas_es_nada_que_hacer_no_un_error() -> None:
    rv.registrar_fallo(FILA_B, "Ambigüedad: 2 carpetas calzan")
    assert rv.seleccionar_para_uno([FILA_A, FILA_B]) == []


def test_marcador_corrupto_no_rompe_y_reintenta() -> None:
    rv.MARCADOR_FALLOS_PATH.write_text("{esto no es json", encoding="utf-8")
    assert rv.fallo_reciente(FILA_A) is False
    assert rv.seleccionar_para_uno([FILA_A, FILA_B]) == [FILA_A]


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="rayando_cda_reintentos_"))
    try:
        with patch.object(rv, "LOGS_AUTO_DIR", tmp), \
             patch.object(rv, "MARCADOR_FALLOS_PATH", tmp / "correccion_video_fallos.log"):
            test_sin_marcador_no_hay_fallo_reciente()
            test_registrar_marca_solo_esa_fila()
            test_cambiar_el_texto_del_pedido_habilita_el_reintento()
            test_limpiar_tras_exito_permite_reintentar()
            test_uno_saltea_la_fila_trabada_y_toma_la_siguiente()
            test_todas_trabadas_es_nada_que_hacer_no_un_error()
            test_marcador_corrupto_no_rompe_y_reintenta()
        print("OK: el marcador de fallos evita reintentos/mails repetidos y no bloquea a las demás filas.")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
