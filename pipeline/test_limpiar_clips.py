"""Prueba AISLADA de limpiar_clips.py: el filtro de qué filas borrar (puro,
por estado + antigüedad), el parseo de rutas de Storage, y el contrato de
exit codes de main() (0 = nada / dry-run, 3 = se limpió algo, 1 = error) del
que depende auto_procesar.ps1 para decidir la alerta.

No toca Supabase, YouTube ni disco: get_supabase_client() y eliminar_youtube()
se reemplazan por dobles.

Uso:
    python test_limpiar_clips.py
"""
from __future__ import annotations

import datetime as _dt
import sys
from unittest.mock import patch

import limpiar_clips as lc

AHORA = _dt.datetime(2026, 9, 1, tzinfo=_dt.timezone.utc)


def _fila(**kw) -> dict:
    base = {
        "id": "00000000-0000-0000-0000-000000000000",
        "estado": "pendiente",
        "publicado": False,
        "revisado_en": None,
        "created_at": "2026-06-01T00:00:00+00:00",
        "youtube_video_id": "abc123",
        "video_url": None,
        "portada_url": None,
        "youtube_titulo": "clip de prueba",
    }
    base.update(kw)
    return base


def _limpiar(filas):
    return lc.clips_a_limpiar(filas, AHORA, 7, 30)


def test_pendiente_viejo_se_limpia_a_los_7_dias() -> None:
    viejo = _fila(estado="pendiente", created_at="2026-08-20T00:00:00+00:00")  # 12 días
    assert _limpiar([viejo]) == [viejo]


def test_pendiente_reciente_se_conserva() -> None:
    reciente = _fila(estado="pendiente", created_at="2026-08-28T00:00:00+00:00")  # 4 días
    assert _limpiar([reciente]) == []


def test_rechazado_usa_umbral_de_30_dias() -> None:
    hace_10 = _fila(estado="rechazado", revisado_en="2026-08-22T00:00:00+00:00")
    hace_40 = _fila(estado="rechazado", revisado_en="2026-07-23T00:00:00+00:00")
    assert _limpiar([hace_10, hace_40]) == [hace_40]


def test_no_toca_aprobados_publicados_ni_correccion() -> None:
    aprobado = _fila(estado="aprobado", created_at="2026-01-01T00:00:00+00:00")
    publicado = _fila(estado="pendiente", publicado=True, created_at="2026-01-01T00:00:00+00:00")
    correccion = _fila(estado="correccion_video", created_at="2026-01-01T00:00:00+00:00")
    assert _limpiar([aprobado, publicado, correccion]) == []


def test_rechazado_cae_a_created_at_si_no_hay_revisado_en() -> None:
    fila = _fila(estado="rechazado", revisado_en=None, created_at="2026-07-01T00:00:00+00:00")
    assert _limpiar([fila]) == [fila]


def test_storage_path_extrae_carpeta_y_archivo() -> None:
    url = "https://x.supabase.co/storage/v1/object/public/portadas/2026-08-31/candidato-05.jpg"
    assert lc._storage_path(url, "portadas") == "2026-08-31/candidato-05.jpg"
    assert lc._storage_path(url + "?download=p.jpg", "portadas") == "2026-08-31/candidato-05.jpg"
    assert lc._storage_path(None, "portadas") is None
    assert lc._storage_path("https://otro/dominio/x.jpg", "portadas") is None


class _FakeQuery:
    def __init__(self, filas, sink):
        self._filas = filas
        self._sink = sink

    def select(self, *_a, **_k):
        return self

    def in_(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def delete(self):
        self._sink["borradas"] += 1
        return self

    def execute(self):
        return type("R", (), {"data": self._filas})()


class _FakeSupabase:
    def __init__(self, filas, sink):
        self._filas = filas
        self._sink = sink

    def table(self, *_a, **_k):
        return _FakeQuery(self._filas, self._sink)


def _correr_main(argv, filas):
    sink = {"borradas": 0}
    with patch.object(lc.publicar, "get_supabase_client", return_value=_FakeSupabase(filas, sink)), \
         patch.object(lc.publicar, "eliminar_youtube", return_value=None), \
         patch.object(sys, "argv", ["limpiar_clips.py", *argv]):
        code = lc.main()
    return code, sink


def test_exit_0_cuando_no_hay_nada_que_limpiar() -> None:
    code, sink = _correr_main(["--apply"], [])
    assert code == 0 and sink["borradas"] == 0


def test_exit_3_cuando_se_limpia_algo() -> None:
    code, sink = _correr_main(["--apply"], [_fila(created_at="2026-01-01T00:00:00+00:00")])
    assert code == 3 and sink["borradas"] == 1


def test_exit_0_en_dry_run_aunque_haya_candidatos() -> None:
    code, sink = _correr_main([], [_fila(created_at="2026-01-01T00:00:00+00:00")])
    assert code == 0 and sink["borradas"] == 0


def main() -> None:
    test_pendiente_viejo_se_limpia_a_los_7_dias()
    test_pendiente_reciente_se_conserva()
    test_rechazado_usa_umbral_de_30_dias()
    test_no_toca_aprobados_publicados_ni_correccion()
    test_rechazado_cae_a_created_at_si_no_hay_revisado_en()
    test_storage_path_extrae_carpeta_y_archivo()
    test_exit_0_cuando_no_hay_nada_que_limpiar()
    test_exit_3_cuando_se_limpia_algo()
    test_exit_0_en_dry_run_aunque_haya_candidatos()
    print("OK: filtro por estado/antigüedad, parseo de Storage y exit codes de main().")


if __name__ == "__main__":
    main()
