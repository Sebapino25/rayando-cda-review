"""Detecta candidatos a clip a partir de la transcripción completa de un
programa, usando la API de Anthropic (ver copys_ia.py y publicar.py para
los otros usos de la API en este pipeline).

Prioriza, en este orden: humor, declaraciones fuertes sobre la U/la
dirigencia, momentos con carga emocional real — mismo criterio editorial
usado como referencia original del proyecto.

Los timestamps de cada candidato SIEMPRE calzan con el inicio/fin de un
segmento real de la transcripción de Whisper — nunca son un segundo
arbitrario. El modelo elige rangos de ÍNDICE sobre la lista numerada de
segmentos que le pasamos; acá calculamos el timestamp real a partir de
esos índices, así el corte nunca puede caer a mitad de un segmento.
Además marcamos qué segmentos abren/cierran oración (terminan en
".", "!", "?" o "…") y le pedimos al modelo que prefiera esos como
inicio/fin — no es una garantía absoluta de "nunca a mitad de frase"
(Whisper a veces parte una misma oración en dos segmentos), pero es la
mejor aproximación mecánica disponible sobre los segmentos reales.

Modo de prueba: correr este archivo directo (`python detectar_momentos.py
<video>`) solo detecta e imprime los candidatos en consola — no corta ni
sube nada. La orquestación automática (cortar + subir + Supabase) es un
script aparte que importa detectar_candidatos() y reusa cortar_clip.py /
publicar.py.

Requiere ANTHROPIC_API_KEY en el .env.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from dotenv import load_dotenv

import config

load_dotenv(config.PROJECT_DIR / ".env")

_FIN_ORACION_RE = re.compile(r"[.!?…]\s*$")

SYSTEM_PROMPT = """Sos el/la encargado/a editorial de detectar los mejores \
momentos para cortar clips de "Rayando el CDA", programa semanal de \
hinchas de Universidad de Chile (la U), hecho por 3 personas: un \
periodista, un editor y una persona a cargo de estrategia/producción. \
Identidad "Orozquista": crítico de la dirigencia actual del club, no \
oficialista. Tono cercano, chileno, directo.

Te paso la transcripción completa de un programa, como una lista numerada \
de segmentos (cada uno con su índice, tiempo de inicio/fin en segundos, si \
abre y si cierra oración, y el texto). Identificá entre 5 y 8 candidatos a \
clip para redes sociales, priorizando en este orden de criterio:
1. Humor (talles, chascarros, momentos graciosos del panel).
2. Declaraciones fuertes sobre la U o la dirigencia actual (crítica, \
polémica, contundente).
3. Momentos con carga emocional real (una historia personal, una \
confesión, algo que emocione).

Para cada candidato, elegí un rango contiguo de índices [idx_inicio, \
idx_fin] de la lista que te paso (inclusive en ambos extremos) — NUNCA \
inventes un timestamp en segundos. El clip debe durar entre 20 y 90 \
segundos (fin del segmento idx_fin menos inicio del segmento idx_inicio). \
Preferí que idx_inicio sea un segmento con empieza_oracion=true e idx_fin \
uno con termina_oracion=true, para no cortar a mitad de una frase — si el \
mejor momento no calza exacto, elegí el índice más cercano que sí cumpla \
esto, no fuerces un corte a mitad de oración.

Para cada candidato devolvé: idx_inicio, idx_fin y razon (por qué elegiste \
justo ese momento, en 1-2 frases, específico al contenido — nunca \
genérico, tipo "es un buen momento").

No elijas candidatos que se superpongan entre sí (rangos de índices \
disjuntos). Priorizá variedad: no repitas el mismo tema/persona en todos \
los candidatos si el programa da para más variedad."""

if config.PROMPT_DETECCION:
    # Prompt propio del programa (config.PROGRAMA != "rayando"). Los límites
    # salen de config para que nunca se desfasen del filtro de duración.
    SYSTEM_PROMPT = config.PROMPT_DETECCION.format(
        min_n=config.CANDIDATOS_MIN_N,
        max_n=config.CANDIDATOS_MAX_N,
        dur_min=int(config.CANDIDATOS_DURACION_MIN),
        dur_max=int(config.REEL_MAX_SECONDS),
    )

_SCHEMA = {
    "type": "object",
    "properties": {
        "candidatos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "idx_inicio": {"type": "integer"},
                    "idx_fin": {"type": "integer"},
                    "razon": {"type": "string"},
                },
                "required": ["idx_inicio", "idx_fin", "razon"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["candidatos"],
    "additionalProperties": False,
}


def _schema_con_puntaje() -> dict:
    """Mismo esquema, con `puntaje` (1-10) obligatorio: se usa en la detección
    por ventanas para ordenar candidatos de distintas partes del programa."""
    sch = json.loads(json.dumps(_SCHEMA))
    item = sch["properties"]["candidatos"]["items"]
    item["properties"]["puntaje"] = {"type": "integer"}
    item["required"] = ["idx_inicio", "idx_fin", "razon", "puntaje"]
    return sch


@dataclass
class Candidato:
    idx_inicio: int
    idx_fin: int
    timestamp_inicio: float
    timestamp_fin: float
    duracion_segundos: float
    razon: str
    transcripcion: str
    puntaje: int | None = None  # solo en detección por ventanas (1-10)


class DeteccionError(Exception):
    """La detección de momentos con la API de Anthropic falló."""


def _client():
    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise DeteccionError("Falta la variable de entorno ANTHROPIC_API_KEY (revisa tu .env)")
    return anthropic.Anthropic(api_key=api_key)


def _termina_oracion(texto: str) -> bool:
    return bool(_FIN_ORACION_RE.search(texto.strip()))


def _construir_lista_segmentos(segments: list[dict], desde: int = 0, hasta: int | None = None) -> str:
    """Lista numerada de segmentos. Los índices son SIEMPRE los del programa
    completo, aunque se pase solo un rango [desde, hasta) (detección por
    ventanas)."""
    hasta = len(segments) if hasta is None else hasta
    lineas = []
    # idx 0 siempre puede abrir oración; en una ventana, depende del anterior
    termina_anterior = True if desde == 0 else _termina_oracion(segments[desde - 1]["text"])
    for i in range(desde, hasta):
        seg = segments[i]
        texto = seg["text"].strip()
        empieza = termina_anterior
        termina = _termina_oracion(texto)
        lineas.append(
            f"[{i}] ({seg['start']:.1f}-{seg['end']:.1f}s, "
            f"empieza_oracion={str(empieza).lower()}, "
            f"termina_oracion={str(termina).lower()}) {texto}"
        )
        termina_anterior = termina
    return "\n".join(lineas)


def _llamar_modelo(system: str, mensaje_usuario: str, schema: dict) -> list[dict]:
    """Una llamada a la API; devuelve la lista cruda de candidatos del modelo."""
    client = _client()
    try:
        with client.messages.stream(
            model=config.CANDIDATOS_MODEL,
            max_tokens=16000,
            thinking={"type": "adaptive"},
            system=system,
            output_config={"format": {"type": "json_schema", "schema": schema}},
            messages=[{"role": "user", "content": mensaje_usuario}],
        ) as stream:
            response = stream.get_final_message()
    except Exception as e:
        raise DeteccionError(f"Llamada a la API de Anthropic falló: {e}") from e

    if response.stop_reason == "refusal":
        raise DeteccionError("La API de Anthropic rechazó la solicitud (stop_reason=refusal)")

    try:
        texto = next(b.text for b in response.content if b.type == "text")
        return json.loads(texto)["candidatos"]
    except (StopIteration, json.JSONDecodeError, KeyError, TypeError) as e:
        raise DeteccionError(f"Respuesta de la API no tiene el formato esperado: {e}") from e


def _validar_candidatos(
    crudos: list[dict],
    segments: list[dict],
    rangos_aceptados: list[tuple[int, int]] | None = None,
    i_min: int = 0,
    i_max: int | None = None,
) -> list[Candidato]:
    """Valida los candidatos crudos del modelo (índices, solapamiento,
    duración) y arma los Candidato con timestamps y transcripción reales.
    i_min/i_max acotan los índices permitidos (ventana)."""
    n = len(segments)
    i_max = n - 1 if i_max is None else i_max
    rangos_aceptados = [] if rangos_aceptados is None else rangos_aceptados
    aceptados: list[Candidato] = []

    for c in crudos:
        idx_inicio, idx_fin = c.get("idx_inicio"), c.get("idx_fin")
        if not isinstance(idx_inicio, int) or not isinstance(idx_fin, int):
            continue
        if not (i_min <= idx_inicio <= idx_fin <= i_max):
            continue  # índice inválido (o fuera de la ventana), se descarta

        solapa = any(not (idx_fin < a_ini or idx_inicio > a_fin) for a_ini, a_fin in rangos_aceptados)
        if solapa:
            continue  # candidato superpuesto con uno ya aceptado, se descarta

        ts_inicio = segments[idx_inicio]["start"]
        ts_fin = segments[idx_fin]["end"]
        duracion = ts_fin - ts_inicio
        if not (config.CANDIDATOS_DURACION_MIN <= duracion <= config.REEL_MAX_SECONDS):
            continue  # fuera del rango de duración pedido, se descarta

        # La transcripción se arma acá a partir de los segmentos reales, no
        # se le pide al modelo que la copie — así no hay riesgo de que la
        # parafrasee o la altere.
        transcripcion = " ".join(
            segments[i]["text"].strip() for i in range(idx_inicio, idx_fin + 1)
        )
        puntaje = c.get("puntaje")

        aceptados.append(
            Candidato(
                idx_inicio=idx_inicio,
                idx_fin=idx_fin,
                timestamp_inicio=ts_inicio,
                timestamp_fin=ts_fin,
                duracion_segundos=round(duracion, 2),
                razon=c.get("razon", ""),
                transcripcion=transcripcion,
                puntaje=puntaje if isinstance(puntaje, int) else None,
            )
        )
        rangos_aceptados.append((idx_inicio, idx_fin))

    return aceptados


def _ventanas(segments: list[dict], ventana_seg: float, solape_seg: float) -> list[tuple[int, int]]:
    """Parte el programa en ventanas de ~ventana_seg segundos, cada una con
    solape_seg de más al final (para no cortar un momento justo en el borde).
    Devuelve rangos de índice [i0, i1) sobre `segments`. Una cola muy corta
    (menos de un tercio de ventana) se une a la ventana anterior."""
    n = len(segments)
    if n == 0 or not ventana_seg or ventana_seg <= 0:
        return [(0, n)]
    fin_total = segments[-1]["end"]
    inicios: list[float] = []
    t = 0.0
    while t < fin_total:
        inicios.append(t)
        t += ventana_seg
    if len(inicios) > 1 and fin_total - inicios[-1] < ventana_seg / 3:
        inicios.pop()

    def primer_indice(desde_seg: float) -> int:
        for i, seg in enumerate(segments):
            if seg["start"] >= desde_seg:
                return i
        return n

    ventanas: list[tuple[int, int]] = []
    for k, t0 in enumerate(inicios):
        ultima = k == len(inicios) - 1
        i0 = primer_indice(t0)
        i1 = n if ultima else primer_indice(t0 + ventana_seg + solape_seg)
        if i1 > i0:
            ventanas.append((i0, i1))
    return ventanas


def _combinar_ventanas(por_ventana: list[list[Candidato]], pool_n: int) -> list[Candidato]:
    """Junta los candidatos de todas las ventanas: ordena por puntaje (a igual
    puntaje, el que aparece antes en el programa), descarta los que se
    superponen con uno mejor ya elegido (típico del solape entre ventanas),
    se queda con los pool_n mejores y los devuelve en orden cronológico."""
    todos = [c for lista in por_ventana for c in lista]
    todos.sort(key=lambda c: (-(c.puntaje or 0), c.timestamp_inicio))
    elegidos: list[Candidato] = []
    for c in todos:
        if any(not (c.idx_fin < e.idx_inicio or c.idx_inicio > e.idx_fin) for e in elegidos):
            continue
        elegidos.append(c)
        if len(elegidos) >= pool_n:
            break
    elegidos.sort(key=lambda c: c.timestamp_inicio)
    return elegidos


def _hhmm(segundos: float) -> str:
    s = int(segundos)
    return f"{s // 3600}:{(s % 3600) // 60:02d}"


_NOTA_VENTANA = (
    "\n\nNOTA: en esta llamada recibís solo una parte del programa. Los topes de "
    "cantidad se aplican a esta parte; la selección final entre las partes se hace "
    "después, según el puntaje que le des a cada candidato."
)


def _detectar_por_ventanas(segments: list[dict]) -> list[Candidato]:
    """Detección por ventanas: una llamada por cada ~15 minutos de programa
    (en paralelo), cada una con puntaje, y una selección final entre todas.
    Evita que un modelo que lee una hora de transcripción de una vez pase por
    alto tramos enteros. Solo con prompt propio del programa."""
    ventanas = _ventanas(segments, config.DETECCION_VENTANA_SEG, config.DETECCION_VENTANA_SOLAPE_SEG)
    por_ventana_max = max(1, int(config.DETECCION_POR_VENTANA_MAX))
    pool_n = int(config.CANDIDATOS_POOL_N or config.CANDIDATOS_MAX_N)
    system = (
        config.PROMPT_DETECCION.format(
            min_n=0,
            max_n=por_ventana_max,
            dur_min=int(config.CANDIDATOS_DURACION_MIN),
            dur_max=int(config.REEL_MAX_SECONDS),
        )
        + _NOTA_VENTANA
    )
    schema = _schema_con_puntaje()
    total = len(ventanas)

    def tarea(k: int) -> list[Candidato]:
        i0, i1 = ventanas[k]
        lista = _construir_lista_segmentos(segments, i0, i1)
        mensaje = (
            f"Parte {k + 1} de {total} del programa "
            f"(de {_hhmm(segments[i0]['start'])} a {_hhmm(segments[i1 - 1]['end'])}). "
            "Los índices de la lista son los del programa completo: elegí índices solo de esta parte. "
            f"Devolvé hasta {por_ventana_max} candidatos de esta parte; si no hay momentos realmente "
            "buenos, devolvé menos o ninguno. Para cada candidato agregá además puntaje (entero de 1 a 10): "
            "qué tan buen clip es, juzgado contra los mejores clips que esperarías de un programa de "
            "reacción de humor. 9-10 imperdible, 7-8 muy bueno, 5-6 aceptable, 4 o menos flojo. Sé exigente "
            "y consistente: el puntaje se usa para comparar candidatos de distintas partes del programa.\n\n"
            f"Transcripción de esta parte ({i1 - i0} segmentos):\n\n{lista}"
        )
        crudos = _llamar_modelo(system, mensaje, schema)
        return _validar_candidatos(crudos, segments, None, i0, i1 - 1)

    with ThreadPoolExecutor(max_workers=total) as ex:
        por_ventana = list(ex.map(tarea, range(total)))

    elegidos = _combinar_ventanas(por_ventana, pool_n)
    if not elegidos:
        raise DeteccionError(
            "La API no devolvió ningún candidato válido en ninguna parte del programa "
            "(0 después de validar índices/duración/solapamiento)"
        )
    return elegidos


def detectar_candidatos(segments: list[dict]) -> list[Candidato]:
    """Llama a la API de Anthropic para identificar entre
    config.CANDIDATOS_MIN_N y config.CANDIDATOS_MAX_N candidatos a clip
    sobre la transcripción completa (segments = data["segments"] del .json
    maestro de transcribir.py). Lanza DeteccionError si falla la llamada o
    la respuesta no es utilizable.

    Si el programa define config.DETECCION_VENTANA_SEG > 0 (y tiene prompt
    propio), se usa la detección por ventanas (ver _detectar_por_ventanas)."""
    if not segments:
        raise DeteccionError("La transcripción no tiene segmentos")

    if config.DETECCION_VENTANA_SEG and config.DETECCION_VENTANA_SEG > 0 and config.PROMPT_DETECCION:
        return _detectar_por_ventanas(segments)

    lista = _construir_lista_segmentos(segments)
    mensaje_usuario = f"Transcripción completa del programa ({len(segments)} segmentos):\n\n{lista}"

    crudos = _llamar_modelo(SYSTEM_PROMPT, mensaje_usuario, _SCHEMA)
    aceptados = _validar_candidatos(crudos, segments)

    if not aceptados:
        raise DeteccionError(
            "La API no devolvió ningún candidato válido (0 después de validar índices/duración/solapamiento)"
        )

    return aceptados


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Detecta candidatos a clip a partir de la transcripción completa de una "
            "grabación (modo de prueba: solo imprime, no corta ni sube nada)."
        )
    )
    parser.add_argument("video", help="Nombre en 'grabaciones' o ruta absoluta del video")
    args = parser.parse_args()

    import cortar_clip  # reusa resolve_video / load_master_segments / format_hhmmss

    video_path = cortar_clip.resolve_video(args.video)
    segments = cortar_clip.load_master_segments(video_path)
    if segments is None:
        sys.exit(
            f"No se encontró transcripción para '{video_path.name}' en "
            f"{config.TRANSCRIPTS_DIR / video_path.stem}. Corré transcribir.py primero."
        )

    print(f"Analizando {len(segments)} segmentos de '{video_path.name}' con {config.CANDIDATOS_MODEL}...")
    try:
        candidatos = detectar_candidatos(segments)
    except DeteccionError as e:
        sys.exit(f"Error detectando candidatos: {e}")

    print(f"\n{len(candidatos)} candidatos detectados:\n")
    for i, c in enumerate(candidatos, start=1):
        print(f"--- Candidato {i} (candidato-{i:02d}) ---")
        print(
            f"  Timestamps: {cortar_clip.format_hhmmss(c.timestamp_inicio)} -> "
            f"{cortar_clip.format_hhmmss(c.timestamp_fin)} ({c.duracion_segundos}s)"
        )
        if c.puntaje is not None:
            print(f"  Puntaje: {c.puntaje}/10")
        print(f"  Razón: {c.razon}")
        print(f"  Transcripción: {c.transcripcion}")
        print()


if __name__ == "__main__":
    main()
