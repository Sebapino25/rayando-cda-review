"""Prueba AISLADA del rollback de reprocesar_video: si un paso técnico falla
DESPUÉS de haber respaldado la versión anterior, la carpeta tiene que quedar
exactamente como estaba, para que la correlación fila<->carpeta (que compara
subtitulos.srt contra transcripcion_original) siga funcionando y el próximo
reintento reporte el error REAL en vez de "no se encontró ninguna carpeta".

Usa carpetas temporales (monkeypatch de config.CLIPS_DIR) y mockea el recorte
y las subidas: no toca clips reales, ni ffmpeg, ni YouTube, ni Supabase.

Uso:
    python test_reprocesar_video_rollback.py
"""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import config
import correlacionar_clip
import reprocesar_video as rv

TEXTO_VIEJO = "hola que tal como andan"
TEXTO_NUEVO = "que tal como andan hoy"

ARCHIVOS = (
    "vertical.mp4", "subtitulos.srt", "subtitulos.ass", "horizontal_original.mp4",
    "portada_vertical.jpg", "portada_horizontal.jpg", "copys.md",
)
COPYS = "# Clip\n\n**Portada:** El anti U es Chile\n\n## YouTube\n**Título:** algo\n"


def _srt(texto: str) -> str:
    return f"1\n00:00:00,000 --> 00:00:02,000\n{texto}\n"


def _crear_clip(base: Path, semana: str, nombre: str, texto: str) -> Path:
    carpeta = base / semana / nombre
    carpeta.mkdir(parents=True)
    (carpeta / "subtitulos.srt").write_text(_srt(texto), encoding="utf-8")
    (carpeta / "subtitulos.ass").write_text("ass viejo", encoding="utf-8")
    (carpeta / "vertical.mp4").write_bytes(b"vertical viejo")
    (carpeta / "horizontal_original.mp4").write_bytes(b"horizontal viejo")
    (carpeta / "portada_vertical.jpg").write_bytes(b"portada vieja")
    (carpeta / "portada_horizontal.jpg").write_bytes(b"portada h vieja")
    (carpeta / "copys.md").write_text(COPYS, encoding="utf-8")
    (carpeta / "metadata.json").write_text(
        json.dumps({"video_fuente": str(base / "2026-07-27 20-00-00.mkv")}), encoding="utf-8"
    )
    return carpeta


def _snapshot(carpeta: Path) -> dict[str, bytes]:
    return {n: (carpeta / n).read_bytes() for n in ARCHIVOS if (carpeta / n).exists()}


def _simular_recorte_nuevo(carpeta: Path) -> None:
    """Lo que dejaría _ejecutar_recorte a medio camino: subtítulos y videos
    del rango NUEVO, mientras la fila de Supabase sigue con el texto VIEJO."""
    (carpeta / "subtitulos.srt").write_text(_srt(TEXTO_NUEVO), encoding="utf-8")
    (carpeta / "subtitulos.ass").write_text("ass nuevo", encoding="utf-8")
    (carpeta / "vertical.mp4").write_bytes(b"vertical nuevo")
    (carpeta / "horizontal_original.mp4").write_bytes(b"horizontal nuevo")
    (carpeta / "portada_vertical.jpg").write_bytes(b"portada nueva")


def test_restaurar_deja_la_carpeta_igual_que_antes(tmp: Path) -> None:
    carpeta = _crear_clip(tmp, "2026-07-27", "clip-a", TEXTO_VIEJO)
    antes = _snapshot(carpeta)

    destino = correlacionar_clip.respaldar_version_anterior(carpeta)
    assert destino.exists()
    _simular_recorte_nuevo(carpeta)

    correlacionar_clip.restaurar_version_respaldada(carpeta, destino)

    assert _snapshot(carpeta) == antes, "los archivos no volvieron a su estado original"
    assert not destino.exists(), f"la carpeta de respaldo {destino} tendría que haberse borrado"
    shutil.rmtree(carpeta.parent)


def test_tras_restaurar_la_correlacion_vuelve_a_encontrar_la_carpeta(tmp: Path) -> None:
    carpeta = _crear_clip(tmp, "2026-07-27", "clip-a", TEXTO_VIEJO)
    fila = {"id": "abc-123", "semana": "2026-07-27", "transcripcion_original": TEXTO_VIEJO}

    destino = correlacionar_clip.respaldar_version_anterior(carpeta)
    _simular_recorte_nuevo(carpeta)
    # Sin restaurar: la carpeta es INENCONTRABLE (el bug que se está arreglando).
    assert correlacionar_clip.encontrar_carpetas_candidatas(fila) == []

    correlacionar_clip.restaurar_version_respaldada(carpeta, destino)
    assert correlacionar_clip.encontrar_carpetas_candidatas(fila) == [carpeta]
    shutil.rmtree(carpeta.parent)


def _fila(carpeta: Path) -> dict:
    return {
        "id": "abc-123",
        "semana": "2026-07-27",
        "comentarios_video": "Empezá 2 segundos antes",
        "transcripcion_original": TEXTO_VIEJO,
        "titulo": "Un clip",
        "youtube_video_id": "VIEJO123",
    }


def _decision(carpeta: Path) -> rv.DecisionReproceso:
    return rv.DecisionReproceso(
        carpeta=carpeta, nuevo_inicio=10.0, nuevo_fin=20.0,
        motivo_abort=None, interpretacion_motivo="ok",
    )


def _decision_titulo(carpeta: Path) -> rv.DecisionReproceso:
    return rv.DecisionReproceso(
        carpeta=carpeta, nuevo_inicio=None, nuevo_fin=None,
        motivo_abort=None, interpretacion_motivo="cambio de título",
        titulo_nuevo="El país es anti U de Chile",
    )


def _procesar_con_fallo(carpeta: Path, decision=None, **mocks):
    """Corre procesar_fila(apply=True) con decidir() mockeado y el fallo que
    se le pase, sin tocar nada real."""
    with patch.object(rv, "decidir", return_value=decision or _decision(carpeta)), \
         patch.object(rv.cortar_clip, "program_date_from_name", return_value="2026-07-27"), \
         patch.object(rv, "registrar_fallo", lambda *a, **k: None), \
         patch.object(rv, "limpiar_fallo", lambda *a, **k: None):
        with patch.multiple(rv, **mocks):
            return rv.procesar_fila(_fila(carpeta), apply=True)


def test_rollback_si_falla_el_recorte(tmp: Path) -> None:
    carpeta = _crear_clip(tmp, "2026-07-27", "clip-a", TEXTO_VIEJO)
    antes = _snapshot(carpeta)

    def recorte_que_falla(*args, **kwargs):
        _simular_recorte_nuevo(carpeta)  # deja archivos parciales del rango nuevo
        raise rv.EjecutarError("ffmpeg explotó")

    ok = _procesar_con_fallo(carpeta, _ejecutar_recorte=recorte_que_falla)

    assert ok is False
    assert _snapshot(carpeta) == antes, "un fallo en el recorte tiene que dejar el clip como estaba"
    assert not (carpeta / "v1").exists()
    shutil.rmtree(carpeta.parent)


def test_rollback_si_falla_youtube(tmp: Path) -> None:
    carpeta = _crear_clip(tmp, "2026-07-27", "clip-a", TEXTO_VIEJO)
    antes = _snapshot(carpeta)

    def recorte_ok(*args, **kwargs):
        _simular_recorte_nuevo(carpeta)
        return carpeta / "vertical.mp4", TEXTO_NUEVO

    publicar_falso = type(
        "P", (), {
            "subir_youtube": staticmethod(lambda *a, **k: (_ for _ in ()).throw(RuntimeError("cuota de YouTube agotada"))),
        },
    )

    ok = _procesar_con_fallo(carpeta, _ejecutar_recorte=recorte_ok, publicar=publicar_falso)

    assert ok is False
    assert _snapshot(carpeta) == antes, "un fallo en YouTube tiene que dejar el clip como estaba"
    assert not (carpeta / "v1").exists()
    shutil.rmtree(carpeta.parent)


def test_exito_no_restaura_y_deja_el_respaldo(tmp: Path) -> None:
    carpeta = _crear_clip(tmp, "2026-07-27", "clip-a", TEXTO_VIEJO)

    def recorte_ok(*args, **kwargs):
        _simular_recorte_nuevo(carpeta)
        return carpeta / "vertical.mp4", TEXTO_NUEVO

    llamadas = {}

    class _PublicarOk:
        @staticmethod
        def subir_youtube(*a, **k):
            return "NUEVO456"

        @staticmethod
        def subir_portada_storage(*a, **k):
            return None

        @staticmethod
        def subir_video_storage(*a, **k):
            return None

        @staticmethod
        def actualizar_clip_supabase(clip_id, campos):
            llamadas["supabase"] = campos

    ok = _procesar_con_fallo(carpeta, _ejecutar_recorte=recorte_ok, publicar=_PublicarOk)

    assert ok is True
    assert llamadas["supabase"]["transcripcion_original"] == TEXTO_NUEVO
    # En el camino feliz NO se restaura: quedan los archivos nuevos y el vN\.
    assert (carpeta / "subtitulos.srt").read_text(encoding="utf-8") == _srt(TEXTO_NUEVO)
    assert (carpeta / "v1" / "subtitulos.srt").read_text(encoding="utf-8") == _srt(TEXTO_VIEJO)
    shutil.rmtree(carpeta.parent)


class _PublicarOk:
    llamadas: dict = {}

    @staticmethod
    def validar_clip(*a, **k):
        return None

    ClipInvalido = RuntimeError

    @staticmethod
    def subir_youtube(*a, **k):
        return "NUEVO456"

    @staticmethod
    def subir_portada_storage(*a, **k):
        return None

    @staticmethod
    def subir_video_storage(*a, **k):
        return None

    @staticmethod
    def actualizar_clip_supabase(clip_id, campos):
        _PublicarOk.llamadas["supabase"] = campos


def _rearmar_falso(carpeta: Path, titulos: list):
    """Reemplaza build_vertical/build_portadas: deja archivos 'nuevos' y
    anota con qué título se llamó."""
    def build_vertical(out_dir, has_subtitles, titulo_portada=None):
        titulos.append(titulo_portada)
        (out_dir / "vertical.mp4").write_bytes(b"vertical titulo nuevo")

    def build_portadas(out_dir, horizontal_path, titulo_portada, overrides):
        assert horizontal_path.exists(), "el horizontal tiene que estar repuesto antes de armar la portada"
        (out_dir / "portada_vertical.jpg").write_bytes(b"portada titulo nuevo")

    return build_vertical, build_portadas


def test_cambio_de_titulo_exito(tmp: Path) -> None:
    carpeta = _crear_clip(tmp, "2026-07-27", "clip-a", TEXTO_VIEJO)
    titulos: list = []
    build_vertical, build_portadas = _rearmar_falso(carpeta, titulos)
    _PublicarOk.llamadas = {}

    with patch.object(rv.cortar_clip, "build_vertical", build_vertical), \
         patch.object(rv.portadas, "build_portadas", build_portadas):
        ok = _procesar_con_fallo(carpeta, decision=_decision_titulo(carpeta), publicar=_PublicarOk,
                                 _ejecutar_recorte=lambda *a, **k: (_ for _ in ()).throw(AssertionError("no debe re-cortar")))

    assert ok is True
    assert titulos == ["El país es anti U de Chile"]
    campos = _PublicarOk.llamadas["supabase"]
    assert campos["youtube_video_id"] == "NUEVO456" and campos["estado"] == "pendiente"
    # Un cambio de título no toca corte ni transcripción.
    assert not {"timestamp_inicio", "timestamp_fin", "transcripcion", "transcripcion_original"} & set(campos)
    # Horizontal y subtítulos siguen siendo los mismos (no se re-cortó) ...
    assert (carpeta / "horizontal_original.mp4").read_bytes() == b"horizontal viejo"
    assert (carpeta / "subtitulos.srt").read_text(encoding="utf-8") == _srt(TEXTO_VIEJO)
    # ... así que la carpeta sigue correlacionando con la fila.
    fila = {"id": "abc-123", "semana": "2026-07-27", "transcripcion_original": TEXTO_VIEJO}
    assert correlacionar_clip.encontrar_carpetas_candidatas(fila) == [carpeta]
    # El título nuevo queda en copys.md para los reprocesos siguientes, sin tocar el resto.
    assert rv.cortar_clip.titulo_portada_de_copys(carpeta) == "El país es anti U de Chile"
    assert "**Título:** algo" in (carpeta / "copys.md").read_text(encoding="utf-8")
    assert (carpeta / "v1" / "portada_vertical.jpg").read_bytes() == b"portada vieja"
    shutil.rmtree(carpeta.parent)


def test_cambio_de_titulo_fallido_deja_todo_como_estaba(tmp: Path) -> None:
    carpeta = _crear_clip(tmp, "2026-07-27", "clip-a", TEXTO_VIEJO)
    antes = _snapshot(carpeta)
    titulos: list = []
    build_vertical, build_portadas = _rearmar_falso(carpeta, titulos)
    publicar_falso = type("P", (_PublicarOk,), {
        "subir_youtube": staticmethod(lambda *a, **k: (_ for _ in ()).throw(RuntimeError("cuota de YouTube agotada"))),
    })

    with patch.object(rv.cortar_clip, "build_vertical", build_vertical), \
         patch.object(rv.portadas, "build_portadas", build_portadas):
        ok = _procesar_con_fallo(carpeta, decision=_decision_titulo(carpeta), publicar=publicar_falso)

    assert ok is False
    assert _snapshot(carpeta) == antes, "portada, copys.md y video tienen que volver a la versión con el título viejo"
    assert not (carpeta / "v1").exists()
    shutil.rmtree(carpeta.parent)


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="rayando_cda_rollback_"))
    try:
        with patch.object(config, "CLIPS_DIR", tmp):
            test_restaurar_deja_la_carpeta_igual_que_antes(tmp)
            test_tras_restaurar_la_correlacion_vuelve_a_encontrar_la_carpeta(tmp)
            test_rollback_si_falla_el_recorte(tmp)
            test_rollback_si_falla_youtube(tmp)
            test_exito_no_restaura_y_deja_el_respaldo(tmp)
            test_cambio_de_titulo_exito(tmp)
            test_cambio_de_titulo_fallido_deja_todo_como_estaba(tmp)
        print("OK: el rollback restaura la carpeta ante fallo de recorte/YouTube, el éxito no restaura, "
              "y el cambio de título re-quema sin re-cortar (y se deshace si falla).")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
