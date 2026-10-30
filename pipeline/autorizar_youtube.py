"""Autoriza (una sola vez) el canal de YouTube de un programa y guarda el token.

    python autorizar_youtube.py --programa spa

Abre el navegador: hay que entrar con la cuenta que administra el canal del
programa y, si Google pregunta, elegir ESE canal (no el personal ni el de
Recda). Al terminar muestra el canal autorizado y su id: el id va en
programas/<programa>.json como "YOUTUBE_CANAL_ID" (dentro de "config"), para
que el pipeline se niegue a subir si alguna vez el token es de otro canal.

No sube ni borra nada. Si el token ya existe, solo muestra de qué canal es.
"""
from __future__ import annotations

import sys

import programa_cli  # noqa: F401  (antes de config: fija PROGRAMA)
import config
import publicar


def main() -> int:
    if config.PROGRAMA == "rayando":
        print("Rayando ya tiene su token (youtube_token.json). Este script es para otros programas: --programa spa")
        return 1
    falta = publicar.youtube_faltante(exigir_token=False)
    if falta:
        print(f"No se puede autorizar todavía: {falta}")
        return 1
    token = publicar._youtube_token_path()
    print(f"Programa: {config.PROGRAMA_NOMBRE}. Token: {token}")
    if not token.exists():
        print("Se abrirá el navegador. Entra con la cuenta del canal del programa y elige ese canal.")
    from googleapiclient.discovery import build

    youtube = build("youtube", "v3", credentials=publicar._youtube_credentials())
    canal_id, nombre = publicar.canal_autorizado(youtube)
    print(f"\nCanal autorizado: {nombre}  (id {canal_id})")
    if config.YOUTUBE_CANAL_ID == canal_id:
        print(f"Coincide con YOUTUBE_CANAL_ID de programas/{config.PROGRAMA}.json. Listo.")
    elif config.YOUTUBE_CANAL_ID:
        print(f"OJO: programas/{config.PROGRAMA}.json espera {config.YOUTUBE_CANAL_ID}. "
              f"Si este no es el canal correcto, borra {token} y vuelve a correr el script.")
        return 1
    else:
        print(f'Si es el canal correcto, agrega "YOUTUBE_CANAL_ID": "{canal_id}" en programas/{config.PROGRAMA}.json (dentro de "config").')
    return 0


if __name__ == "__main__":
    sys.exit(main())
