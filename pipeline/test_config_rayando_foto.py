"""Red de seguridad de la unificación (A1a): sin PROGRAMA (o con
PROGRAMA=rayando/recda), config.py tiene que dar EXACTAMENTE las mismas
constantes que el config.py de main antes de fusionar la rama multiprograma.

La foto está en fixtures/config_rayando_main.json. Se generó una sola vez con:

    git show 764edb9:pipeline/config.py > config_main.py
    python test_config_rayando_foto.py --regenerar config_main.py

Solo se regenera si un cambio a Recda es a propósito (y se anota en BITACORA).
Las claves nuevas que agregó la unificación van en CLAVES_NUEVAS con su valor
esperado para Recda.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).parent
FOTO = AQUI / "fixtures" / "config_rayando_main.json"

# Claves que no existían en main. Para Recda tienen que quedar en estos valores
# (o sea, apagadas o iguales a lo que hacía el código antes).
CLAVES_NUEVAS = {
    "PROGRAMA": "rayando",
    "ALIAS_PROGRAMA": {"recda": "rayando"},
    "REDES": ["youtube", "instagram", "tiktok"],
    "DIA_PROGRAMA": 0,
    "PROGRAMAS_DIR": "<PIPELINE>/programas",
    "SUBIR_YOUTUBE": True,
    "LAYOUT_SPLIT_JSON": None,
    "VERTICAL_LAYOUT": "blur",
    "LOGO_POSICION": "bottom-right",
    "MANTENER_CAPITULOS": None,
    "PROMPT_DETECCION": None,
    "CONTEXTO_COPYS": None,
    "PROMPT_CORRECCION_PROGRAMA": None,
    "PROGRAMA_NOMBRE": "Rayando el CDA",
    "WHISPER_CONTEXTO": "Rayando el CDA, programa de Universidad de Chile.",
    "DETECCION_VENTANA_SEG": 0,
    "DETECCION_VENTANA_SOLAPE_SEG": 90,
    "DETECCION_POR_VENTANA_MAX": 3,
    "CANDIDATOS_POOL_N": None,
    "DICCIONARIO_PATH": "<PIPELINE>/diccionario.json",
    "CLIP_OVERRIDES_PATH": "<PIPELINE>/clip_overrides.json",
    # Cambio aprobado por Seba (30/10/2026) para los dos programas: el mp4 de
    # un clip publicado se borra de Storage a los 7 días (limpiar_clips.py).
    "BORRAR_VIDEO_PUBLICADO_DIAS": 7,
    "YOUTUBE_CANAL_ID": None,
}

# Volcado de las constantes de un config.py (en un proceso aparte, para no
# arrastrar el entorno del test).
_VOLCAR = r'''
import json, sys, types
from pathlib import Path
ruta = Path(sys.argv[1]).resolve()
pipeline = Path(sys.argv[2]).resolve()
sys.path.insert(0, str(pipeline))
# Se ejecuta como si estuviera en pipeline/ (PROJECT_DIR sale de __file__).
ns = {"__file__": str(pipeline / "config.py"), "__name__": "config"}
exec(compile(ruta.read_text(encoding="utf-8"), str(ruta), "exec"), ns)

def norm(v):
    if isinstance(v, Path) or (isinstance(v, str) and v.startswith(str(pipeline))):
        s = str(v)
        p = str(pipeline)
        return s.replace(p, "<PIPELINE>").replace("\\", "/") if s.startswith(p) else s.replace("\\", "/")
    if isinstance(v, (set, frozenset)):
        return sorted(norm(x) for x in v)
    if isinstance(v, (list, tuple)):
        return [norm(x) for x in v]
    if isinstance(v, dict):
        return {str(k): norm(x) for k, x in v.items()}
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    return repr(v)

out = {k: norm(v) for k, v in ns.items() if k.isupper() and not k.startswith("_") and not isinstance(v, types.ModuleType)}
print(json.dumps(out, ensure_ascii=False, sort_keys=True))
'''


def volcar(ruta_config: Path, programa: str | None) -> dict:
    env = {k: v for k, v in os.environ.items() if k != "PROGRAMA"}
    if programa is not None:
        env["PROGRAMA"] = programa
    env["PYTHONIOENCODING"] = "utf-8"
    r = subprocess.run(
        [sys.executable, "-c", _VOLCAR, str(ruta_config), str(AQUI)],
        capture_output=True, text=True, encoding="utf-8", env=env, check=True,
    )
    return json.loads(r.stdout)


def comparar(programa: str | None) -> list[str]:
    foto = json.loads(FOTO.read_text(encoding="utf-8"))
    actual = volcar(AQUI / "config.py", programa)
    errores = []
    for k, v in foto.items():
        if k not in actual:
            errores.append(f"{k}: desapareció")
        elif actual[k] != v:
            errores.append(f"{k}: era {v!r}, ahora {actual[k]!r}")
    for k, v in actual.items():
        if k in foto:
            continue
        if k not in CLAVES_NUEVAS:
            errores.append(f"{k}: clave nueva sin declarar en CLAVES_NUEVAS (valor {v!r})")
        elif v != CLAVES_NUEVAS[k]:
            errores.append(f"{k}: clave nueva con valor {v!r}, se esperaba {CLAVES_NUEVAS[k]!r}")
    return errores


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--regenerar":
        FOTO.parent.mkdir(exist_ok=True)
        datos = volcar(Path(sys.argv[2]), None)
        FOTO.write_text(json.dumps(datos, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(f"Foto regenerada: {FOTO} ({len(datos)} constantes)")
        return 0

    fallas = 0
    for programa in (None, "rayando", "recda"):
        errores = comparar(programa)
        etiqueta = f"PROGRAMA={programa}" if programa else "sin PROGRAMA"
        if errores:
            fallas += 1
            print(f"FALLA ({etiqueta}): config de Recda cambió respecto de main:")
            for e in errores:
                print("  -", e)
    if fallas:
        return 1
    print("OK: sin PROGRAMA, con rayando y con recda, config.py da las mismas constantes que main.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
