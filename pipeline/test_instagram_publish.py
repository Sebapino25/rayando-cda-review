"""Prueba AISLADA de la conexion con la API de Instagram (Graph API via
Instagram Business Login). NO esta integrado al pipeline real (publicar.py).

Sube una imagen de prueba simple al bucket publico 'portadas' de Supabase
Storage, crea un contenedor de media en Instagram (POST /{ig-user-id}/media)
y lo publica (POST /{ig-user-id}/media_publish) en la cuenta @rayandoelcda.

Uso:
    python test_instagram_publish.py            # publica y deja el post
    python test_instagram_publish.py --delete ID # intenta borrar un post por media id

Requiere en .env: INSTAGRAM_ACCESS_TOKEN, INSTAGRAM_BUSINESS_ACCOUNT_ID,
SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY.
"""
from __future__ import annotations

import os
import sys
import time
from io import BytesIO
from pathlib import Path

import requests
from dotenv import load_dotenv
from PIL import Image, ImageDraw

PROJECT_DIR = Path(__file__).resolve().parent
load_dotenv(PROJECT_DIR / ".env")

GRAPH_API_BASE = "https://graph.instagram.com"
CAPTION = "Prueba interna — se borra enseguida"


def _env(nombre: str) -> str:
    valor = os.environ.get(nombre)
    if not valor:
        raise RuntimeError(f"Falta la variable de entorno {nombre} (revisa tu .env)")
    return valor


def generar_imagen_prueba() -> bytes:
    img = Image.new("RGB", (1080, 1080), color=(8, 24, 51))
    draw = ImageDraw.Draw(img)
    draw.text((80, 500), "PRUEBA INTERNA - RAYANDO EL CDA", fill=(255, 255, 255))
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def subir_imagen_prueba_storage() -> str:
    from supabase import create_client
    from supabase.client import ClientOptions

    url = _env("SUPABASE_URL")
    key = _env("SUPABASE_SERVICE_ROLE_KEY")
    supabase = create_client(url, key, options=ClientOptions(schema="rayando_cda"))

    data = generar_imagen_prueba()
    storage_path = f"prueba/test_instagram_publish_{int(time.time())}.jpg"
    supabase.storage.from_("portadas").upload(
        storage_path, data, {"content-type": "image/jpeg", "upsert": "true"}
    )
    public_url = supabase.storage.from_("portadas").get_public_url(storage_path)
    print(f"  Imagen de prueba subida a Storage: {public_url}")
    return public_url


def crear_contenedor_media(image_url: str) -> str:
    ig_user_id = _env("INSTAGRAM_BUSINESS_ACCOUNT_ID")
    token = _env("INSTAGRAM_ACCESS_TOKEN")
    resp = requests.post(
        f"{GRAPH_API_BASE}/{ig_user_id}/media",
        data={
            "image_url": image_url,
            "caption": CAPTION,
            "access_token": token,
        },
    )
    print(f"  POST /media -> status {resp.status_code}")
    resp.raise_for_status()
    creation_id = resp.json()["id"]
    print(f"  creation_id: {creation_id}")
    return creation_id


def esperar_contenedor_listo(creation_id: str, timeout_s: int = 60) -> None:
    token = _env("INSTAGRAM_ACCESS_TOKEN")
    inicio = time.time()
    while time.time() - inicio < timeout_s:
        resp = requests.get(
            f"{GRAPH_API_BASE}/{creation_id}",
            params={"fields": "status_code", "access_token": token},
        )
        resp.raise_for_status()
        status = resp.json().get("status_code")
        print(f"  status_code del contenedor: {status}")
        if status == "FINISHED":
            return
        if status == "ERROR":
            raise RuntimeError(f"El contenedor de media fallo: {resp.json()}")
        time.sleep(3)
    raise TimeoutError("El contenedor de media no llego a FINISHED a tiempo")


def publicar_contenedor(creation_id: str) -> str:
    ig_user_id = _env("INSTAGRAM_BUSINESS_ACCOUNT_ID")
    token = _env("INSTAGRAM_ACCESS_TOKEN")
    resp = requests.post(
        f"{GRAPH_API_BASE}/{ig_user_id}/media_publish",
        data={"creation_id": creation_id, "access_token": token},
    )
    print(f"  POST /media_publish -> status {resp.status_code}")
    resp.raise_for_status()
    media_id = resp.json()["id"]
    print(f"  media_id publicado: {media_id}")
    return media_id


def obtener_permalink(media_id: str) -> str | None:
    token = _env("INSTAGRAM_ACCESS_TOKEN")
    resp = requests.get(
        f"{GRAPH_API_BASE}/{media_id}",
        params={"fields": "permalink,timestamp", "access_token": token},
    )
    if resp.status_code != 200:
        print(f"  No se pudo obtener el permalink: {resp.status_code} {resp.text}")
        return None
    data = resp.json()
    print(f"  permalink: {data.get('permalink')}  timestamp: {data.get('timestamp')}")
    return data.get("permalink")


def borrar_media(media_id: str) -> bool:
    token = _env("INSTAGRAM_ACCESS_TOKEN")
    resp = requests.delete(f"{GRAPH_API_BASE}/{media_id}", params={"access_token": token})
    print(f"  DELETE /{media_id} -> status {resp.status_code}: {resp.text}")
    return resp.status_code == 200 and resp.json().get("success") is True


def main() -> None:
    if len(sys.argv) >= 3 and sys.argv[1] == "--delete":
        media_id = sys.argv[2]
        print(f"Intentando borrar media_id={media_id}...")
        ok = borrar_media(media_id)
        print("Borrado OK" if ok else "No se pudo borrar via API (borrar a mano en la app)")
        return

    print("1. Subiendo imagen de prueba a Supabase Storage...")
    image_url = subir_imagen_prueba_storage()

    print("2. Creando contenedor de media en Instagram...")
    creation_id = crear_contenedor_media(image_url)

    print("3. Esperando a que el contenedor este listo...")
    esperar_contenedor_listo(creation_id)

    print("4. Publicando...")
    media_id = publicar_contenedor(creation_id)

    print("5. Confirmando con permalink...")
    obtener_permalink(media_id)

    print(f"\nMEDIA ID PUBLICADO: {media_id}")
    print("Borra este post ahora mismo:")
    print(f"  python test_instagram_publish.py --delete {media_id}")


if __name__ == "__main__":
    main()
