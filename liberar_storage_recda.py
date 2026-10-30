"""Borra de Supabase Storage los videos de clips de Recda ya publicados antes
de una fecha (default 2026-10-01) y deja video_url en NULL en la fila.
No toca la fila en nada más, ni portadas, ni YouTube, ni qa-fixture.

Uso (desde cualquier carpeta, con el .env del pipeline):
    python liberar_storage_recda.py --env C:\\Audiovisual\\la-herramienta\\rayando-cda-dev\\pipeline\\.env
    python liberar_storage_recda.py --env ... --apply
Sin --apply solo muestra el plan.
"""
import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

BUCKET = "clips-video"
SCHEMA = "rayando_cda"


def storage_path(url):
    marcador = f"/object/public/{BUCKET}/"
    i = (url or "").find(marcador)
    return None if i == -1 else url[i + len(marcador):].split("?", 1)[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", required=True, help="ruta al .env del pipeline")
    ap.add_argument("--antes-de", default="2026-10-01")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    load_dotenv(Path(a.env))
    from supabase import create_client
    from supabase.client import ClientOptions

    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"],
                       options=ClientOptions(schema=SCHEMA))
    filas = (sb.table("clips").select("id, semana, video_url")
             .not_.is_("publicado_en", "null").not_.is_("video_url", "null")
             .neq("semana", "qa-fixture").lt("semana", a.antes_de)
             .order("semana").execute().data)
    plan = [(f, storage_path(f["video_url"])) for f in filas]
    plan = [(f, p) for f, p in plan if p]
    print(f"{len(plan)} videos de clips publicados antes de {a.antes_de}:")
    for f, p in plan:
        print(f"  {f['semana']}  {p}")
    if not a.apply:
        print("\n(plan solamente; agrega --apply para borrar)")
        return 0

    ok = err = 0
    for f, p in plan:
        try:
            sb.storage.from_(BUCKET).remove([p])
            sb.table("clips").update({"video_url": None}).eq("id", f["id"]).execute()
            ok += 1
        except Exception as e:
            err += 1
            print(f"  ERROR {p}: {e}")
    print(f"\nBorrados: {ok}. Errores: {err}.")
    return 1 if err else 0


if __name__ == "__main__":
    sys.exit(main())
