"""--programa en la línea de comandos.

config.py lee PROGRAMA al importarse, así que la bandera tiene que fijarse
antes de cualquier `import config`. Cada script de entrada importa este módulo
primero:

    import programa_cli  # noqa: F401  (antes de config: fija PROGRAMA)

Saca `--programa X` (o `--programa=X`) de sys.argv y lo deja en la variable
de entorno PROGRAMA, que también ven los subprocesos. Sin la bandera no hace
nada: la variable de entorno sigue funcionando como antes.
"""

from __future__ import annotations

import os
import sys


def aplicar(argv: list[str]) -> list[str]:
    """Devuelve argv sin --programa y fija os.environ["PROGRAMA"] si venía."""
    resto: list[str] = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--programa":
            if i + 1 >= len(argv):
                sys.exit("Error: --programa necesita un valor (rayando, recda o spa).")
            os.environ["PROGRAMA"] = argv[i + 1].strip().lower()
            i += 2
            continue
        if arg.startswith("--programa="):
            os.environ["PROGRAMA"] = arg.split("=", 1)[1].strip().lower()
            i += 1
            continue
        resto.append(arg)
        i += 1
    return resto


if "config" in sys.modules and "--programa" in " ".join(sys.argv):
    sys.exit("Error interno: programa_cli se importó después de config; --programa no tendría efecto.")

sys.argv[1:] = aplicar(sys.argv[1:])
