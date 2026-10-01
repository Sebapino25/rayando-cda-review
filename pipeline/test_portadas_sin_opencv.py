"""Prueba AISLADA: portadas debe funcionar sin OpenCV (Smart App Control de
Windows bloqueó cv2.pyd el 30/09/2026 y tumbó reprocesar_video/subtítulos).

Simula cv2 bloqueado (import falla con ImportError) y comprueba que
_score_frame puntúa por nitidez, sin rostros, y que la nitidez numpy
coincide con la de OpenCV cuando éste está disponible.

Uso:
    python test_portadas_sin_opencv.py
"""
from __future__ import annotations

import importlib
import sys

import numpy as np
from PIL import Image


def _importar_portadas_sin_cv2():
    class _Bloqueador:
        def find_spec(self, name, path=None, target=None):
            if name == "cv2" or name.startswith("cv2."):
                raise ImportError("DLL load failed while importing cv2: bloqueada por Control de aplicaciones")
            return None

    for m in [m for m in sys.modules if m == "cv2" or m.startswith("cv2.") or m == "portadas"]:
        del sys.modules[m]
    b = _Bloqueador()
    sys.meta_path.insert(0, b)
    try:
        return importlib.import_module("portadas")
    finally:
        sys.meta_path.remove(b)


def main() -> None:
    rng = np.random.default_rng(0)
    nitida = Image.fromarray(rng.integers(0, 256, (120, 160, 3), dtype=np.uint8))
    plana = Image.new("RGB", (160, 120), (90, 90, 90))

    p = _importar_portadas_sin_cv2()
    assert p.cv2 is None, "cv2 debería quedar en None si falla el import"
    a, b = p._score_frame(nitida), p._score_frame(plana)
    assert a["has_face"] is False and a["face_bbox"] is None
    assert a["sharpness"] > b["sharpness"] == 0.0, (a, b)
    assert a["score"] > b["score"], (a, b)
    print("OK sin OpenCV: nitidez", a["sharpness"], "vs plana", b["sharpness"])

    try:
        import cv2
    except Exception:
        print("OpenCV no disponible aquí; se omite la comparación con cv2.")
        return
    gray = np.asarray(nitida.convert("L"))
    ref = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    mia = p._laplacian_var(gray)
    assert abs(ref - mia) / ref < 0.02, (ref, mia)  # difiere solo en el borde
    print(f"OK equivalencia con cv2: {ref:.1f} ~ {mia:.1f}")


if __name__ == "__main__":
    main()
