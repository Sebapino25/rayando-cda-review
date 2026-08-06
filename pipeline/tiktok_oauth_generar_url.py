"""Genera la URL de autorización OAuth de TikTok para el paso manual único:
Sebastián la abre en el navegador, logueado en la cuenta de TikTok de
@rayandoelcda, aprueba el acceso, y TikTok redirige a
mediakit/tiktok-callback.html con un "code" en la URL — ese code se pega en
tiktok_oauth_intercambiar_codigo.py.

Requiere TIKTOK_CLIENT_KEY y TIKTOK_OAUTH_REDIRECT_URI en pipeline/.env (ver
.env.example). El redirect_uri tiene que ser EXACTO al que está cargado en
TikTok Developers (Login Kit > Redirect URI) — y ese, mientras esté en
revisión, no funciona todavía.

Uso:
    python tiktok_oauth_generar_url.py
"""

import os
import secrets
from urllib.parse import urlencode

from dotenv import load_dotenv

import config

load_dotenv(config.PROJECT_DIR / ".env")

# Scopes que la app tiene aprobados en TikTok Developers (ver Content
# Posting API > Scopes): video.publish para publicar de verdad,
# user.info.basic porque TikTok lo exige como mínimo, video.upload por si
# alguna vez hace falta subir como borrador en vez de publicar directo.
SCOPES = "user.info.basic,video.publish,video.upload"


def main() -> None:
    client_key = os.environ.get("TIKTOK_CLIENT_KEY")
    redirect_uri = os.environ.get("TIKTOK_OAUTH_REDIRECT_URI")
    if not client_key or not redirect_uri:
        raise SystemExit(
            "Faltan TIKTOK_CLIENT_KEY y/o TIKTOK_OAUTH_REDIRECT_URI en pipeline/.env "
            "(ver .env.example)."
        )

    state = secrets.token_urlsafe(16)
    params = {
        "client_key": client_key,
        "scope": SCOPES,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "state": state,
    }
    url = f"https://www.tiktok.com/v2/auth/authorize/?{urlencode(params)}"

    print("Abrí esta URL en el navegador, logueado como @rayandoelcda:\n")
    print(url)
    print(f"\n(state usado para esta corrida, por si hace falta verificarlo: {state})")


if __name__ == "__main__":
    main()
