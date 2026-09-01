"""Prueba AISLADA de limpiar_clips.py: el filtro de qué filas borrar (puro,
según el programa vigente y la antigüedad de la `semana`), el parseo de
rutas de Storage, y el contrato de exit codes de main() (0 = nada / dry-run,
3 = se limpió algo, 1 = error) del que depende auto_procesar.ps1.

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

HOY = _dt.date(2026, 9, 1)
VIGENTE = "2026-08-31"


def _fila(**kw) -> dict:
    base = {
        "id": "00000000-0000-0000-0000-000000000000",
        "estado": "pendiente",
        "publicado": False,
        "semana": "2026-08-24",
        "youtube_video_id": "abc123",
        "video_url": None,
        "portada_url": None,
        "youtube_titulo": "clip de prueba",
    }
    base.update(kw)
    return base


def _limpiar(filas):
    return lc.clips_a_limpiar(filas, VIGENTE, HOY, 30)


def test_pendiente_de_programa_anterior_se_borra() -> None:
    anterior = _fila(estado="pendiente", semana="2026-08-24")
    assert _limpiar([anterior]) == [anterior]


def test_pendiente_del_programa_vigente_se_conserva() -> None:
    vigente = _fila(estado="pendiente", semana=VIGENTE)
    assert _limpiar([vigente]) == []


def test_rechazado_de_programa_anterior_se_borra_del_vigente_no() -> None:
    anterior = _fila(estado="rechazado", semana="2026-08-24")
    vigente = _fila(estado="rechazado", semana=VIGENTE)
    assert _limpiar([anterior, vigente]) == [anterior]


def test_aprobado_sin_publicar_dura_hasta_30_dias_desde_su_semana() -> None:
    # semana de hace 5 días: es "antiguo" (no vigente) pero todavía no se borra
    reserva = _fila(estado="aprobado", semana="2026-08-24")
    # semana de hace 40 días: se borra
    caducado = _fila(estado="aprobado", semana="2026-07-20")
    assert _limpiar([reserva, caducado]) == [caducado]


def test_no_toca_publicados_ni_correccion_video() -> None:
    publicado = _fila(estado="aprobado", publicado=True, semana="2026-01-01")
    correccion = _fila(estado="correccion_video", semana="2026-01-01")
    assert _limpiar([publicado, correccion]) == []


def test_sin_programa_vigente_no_borra_pendientes_ni_rechazados() -> None:
    filas = [_fila(estado="pendiente", semana="2026-08-24"),
             _fila(estado="rechazado", semana="2026-08-24")]
    assert lc.clips_a_limpiar(filas, None, HOY, 30) == []


def test_semana_invalida_nunca_se_toca() -> None:
    # fila de prueba con semana no-fecha: no se puede ubicar en el tiempo
    basura = _fila(estado="pendiente", semana="qa-fixture")
    assert _limpiar([basura]) == []
    # y una semana basura como "vigente" no arrastra a los pendientes reales
    real = _fila(estado="pendiente", semana="2026-08-24")
    assert lc.clips_a_limpiar([real], "qa-fixture", HOY, 30) == []


def test_storage_path() -> None:
    url = "https://x.supabase.co/storage/v1/object/public/portadas/2026-08-31/candidato-05.jpg"
    assert lc._storage_path(url, "portadas") == "2026-08-31/candidato-05.jpg"
    assert lc._storage_path(url + "?download=p.jpg", "portadas") == "2026-08-31/candidato-05.jpg"
    assert lc._storage_path(None, "portadas") is None
    assert lc._storage_path("https://otro/dominio/x.jpg", "portadas") is None


class _FakeQuery:
    def __init__(self, filas, sink):
        self._filas = filas
        self._sink = sink
        self.not_ = self

    def select(self, *_a, **_k):
        return self

    def in_(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def is_(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def delete(self):
        self._sink["borradas"] += 1
        return self

    def execute(self):
        return type("R", (), {"data": self._filas})()


class _FakeSupabase:
    def __init__(self, filas, sink, semana="2026-08-31"):
        self._filas = filas
        self._sink = sink
        self._semana = semana

    def table(self, *_a, **_k):
        # _programa_vigente pide select('semana')...order...limit(1); le damos
        # la fila de semana vigente. El resto de las llamadas devuelve `filas`.
        return _FakeQuery(self._filas, self._sink)


def _correr_main(argv, filas, semana_vigente="2026-08-31"):
    sink = {"borradas": 0}
    fake = _FakeSupabase(filas, sink, semana_vigente)
    # _programa_vigente y el select principal comparten el mismo doble: para
    # que _programa_vigente devuelva algo, metemos una fila con `semana`.
    with patch.object(lc, "_programa_vigente", return_value=semana_vigente), \
         patch.object(lc.publicar, "get_supabase_client", return_value=fake), \
         patch.object(lc.publicar, "eliminar_youtube", return_value=None), \
         patch.object(sys, "argv", ["limpiar_clips.py", *argv]):
        code = lc.main()
    return code, sink


def test_exit_0_cuando_no_hay_nada() -> None:
    code, sink = _correr_main(["--apply"], [])
    assert code == 0 and sink["borradas"] == 0


def test_exit_3_cuando_se_limpia_algo() -> None:
    code, sink = _correr_main(["--apply"], [_fila(estado="pendiente", semana="2026-08-24")])
    assert code == 3 and sink["borradas"] == 1


def test_exit_0_en_dry_run() -> None:
    code, sink = _correr_main([], [_fila(estado="pendiente", semana="2026-08-24")])
    assert code == 0 and sink["borradas"] == 0


def main() -> None:
    test_pendiente_de_programa_anterior_se_borra()
    test_pendiente_del_programa_vigente_se_conserva()
    test_rechazado_de_programa_anterior_se_borra_del_vigente_no()
    test_aprobado_sin_publicar_dura_hasta_30_dias_desde_su_semana()
    test_no_toca_publicados_ni_correccion_video()
    test_sin_programa_vigente_no_borra_pendientes_ni_rechazados()
    test_storage_path()
    test_exit_0_cuando_no_hay_nada()
    test_exit_3_cuando_se_limpia_algo()
    test_exit_0_en_dry_run()
    print("OK: filtro por programa vigente / reserva de 30 días, Storage y exit codes.")


if __name__ == "__main__":
    main()
