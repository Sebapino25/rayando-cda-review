"""Corrige el capítulo de uno o varios clips (el capítulo NO se edita en la
app: se corrige con este comando).

Actualiza rayando_cda.clips.capitulo y la descripción en YouTube
(videos.update) de los clips afectados: reemplaza la línea "Del capítulo N
de Rayando el CDA" y el hashtag #RECDA<N> (ver
publicar.descripcion_con_capitulo), sin tocar el resto de la descripción.
Muestra lo que va a hacer y pide confirmación antes de escribir.

Uso:
    python corregir_capitulo.py <clip_id> <N>      # un clip
    python corregir_capitulo.py <AAAA-MM-DD> <N>   # todos los clips de esa semana

Con una fecha, además deja la tabla capitulos coherente: si N no existe, lo
crea con esa fecha (o renumera el capítulo que ya tenía esa fecha), para que
un reproceso de esa grabación vuelva a dar N. El fixture de QA (semana
'qa-fixture') nunca se toca.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import re
import sys

import config
import publicar

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_FECHA_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SEMANA_FIXTURE = "qa-fixture"


def _capitulos(supabase) -> dict[int, str]:
    filas = publicar.reintentar_transitorio(
        supabase.table(config.SUPABASE_CAPITULOS_TABLE).select("numero,fecha").execute
    ).data
    return {int(f["numero"]): f["fecha"] for f in filas}


def _clips(supabase, objetivo: str) -> list[dict]:
    query = supabase.table(config.SUPABASE_TABLE).select("id,semana,capitulo,youtube_video_id,youtube_titulo,titulo")
    if _FECHA_RE.match(objetivo):
        query = query.eq("semana", objetivo)
    else:
        query = query.eq("id", objetivo)
    filas = publicar.reintentar_transitorio(query.execute).data
    return [f for f in filas if f.get("semana") != SEMANA_FIXTURE]


def _plan_tabla(fecha: str, numero: int, capitulos: dict[int, str]) -> dict | None:
    """Cambio en la tabla capitulos para que la fecha quede con N (solo modo fecha)."""
    if numero in capitulos:
        return None
    previo = next((n for n, f in capitulos.items() if f == fecha), None)
    if previo is not None:
        return {"accion": "renumerar", "de": previo, "a": numero}
    tipo = "normal" if _dt.date.fromisoformat(fecha).weekday() == 0 else "extraordinario"
    return {"accion": "crear", "numero": numero, "fecha": fecha, "tipo": tipo}


def _actualizar_youtube(youtube, video_id: str, numero: int) -> bool:
    """Reemplaza la línea/hashtag de capítulo. Devuelve False si no hacía falta."""
    items = youtube.videos().list(part="snippet", id=video_id).execute().get("items", [])
    if not items:
        raise RuntimeError(f"No se encontró el video {video_id} en YouTube")
    snippet = items[0]["snippet"]
    nueva = publicar.descripcion_con_capitulo(snippet.get("description", ""), numero)
    if nueva == snippet.get("description", ""):
        return False
    # videos.update exige el snippet completo (si no, categoryId se puede
    # resetear): se manda el leído con solo la descripción cambiada.
    snippet["description"] = nueva
    youtube.videos().update(part="snippet", body={"id": video_id, "snippet": snippet}).execute()
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Corrige el capítulo de un clip o de todos los clips de una semana.")
    parser.add_argument("objetivo", help="id del clip (uuid) o fecha de la semana (AAAA-MM-DD)")
    parser.add_argument("numero", type=int, help="capítulo correcto")
    args = parser.parse_args()
    es_fecha = bool(_FECHA_RE.match(args.objetivo))

    supabase = publicar.get_supabase_client()
    capitulos = _capitulos(supabase)
    clips = _clips(supabase, args.objetivo)
    if not clips:
        print(f"No hay clips para '{args.objetivo}' (el fixture de QA se excluye).")
        return 1

    plan_tabla = _plan_tabla(args.objetivo, args.numero, capitulos) if es_fecha else None
    if not es_fecha and args.numero not in capitulos:
        print(
            f"El capítulo {args.numero} no existe en la tabla capitulos. Para crearlo, corrige por "
            "fecha (python corregir_capitulo.py AAAA-MM-DD N)."
        )
        return 1

    print(f"Capítulo -> {args.numero} para {len(clips)} clip(s):")
    for c in clips:
        print(
            f"  - {c['id']} semana {c['semana']} | capítulo actual {c.get('capitulo')} | "
            f"YouTube {c.get('youtube_video_id') or '(sin video)'} | {c.get('youtube_titulo') or c.get('titulo')}"
        )
    if plan_tabla and plan_tabla["accion"] == "crear":
        print(f"Tabla capitulos: se crea el {plan_tabla['numero']} ({plan_tabla['tipo']}) con fecha {plan_tabla['fecha']}.")
    elif plan_tabla:
        print(f"Tabla capitulos: el capítulo {plan_tabla['de']} (fecha {args.objetivo}) pasa a ser el {plan_tabla['a']}.")
    print("Se actualiza la descripción de cada video en YouTube (línea y hashtag de capítulo).")

    if input("¿Confirmar? (s/N): ").strip().lower() not in ("s", "si", "sí"):
        print("Cancelado, no se escribió nada.")
        return 1

    tabla = supabase.table(config.SUPABASE_CAPITULOS_TABLE)
    if plan_tabla and plan_tabla["accion"] == "crear":
        publicar.reintentar_transitorio(
            tabla.insert({k: plan_tabla[k] for k in ("numero", "fecha", "tipo")}).execute
        )
    elif plan_tabla:
        publicar.reintentar_transitorio(tabla.update({"numero": plan_tabla["a"]}).eq("numero", plan_tabla["de"]).execute)

    youtube = publicar.get_youtube_client() if any(c.get("youtube_video_id") for c in clips) else None
    errores = 0
    for c in clips:
        publicar.actualizar_clip_supabase(c["id"], {"capitulo": args.numero})
        estado_yt = "sin video"
        if c.get("youtube_video_id"):
            try:
                cambio = _actualizar_youtube(youtube, c["youtube_video_id"], args.numero)
                estado_yt = "descripción actualizada" if cambio else "descripción ya estaba bien"
            except Exception as e:  # noqa: BLE001 - se informa y sigue con los demás
                errores += 1
                estado_yt = f"ERROR: {e}"
        print(f"  {c['id']}: capítulo {args.numero} en Supabase; YouTube: {estado_yt}")

    if errores:
        print(f"{errores} video(s) no se pudieron actualizar en YouTube. Supabase sí quedó corregido; reintenta el comando.")
        return 1
    print("Listo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
