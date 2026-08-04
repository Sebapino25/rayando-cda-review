"""Prueba AISLADA de reprocesar_subtitulos.py: la redistribución de texto
(pura, sin tocar disco/red) y el contrato de exit codes de main() (0 = nada
pendiente, 3 = se aplicó con éxito, 1 = alguna fila se omitió o falló) del
que depende auto_procesar.ps1 para decidir qué alerta mandar.

No toca Supabase, YouTube ni el sistema de archivos: procesar_fila() y
get_supabase_client() se reemplazan por dobles de prueba.

Uso:
    python test_reprocesar_subtitulos.py
"""
from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

import reprocesar_subtitulos as rs

SEGMENTOS = [
    (0.0, 2.0, "hola como estas"),
    (2.0, 4.0, "todo bien"),
    (4.0, 6.0, "genial gracias"),
]


def test_redistribuir_texto_reparte_proporcional_a_las_palabras() -> None:
    resultado = rs.redistribuir_texto(SEGMENTOS, "hola como andas todo excelente genial gracias total")
    # 3 segmentos originales de 3/2/2 palabras -> misma cantidad de bloques,
    # con la última quedándose con el resto exacto (ver redistribuir_texto).
    assert len(resultado) == 3
    assert resultado[0][:2] == (0.0, 2.0)
    assert resultado[-1][:2] == (4.0, 6.0)
    todas_las_palabras = " ".join(texto for _, _, texto in resultado).split()
    assert todas_las_palabras == "hola como andas todo excelente genial gracias total".split()


def test_redistribuir_texto_vacio_no_genera_segmentos() -> None:
    assert rs.redistribuir_texto(SEGMENTOS, "") == []
    assert rs.redistribuir_texto([], "algo") == []


def _correr_main_con(monkeypatch, argv, resultados_procesar_fila, filas):
    monkeypatch.setattr(sys, "argv", ["reprocesar_subtitulos.py", *argv])
    with patch.object(rs.publicar, "get_supabase_client", return_value=object()), \
         patch.object(rs, "buscar_pendientes", return_value=filas), \
         patch.object(rs, "procesar_fila", side_effect=resultados_procesar_fila):
        with pytest.raises(SystemExit) as excinfo:
            rs.main()
    return excinfo.value.code


def test_exit_0_cuando_no_hay_filas_pendientes(monkeypatch) -> None:
    assert _correr_main_con(monkeypatch, ["--apply"], [], []) == 0


def test_exit_3_cuando_se_aplico_todo_con_exito(monkeypatch) -> None:
    filas = [{"id": "a"}, {"id": "b"}]
    assert _correr_main_con(monkeypatch, ["--apply"], [True, True], filas) == 3


def test_exit_0_en_dry_run_aunque_todo_haya_salido_bien(monkeypatch) -> None:
    # Sin --apply: dry-run, todo "hubiera funcionado" -> 0, no 3 (3 implica
    # que de verdad se tocó algo, ver auto_procesar.ps1).
    filas = [{"id": "a"}]
    assert _correr_main_con(monkeypatch, [], [True], filas) == 0


def test_exit_1_cuando_alguna_fila_se_omitio_o_fallo(monkeypatch) -> None:
    filas = [{"id": "a"}, {"id": "b"}]
    assert _correr_main_con(monkeypatch, ["--apply"], [True, False], filas) == 1


def main() -> None:
    import types

    class DummyMonkeypatch:
        def setattr(self, obj, name, value):
            setattr(obj, name, value)

    mp = DummyMonkeypatch()
    test_redistribuir_texto_reparte_proporcional_a_las_palabras()
    test_redistribuir_texto_vacio_no_genera_segmentos()
    test_exit_0_cuando_no_hay_filas_pendientes(mp)
    test_exit_3_cuando_se_aplico_todo_con_exito(mp)
    test_exit_0_en_dry_run_aunque_todo_haya_salido_bien(mp)
    test_exit_1_cuando_alguna_fila_se_omitio_o_fallo(mp)
    print("OK: redistribuir_texto reparte bien y main() devuelve el exit code correcto en los 4 casos.")


if __name__ == "__main__":
    main()
