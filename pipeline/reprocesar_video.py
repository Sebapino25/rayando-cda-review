"""Cierra el loop de corrección de in/out points pedida por el equipo
editorial: busca en rayando_cda.clips las filas con
estado='correccion_video', usa la API de Anthropic (interpretar_correccion)
para interpretar comentarios_video contra la transcripción completa del
programa y, si hay confianza, vuelve a cortar el clip (horizontal +
vertical con subtítulos/logo/portada) desde la grabación original con el
nuevo rango, lo sube como nuevo video no listado de YouTube y actualiza la
fila (estado vuelve a 'pendiente').

Nunca adivina: si la interpretación no tiene confianza, o la carpeta local
no se puede correlacionar sin ambigüedad, aborta sin tocar nada. Y si un
paso técnico falla después de haber respaldado la versión anterior, deshace
el respaldo para dejar el clip exactamente como estaba (ver procesar_fila).

Corre en dry-run por defecto. Usa --apply para ejecutar de verdad,
--clip-id para probar (o forzar el reintento) contra un solo clip, y --uno
para procesar solo la fila pendiente más antigua que no haya fallado ya con
el mismo pedido (pensado para el disparador automático, que llama a este
script cada 5 minutos y deja que la siguiente corrida procese el resto).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import config
import cortar_clip
import publicar
from correlacionar_clip import candidata_mas_parecida, encontrar_carpetas_candidatas
from interpretar_correccion import InterpretacionError, interpretar_correccion

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


@dataclass
class DecisionReproceso:
    carpeta: Path | None
    nuevo_inicio: float | None
    nuevo_fin: float | None
    motivo_abort: str | None
    interpretacion_motivo: str = ""


def cargar_segments_de_carpeta(carpeta: Path) -> list[dict] | None:
    """Encuentra la grabación original (metadata.json -> video_fuente) y
    devuelve sus segmentos maestros de transcripción (mismo formato que
    usa detectar_momentos/interpretar_correccion)."""
    import json

    metadata_path = carpeta / "metadata.json"
    if not metadata_path.exists():
        return None
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    video_path = Path(metadata["video_fuente"])
    return cortar_clip.load_master_segments(video_path)


def decidir(row: dict) -> DecisionReproceso:
    """Localiza la carpeta local y determina los nuevos timestamps a
    partir de comentarios_video, SIN tocar ningún archivo. motivo_abort
    distinto de None significa "no continuar, avisar y no tocar nada"."""
    carpetas = encontrar_carpetas_candidatas(row)
    if len(carpetas) == 0:
        pista = candidata_mas_parecida(row)
        extra = f" Candidata más parecida (no usada): {pista[0]} (similitud {pista[1]:.1%})." if pista else ""
        return DecisionReproceso(
            carpeta=None, nuevo_inicio=None, nuevo_fin=None,
            motivo_abort=f"No se encontró ninguna carpeta local para el clip {row.get('id')}.{extra}",
        )
    if len(carpetas) > 1:
        nombres = ", ".join(str(c) for c in carpetas)
        return DecisionReproceso(
            carpeta=None, nuevo_inicio=None, nuevo_fin=None,
            motivo_abort=f"Ambigüedad: {len(carpetas)} carpetas calzan con el clip {row.get('id')}: {nombres}",
        )

    carpeta = carpetas[0]
    segments = cargar_segments_de_carpeta(carpeta)
    if not segments:
        return DecisionReproceso(
            carpeta=carpeta, nuevo_inicio=None, nuevo_fin=None,
            motivo_abort=f"No se pudo cargar la transcripción maestra para {carpeta} (metadata.json/video_fuente).",
        )

    try:
        interpretacion = interpretar_correccion(row.get("comentarios_video") or "", segments)
    except InterpretacionError as e:
        return DecisionReproceso(
            carpeta=carpeta, nuevo_inicio=None, nuevo_fin=None,
            motivo_abort=f"Falló la interpretación del pedido con la API de Anthropic: {e}",
        )

    if not interpretacion.confianza:
        return DecisionReproceso(
            carpeta=carpeta, nuevo_inicio=None, nuevo_fin=None,
            motivo_abort=f"La IA no tiene confianza en el pedido '{row.get('comentarios_video')}': {interpretacion.motivo}",
        )

    return DecisionReproceso(
        carpeta=carpeta,
        nuevo_inicio=interpretacion.timestamp_inicio,
        nuevo_fin=interpretacion.timestamp_fin,
        motivo_abort=None,
        interpretacion_motivo=interpretacion.motivo,
    )


def buscar_pendientes(supabase, clip_id: str | None) -> list[dict]:
    columnas = (
        "id,semana,estado,comentarios_video,transcripcion_original,"
        "titulo,youtube_titulo,youtube_descripcion,youtube_video_id,created_at"
    )
    query = supabase.table(config.SUPABASE_TABLE).select(columnas).eq("estado", "correccion_video")
    if clip_id:
        query = query.eq("id", clip_id)
    filas = query.order("created_at").execute().data
    # Defensivo: el fixture de QA (estado='prueba') nunca debería calzar
    # con este filtro, pero se excluye igual por si queda en un estado raro.
    return [f for f in filas if f.get("estado") != "prueba"]


# --- Marcador de intentos fallidos (para el disparador automático) ---------
#
# Una fila que falla (típicamente: la IA no tiene confianza en el pedido)
# nunca sale de estado='correccion_video', así que sin memoria el loop de
# auto_procesar.ps1 la reintentaría cada 5 minutos para siempre: una llamada
# a Opus con la transcripción completa (~45k tokens de entrada) y un mail de
# alerta por ciclo, ~288 por día, hasta que alguien la arregle a mano. Peor:
# Resend corta alrededor de 100 mails diarios en el plan gratis, así que
# después de eso se pierden TODAS las alertas del pipeline en silencio.
#
# Solución barata (sin migración ni columna nueva en Supabase): después de un
# intento fallido se guarda en logs_auto\ un marcador por clip con el hash de
# comentarios_video. Mientras el texto del pedido NO cambie, esa fila se
# saltea en las corridas con --uno (el disparador automático), así que no se
# vuelve a llamar a la API ni a mandar mail. Si el equipo editorial edita
# comentarios_video, el hash cambia y se reintenta sola. Un intento exitoso
# borra el marcador.
#
# El marcador NO se consulta cuando se pasa --clip-id: eso es una corrida
# manual y siempre tiene que poder forzar el reintento.
LOGS_AUTO_DIR = config.PROJECT_DIR / "logs_auto"
# Extensión .log a propósito: .gitignore ignora *.log, así que este estado
# operativo no se versiona (mismo criterio que el resto de logs_auto\).
MARCADOR_FALLOS_PATH = LOGS_AUTO_DIR / "correccion_video_fallos.log"


def _hash_comentarios(texto: str | None) -> str:
    normalizado = " ".join((texto or "").split())
    return hashlib.sha256(normalizado.encode("utf-8")).hexdigest()[:16]


def _leer_marcadores() -> dict:
    if not MARCADOR_FALLOS_PATH.exists():
        return {}
    try:
        datos = json.loads(MARCADOR_FALLOS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # Marcador corrupto: se trata como vacío (peor caso, se reintenta una
        # vez de más). Nunca debe hacer fallar el procesamiento.
        return {}
    return datos if isinstance(datos, dict) else {}


def _escribir_marcadores(marcadores: dict) -> None:
    try:
        LOGS_AUTO_DIR.mkdir(parents=True, exist_ok=True)
        MARCADOR_FALLOS_PATH.write_text(
            json.dumps(marcadores, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as e:
        # No poder escribir el marcador no debe romper la corrida: solo
        # significa que la próxima va a reintentar.
        print(f"  ADVERTENCIA: no se pudo escribir {MARCADOR_FALLOS_PATH}: {e}")


def fallo_reciente(row: dict) -> bool:
    """True si esta fila ya falló en su último intento con EXACTAMENTE el
    mismo texto de comentarios_video (y por lo tanto no tiene sentido
    reintentarla ni volver a alertar hasta que alguien la cambie)."""
    marcador = _leer_marcadores().get(str(row.get("id")))
    if not marcador:
        return False
    return marcador.get("hash") == _hash_comentarios(row.get("comentarios_video"))


def registrar_fallo(row: dict, motivo: str) -> None:
    """Deja constancia de que esta fila falló con este texto de pedido."""
    marcadores = _leer_marcadores()
    marcadores[str(row.get("id"))] = {
        "hash": _hash_comentarios(row.get("comentarios_video")),
        "comentarios_video": row.get("comentarios_video"),
        "motivo": motivo,
        "cuando": datetime.now(timezone.utc).isoformat(),
    }
    _escribir_marcadores(marcadores)


def limpiar_fallo(row: dict) -> None:
    """Borra el marcador de una fila que se procesó bien."""
    marcadores = _leer_marcadores()
    if marcadores.pop(str(row.get("id")), None) is not None:
        _escribir_marcadores(marcadores)


def seleccionar_para_uno(filas: list[dict]) -> list[dict]:
    """Para --uno: devuelve la fila pendiente más antigua que NO haya fallado
    en su último intento con el mismo texto, o [] si todas fallaron.

    Sin esto, buscar_pendientes ordena por created_at y --uno se queda con
    filas[:1], así que una sola fila trabada (que nunca sale de
    'correccion_video') bloquearía para siempre a todas las demás
    (head-of-line blocking), en silencio."""
    for fila in filas:
        if not fallo_reciente(fila):
            return [fila]
    return []


from correlacionar_clip import respaldar_version_anterior, restaurar_version_respaldada
import portadas


class EjecutarError(Exception):
    """Falló un paso técnico al ejecutar la corrección (recorte, validación o subida)."""


def _titulo_portada_de_copys(carpeta: Path) -> str | None:
    """Lee el título de portada ORIGINAL desde copys.md (línea `**Portada:**
    ...`), el mismo archivo que escribió cortar_clip.build_copys() al cortar
    el clip por primera vez. Los copys curados no se regeneran en una
    corrección de video (solo cambia el rango de tiempo), así que este es el
    título correcto a reusar — evita depender de clip_overrides.json, que
    para la mayoría de los clips NO tiene una entrada titulo_portada (ver
    docs de clip_overrides.json), lo cual dejaría titulo_portada en None y
    hacía fallar portadas.build_portadas() para el caso común. Devuelve None
    si copys.md no existe o no tiene la línea esperada (fallback al llamador)."""
    copys_path = carpeta / "copys.md"
    if not copys_path.exists():
        return None
    match = re.search(r"\*\*Portada:\*\*\s*(.+)", copys_path.read_text(encoding="utf-8"))
    return match.group(1).strip() if match else None


def _ejecutar_recorte(carpeta: Path, video_path: Path, nuevo_inicio: float, nuevo_fin: float, nombre_clip: str):
    """Re-corta horizontal+vertical (subtítulos/logo/portada) con el nuevo
    rango, reusando las funciones de cortar_clip.py. Devuelve
    (vertical_path, transcripcion_texto)."""
    horizontal_path = carpeta / "horizontal_original.mp4"
    try:
        _method, actual_start, _actual_end = cortar_clip.cut_horizontal(
            video_path, nuevo_inicio, nuevo_fin, horizontal_path
        )
    except Exception as e:
        raise EjecutarError(f"Falló el recorte horizontal: {e}") from e

    # cut_horizontal agrega un margen de aire (config.CLIP_PAD_SECONDS) antes
    # del inicio pedido, así que el video ahora arranca en actual_start, no en
    # nuevo_inicio. Sin este ajuste los subtítulos quedarían desincronizados
    # hasta CLIP_PAD_SECONDS (mismo cálculo que cortar_clip.cortar_y_publicar).
    pad_offset = nuevo_inicio - actual_start

    segments = cortar_clip.load_master_segments(video_path)
    clipped = cortar_clip.clip_segments(segments, nuevo_inicio, nuevo_fin) if segments else []
    if pad_offset and clipped:
        clipped = [(cs + pad_offset, ce + pad_offset, text) for cs, ce, text in clipped]
    has_subtitles = bool(clipped)
    if has_subtitles:
        captions = cortar_clip.split_into_captions(clipped)
        cortar_clip.build_clip_srt(captions, carpeta / "subtitulos.srt")
        cortar_clip.build_clip_ass(captions, carpeta / "subtitulos.ass")

    overrides = cortar_clip._cargar_overrides(nombre_clip)
    titulo_portada = _titulo_portada_de_copys(carpeta) or overrides.get("titulo_portada")
    try:
        cortar_clip.build_vertical(carpeta, has_subtitles, titulo_portada)
    except Exception as e:
        raise EjecutarError(f"Falló la generación del vertical: {e}") from e

    try:
        portadas.build_portadas(carpeta, horizontal_path, titulo_portada, overrides)
    except Exception as e:
        raise EjecutarError(f"Falló la generación de la portada: {e}") from e

    vertical_path = carpeta / "vertical.mp4"
    try:
        publicar.validar_clip(vertical_path)
    except publicar.ClipInvalido as e:
        raise EjecutarError(f"El vertical.mp4 recién generado no pasó la validación técnica: {e}") from e

    transcripcion_texto = cortar_clip.join_transcripcion(clipped)
    return vertical_path, transcripcion_texto


def procesar_fila(row: dict, apply: bool) -> bool:
    """Procesa una fila estado='correccion_video'. Devuelve True si se
    corrigió con éxito (o si en dry-run no hubiera nada que abortar),
    False si abortó o falló un paso técnico."""
    clip_id = row["id"]
    print(f"\n=== Clip {clip_id} (semana {row.get('semana')}) ===")
    print(f"  Pedido: {row.get('comentarios_video')!r}")

    decision = decidir(row)
    if decision.motivo_abort:
        print(f"  ABORTADO: {decision.motivo_abort} (no se tocó ningún archivo)")
        if apply:
            # Marcador: no reintentar ni volver a alertar por este mismo
            # pedido en cada corrida del disparador automático (ver
            # fallo_reciente). En dry-run no se escribe nada.
            registrar_fallo(row, decision.motivo_abort)
        return False

    print(f"  Carpeta local: {decision.carpeta}")
    print(f"  Nuevo rango: {cortar_clip.format_hhmmss(decision.nuevo_inicio)} -> {cortar_clip.format_hhmmss(decision.nuevo_fin)}")
    print(f"  Interpretación: {decision.interpretacion_motivo}")

    if not apply:
        print("  [dry-run] Se respaldaría la versión anterior, se re-cortaría con este rango, "
              "se subiría un video nuevo a YouTube y se actualizaría la fila a estado='pendiente'.")
        return True

    metadata_path = decision.carpeta / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    video_path = Path(metadata["video_fuente"])
    nombre_clip = decision.carpeta.name
    program_date = cortar_clip.program_date_from_name(video_path)

    print("  Respaldando versión anterior (vertical.mp4 + horizontal_original.mp4 + subtítulos) en vN\\...")
    destino_backup = respaldar_version_anterior(decision.carpeta)
    print(f"    Respaldado en: {destino_backup}")

    # A partir de acá la carpeta está "a medio camino": el respaldo ya se
    # llevó el subtitulos.srt viejo y el recorte va a escribir uno nuevo, pero
    # la fila de Supabase sigue con el transcripcion_original VIEJO. Como la
    # correlación fila<->carpeta se hace justamente comparando esos dos textos
    # (ver correlacionar_clip.encontrar_carpetas_candidatas), si algo falla en
    # el medio y no se deshace, la carpeta queda imposible de encontrar para
    # siempre: el reintento de dentro de 5 minutos abortaría con "no se
    # encontró ninguna carpeta" en vez del error real, y lo mismo le pasaría a
    # reprocesar_subtitulos.py. Por eso todo el tramo recorte -> subidas ->
    # update de Supabase va dentro de un try/finally que restaura el respaldo
    # ante CUALQUIER falla. Solo se marca exito=True cuando el update de
    # Supabase ya pasó, que es el momento en que la fila y la carpeta vuelven
    # a estar sincronizadas.
    exito = False
    try:
        try:
            vertical_path, transcripcion_texto = _ejecutar_recorte(
                decision.carpeta, video_path, decision.nuevo_inicio, decision.nuevo_fin, nombre_clip
            )
        except EjecutarError as e:
            print(f"  FALLÓ: {e}")
            return False

        titulo = row.get("titulo") or "Rayando el CDA"
        descripcion = f"{row.get('youtube_titulo') or ''}\n\n{row.get('youtube_descripcion') or ''}".strip()
        print(f'  Subiendo a YouTube como no listado: "{titulo}"...')
        try:
            nuevo_video_id = publicar.subir_youtube(vertical_path, titulo, descripcion=descripcion)
        except Exception as e:
            print(f"  FALLÓ la subida a YouTube: {e}")
            return False
        nueva_url = f"https://youtu.be/{nuevo_video_id}"
        print(f"  Subido: {nueva_url}")

        portada_storage_path = f"{program_date}/{nombre_clip}.jpg"
        try:
            publicar.subir_portada_storage(decision.carpeta / "portada_vertical.jpg", portada_storage_path)
        except Exception as e:
            print(f"  ADVERTENCIA: no se pudo re-subir la portada a Storage ({e}). portada_url queda con la imagen anterior.")

        video_storage_path = f"{program_date}/{nombre_clip}.mp4"
        try:
            publicar.subir_video_storage(vertical_path, video_storage_path)
        except Exception as e:
            print(f"  FALLÓ la re-subida del video a Storage: {e}")
            return False

        print("  Actualizando Supabase (estado -> pendiente, nuevos timestamps, youtube_video_id)...")
        try:
            publicar.actualizar_clip_supabase(
                clip_id,
                {
                    "youtube_video_id": nuevo_video_id,
                    "timestamp_inicio": decision.nuevo_inicio,
                    "timestamp_fin": decision.nuevo_fin,
                    "transcripcion": transcripcion_texto,
                    "transcripcion_original": transcripcion_texto,
                    "estado": "pendiente",
                    "revisado_por": None,
                    "revisado_en": None,
                },
            )
        except Exception as e:
            print(f"  FALLÓ la actualización de Supabase: {e}")
            return False

        # Desde acá la fila ya apunta a la nueva transcripción: la carpeta
        # nueva es la correcta y NO hay que restaurar nada.
        exito = True
    finally:
        if not exito:
            print(f"  Restaurando la versión anterior desde {destino_backup} (el clip queda como estaba)...")
            try:
                restaurar_version_respaldada(decision.carpeta, destino_backup)
                print("    Restaurado. La fila de Supabase no se tocó.")
            except Exception as e:
                print(f"    ERROR al restaurar: {e}. REVISAR A MANO: la carpeta "
                      f"{decision.carpeta} puede haber quedado inconsistente con Supabase.")
            registrar_fallo(row, "Falló un paso técnico del reproceso (ver el log de esta corrida).")

    video_id_anterior = row.get("youtube_video_id")
    resumen_extra = (
        "\n--- Reproceso de video (corrección de in/out) ---\n"
        f"Pedido: {row.get('comentarios_video')}\n"
        f"Nuevo rango: {cortar_clip.format_hhmmss(decision.nuevo_inicio)} -> {cortar_clip.format_hhmmss(decision.nuevo_fin)}\n"
        f"YouTube video ID anterior: {video_id_anterior}\n"
        f"YouTube video ID nuevo: {nuevo_video_id}\n"
        f"YouTube URL nueva: {nueva_url}\n"
    )
    with (decision.carpeta / "resumen.txt").open("a", encoding="utf-8") as f:
        f.write(resumen_extra)

    limpiar_fallo(row)
    print(f"  Listo. Clip vuelve a 'pendiente' para revisión. youtube_video_id: {video_id_anterior} -> {nuevo_video_id}")
    print(f"  NOTA: el video anterior ({video_id_anterior}) sigue en YouTube como no listado; bórralo a mano si ya no sirve.")
    return True


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Busca clips en estado='correccion_video', interpreta el pedido de "
            "comentarios_video con IA y, si hay confianza, vuelve a cortar el clip "
            "con el nuevo in/out y lo sube de nuevo. Nunca adivina: si algo es "
            "ambiguo o de baja confianza, aborta esa fila sin tocar nada."
        )
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Ejecuta de verdad. Sin este flag corre en dry-run (solo muestra qué haría).",
    )
    parser.add_argument(
        "--clip-id", default=None,
        help="Procesa solo este id de rayando_cda.clips (para probar contra un solo clip).",
    )
    parser.add_argument(
        "--uno", action="store_true",
        help="Procesa solo la fila pendiente más antigua que no haya fallado ya con el "
             "mismo texto de comentarios_video (pensado para el disparador automático: "
             "deja que la siguiente corrida procese el resto). Usa --clip-id para forzar "
             "el reintento de una fila que ya falló.",
    )
    args = parser.parse_args()

    supabase = publicar.get_supabase_client()
    filas = buscar_pendientes(supabase, args.clip_id)

    if not filas:
        if args.clip_id:
            print(f"El clip {args.clip_id} no está en estado='correccion_video'.")
        else:
            print("No hay clips pendientes de corrección de video.")
        sys.exit(0)

    if args.uno and not args.clip_id:
        # Saltea las filas que ya fallaron con este mismo pedido: si no, la
        # más antigua trabada bloquearía a todas las demás para siempre
        # (buscar_pendientes ordena por created_at y una fila que falla nunca
        # sale de 'correccion_video'). Que TODAS estén marcadas no es un error
        # nuevo: es lo mismo que "no hay nada pendiente" (salida 0, sin mail).
        pendientes = filas
        filas = seleccionar_para_uno(filas)
        if not filas:
            print(f"Las {len(pendientes)} fila(s) pendiente(s) de corrección ya fallaron con "
                  f"el mismo texto de comentarios_video; no se reintentan hasta que cambie "
                  f"el pedido (marcadores en {MARCADOR_FALLOS_PATH}).")
            sys.exit(0)

    print(f"{'[APPLY]' if args.apply else '[DRY-RUN]'} {len(filas)} clip(s) pendiente(s) de corrección.")
    resultados = [procesar_fila(row, apply=args.apply) for row in filas]

    if all(resultados):
        sys.exit(3 if args.apply else 0)
    sys.exit(1)


if __name__ == "__main__":
    main()
