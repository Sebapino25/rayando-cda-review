"""Segundo paso (y último) de la autorización manual de TikTok: cambia el
"code" que llegó a mediakit/tiktok-callback.html por un access_token +
refresh_token de verdad, y los guarda en rayando_cda.tiktok_token — de ahí
en más refrescar-token-tiktok (cron) los mantiene al día solo, sin que haga
falta repetir este paso (mientras el refresh_token siga vigente, ~1 año).

El code que da TikTok expira en unos minutos — correr esto enseguida
después de copiarlo de la página de callback.

Requiere TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET, TIKTOK_OAUTH_REDIRECT_URI,
SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY en pipeline/.env.

Uso:
    python tiktok_oauth_intercambiar_codigo.py --code <code>
"""

import argparse
import datetime as dt
import os

import requests
from dotenv import load_dotenv

import config
import publicar

load_dotenv(config.PROJECT_DIR / ".env")


def intercambiar_codigo(code: str, client_key: str, client_secret: str, redirect_uri: str) -> dict:
    resp = requests.post(
        "https://open.tiktokapis.com/v2/oauth/token/",
        headers={"Content-Type": "application/x-www-form-urlencoded", "Cache-Control": "no-cache"},
        data={
            "client_key": client_key,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
        timeout=30,
    )
    data = resp.json()
    if not resp.ok or data.get("error"):
        raise RuntimeError(f"TikTok devolvió un error al intercambiar el code: {resp.status_code} {data}")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--code", required=True, help="El 'code' copiado de mediakit/tiktok-callback.html")
    args = parser.parse_args()

    client_key = os.environ.get("TIKTOK_CLIENT_KEY")
    client_secret = os.environ.get("TIKTOK_CLIENT_SECRET")
    redirect_uri = os.environ.get("TIKTOK_OAUTH_REDIRECT_URI")
    if not client_key or not client_secret or not redirect_uri:
        raise SystemExit(
            "Faltan TIKTOK_CLIENT_KEY / TIKTOK_CLIENT_SECRET / TIKTOK_OAUTH_REDIRECT_URI "
            "en pipeline/.env (ver .env.example)."
        )

    print("Intercambiando el code por un access_token...")
    data = intercambiar_codigo(args.code, client_key, client_secret, redirect_uri)

    access_token = data["access_token"]
    refresh_token = data["refresh_token"]
    expires_in = data["expires_in"]

    print(f"  Listo. Cuenta autorizada (open_id): {data.get('open_id')}")
    print(f"  Scopes concedidos: {data.get('scope')}")
    print(f"  El access_token vence en {expires_in}s (~{expires_in / 3600:.1f}h).")

    vence_en = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=expires_in)).isoformat()

    print("Guardando en rayando_cda.tiktok_token...")
    supabase = publicar.get_supabase_client()
    supabase.table("tiktok_token").upsert(
        {
            "id": True,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "vence_en": vence_en,
        }
    ).execute()
    print("  Guardado. refrescar-token-tiktok se encarga de mantenerlo al día de acá en más.")


if __name__ == "__main__":
    main()
