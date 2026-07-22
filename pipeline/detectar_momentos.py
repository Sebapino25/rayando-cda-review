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


@dataclass
class Candidato:
    idx_inicio: int
    idx_fin: int
    timestamp_inicio: float
    timestamp_fin: float
    duracion_segundos: float
    razon: str
    transcripcion: str


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


def _construir_lista_segmentos(segments: list[dict]) -> str:
    lineas = []
    termina_anterior = True  # idx 0 siempre puede abrir oración
    for i, seg in enumerate(segments):
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


def detectar_candidatos(segments: list[dict]) -> list[Candidato]:
    """Llama a la API de Anthropic para identificar entre
    config.CANDIDATOS_MIN_N y config.CANDIDATOS_MAX_N candidatos a clip
    sobre la transcripción completa (segments = data["segments"] del .json
    maestro de transcribir.py). Lanza DeteccionError si falla la llamada o
    la respuesta no es utilizable."""
    if not segments:
        raise DeteccionError("La transcripción no tiene segmentos")

    lista = _construir_lista_segmentos(segments)
    mensaje_usuario = f"Transcripción completa del programa ({len(segments)} segmentos):\n\n{lista}"

    client = _client()
    try:
        with client.messages.stream(
            model=config.CANDIDATOS_MODEL,
            max_tokens=16000,
            thinking={"type": "adaptive"},
            system=SYSTEM_PROMPT,
            output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
            messages=[{"role": "user", "content": mensaje_usuario}],
        ) as stream:
            response = stream.get_final_message()
    except Exception as e:
        raise DeteccionError(f"Llamada a la API de Anthropic falló: {e}") from e

    if response.stop_reason == "refusal":
        raise DeteccionError("La API de Anthropic rechazó la solicitud (stop_reason=refusal)")

    try:
        texto = next(b.text for b in response.content if b.type == "text")
        crudos = json.loads(texto)["candidatos"]
    except (StopIteration, json.JSONDecodeError, KeyError, TypeError) as e:
        raise DeteccionError(f"Respuesta de la API no tiene el formato esperado: {e}") from e

    n = len(segments)
    aceptados: list[Candidato] = []
    rangos_aceptados: list[tuple[int, int]] = []

    for c in crudos:
        idx_inicio, idx_fin = c.get("idx_inicio"), c.get("idx_fin")
        if not isinstance(idx_inicio, int) or not isinstance(idx_fin, int):
            continue
        if not (0 <= idx_inicio <= idx_fin < n):
            continue  # índice inválido devuelto por el modelo, se descarta

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

        aceptados.append(
            Candidato(
                idx_inicio=idx_inicio,
                idx_fin=idx_fin,
                timestamp_inicio=ts_inicio,
                timestamp_fin=ts_fin,
                duracion_segundos=round(duracion, 2),
                razon=c.get("razon", ""),
                transcripcion=transcripcion,
            )
        )
        rangos_aceptados.append((idx_inicio, idx_fin))

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
        print(f"  Razón: {c.razon}")
        print(f"  Transcripción: {c.transcripcion}")
        print()


if __name__ == "__main__":
    main()
