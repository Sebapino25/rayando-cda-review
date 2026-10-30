"""Prueba AISLADA de la asignación de capítulo (capitulos.py) y de la línea
+ hashtag de capítulo en la descripción de YouTube
(publicar.descripcion_con_capitulo).

No toca Supabase ni YouTube: la tabla capitulos se simula con un dict
{numero: fecha} que se actualiza igual que lo haría asignar_capitulo().

Uso:
    python test_capitulos.py
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path

import pytest

import capitulos as cap
import publicar

D = _dt.date
SEMILLA = {80: D(2026, 10, 19)}


def _procesar(nombre_mkv: str, tabla: dict[int, _dt.date], **kw) -> int | None:
    """Lo mismo que hace asignar_capitulo(), contra una tabla en memoria."""
    fecha = cap.fecha_programa(cap.inicio_grabacion(Path(nombre_mkv)))
    decision = cap.resolver_capitulo(fecha, tabla, **kw)
    if decision.crear:
        tabla[decision.numero] = fecha
    return decision.numero


def test_lunes_23h_crea_el_siguiente() -> None:
    tabla = dict(SEMILLA)
    assert _procesar("2026-10-26 23-00-00.mkv", tabla) == 81
    assert tabla[81] == D(2026, 10, 26)


def test_martes_0130_cuenta_como_el_lunes_anterior() -> None:
    assert cap.fecha_programa(_dt.datetime(2026, 10, 27, 1, 30)) == D(2026, 10, 26)
    tabla = dict(SEMILLA)
    assert _procesar("2026-10-27 01-30-00.mkv", tabla) == 81
    assert tabla[81] == D(2026, 10, 26)


def test_martes_despues_de_las_6_no_es_lunes() -> None:
    assert cap.fecha_programa(_dt.datetime(2026, 10, 27, 6, 0)) == D(2026, 10, 27)
    assert _procesar("2026-10-27 06-00-00.mkv", dict(SEMILLA)) is None


def test_dos_mkv_el_mismo_lunes_comparten_capitulo() -> None:
    tabla = dict(SEMILLA)
    assert _procesar("2026-10-26 22-52-31.mkv", tabla) == 81
    assert _procesar("2026-10-26 22-56-41.mkv", tabla) == 81
    # y un tercero que arrancó pasada la medianoche
    assert _procesar("2026-10-27 00-40-00.mkv", tabla) == 81
    assert sorted(tabla) == [80, 81]


def test_reprocesar_no_suma() -> None:
    tabla = dict(SEMILLA)
    assert _procesar("2026-10-26 23-00-00.mkv", tabla) == 81
    assert _procesar("2026-10-26 23-00-00.mkv", tabla) == 81
    # el programa ya sembrado (19/10) sigue siendo el 80, no 81 ni 82
    assert _procesar("2026-10-19 22-53-58.mkv", tabla) == 80
    assert sorted(tabla) == [80, 81]


def test_miercoles_sin_flag_queda_sin_capitulo() -> None:
    tabla = dict(SEMILLA)
    assert _procesar("2026-10-21 22-00-00.mkv", tabla) is None
    assert tabla == SEMILLA


def test_miercoles_con_extraordinario_crea_el_siguiente() -> None:
    tabla = dict(SEMILLA)
    fecha = D(2026, 10, 21)
    decision = cap.resolver_capitulo(fecha, tabla, extraordinario=True)
    assert (decision.numero, decision.crear, decision.tipo) == (81, True, "extraordinario")
    assert _procesar("2026-10-21 22-00-00.mkv", tabla, extraordinario=True) == 81
    # reprocesar el mismo extraordinario no suma, y el lunes siguiente es 82
    assert _procesar("2026-10-21 22-00-00.mkv", tabla, extraordinario=True) == 81
    assert _procesar("2026-10-26 23-00-00.mkv", tabla) == 82


def test_capitulo_forzado_debe_existir() -> None:
    assert _procesar("2026-10-21 22-00-00.mkv", dict(SEMILLA), capitulo_forzado=80) == 80
    with pytest.raises(cap.CapituloError):
        cap.resolver_capitulo(D(2026, 10, 21), dict(SEMILLA), capitulo_forzado=99)
    with pytest.raises(cap.CapituloError):
        cap.resolver_capitulo(D(2026, 10, 21), dict(SEMILLA), extraordinario=True, capitulo_forzado=80)


def test_lunes_viejo_sin_capitulo_no_crea_uno_nuevo() -> None:
    tabla = dict(SEMILLA)
    assert _procesar("2026-10-05 22-56-41.mkv", tabla) is None
    assert tabla == SEMILLA


def test_descripcion_con_capitulo() -> None:
    base = "Así está el clima laboral en Rayando\n\nArrancamos un lunes."
    con80 = publicar.descripcion_con_capitulo(base, 80)
    assert con80 == base + "\n\nDel capítulo 80 de Rayando el CDA\n#RECDA80"
    assert con80.endswith("#RECDA80")
    # sin capítulo no se agrega nada
    assert publicar.descripcion_con_capitulo(base, None) == base
    # idempotente, y corregir 80 -> 81 reemplaza en vez de duplicar
    assert publicar.descripcion_con_capitulo(con80, 80) == con80
    con81 = publicar.descripcion_con_capitulo(con80, 81)
    assert con81 == base + "\n\nDel capítulo 81 de Rayando el CDA\n#RECDA81"
    assert "80" not in con81


def main() -> None:
    test_lunes_23h_crea_el_siguiente()
    test_martes_0130_cuenta_como_el_lunes_anterior()
    test_martes_despues_de_las_6_no_es_lunes()
    test_dos_mkv_el_mismo_lunes_comparten_capitulo()
    test_reprocesar_no_suma()
    test_miercoles_sin_flag_queda_sin_capitulo()
    test_miercoles_con_extraordinario_crea_el_siguiente()
    test_capitulo_forzado_debe_existir()
    test_lunes_viejo_sin_capitulo_no_crea_uno_nuevo()
    test_descripcion_con_capitulo()
    print("OK: asignación de capítulo por fecha y línea/hashtag en la descripción.")


if __name__ == "__main__":
    main()
