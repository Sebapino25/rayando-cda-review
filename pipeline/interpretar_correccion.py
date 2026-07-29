"""Interpreta un pedido en texto libre de corrección de in/out point
(comentarios_video de una fila en estado='correccion_video') contra la
transcripción completa del programa, usando la API de Anthropic — mismo
patrón de llamada que detectar_momentos.py/copys_ia.py.

Los nuevos timestamps SIEMPRE calzan con el inicio/fin de un segmento
real de la transcripción (mismo principio que detectar_momentos.py): el
modelo elige índices sobre la lista numerada de segmentos, nunca
timestamps libres en segundos.

Si el pedido es ambiguo, la frase referenciada no aparece en la
transcripción, o el modelo devuelve índices inválidos, el resultado
tiene confianza=False y timestamp_inicio/timestamp_fin quedan en None —
quien llama nunca debe adivinar en ese caso.

Requiere ANTHROPIC_API_KEY en el .env.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from dotenv import load_dotenv

import config
from detectar_momentos import _construir_lista_segmentos

load_dotenv(config.PROJECT_DIR / ".env")

# Mismo modelo que detectar_momentos.py: es juicio editorial sobre texto
# libre + transcripción completa, corre sin supervisión, el costo es
# marginal frente al riesgo de una mala interpretación.
MODEL = config.CANDIDATOS_MODEL

SYSTEM_PROMPT = """Sos el/la encargado/a técnico/a de interpretar pedidos \
de corrección de in/out point para clips de "Rayando el CDA". El equipo \
editorial ya revisó un clip y pidió un cambio de corte en texto libre \
(ej. "empezá 2 segundos antes", "cortá antes de que diga tal frase", \
"terminá cuando dice tal otra cosa").

Te paso ese pedido y la transcripción completa del programa como una \
lista numerada de segmentos (cada uno con su índice, tiempo de inicio/fin \
en segundos, si abre y si cierra oración, y el texto).

Tu tarea: identificar el nuevo idx_inicio e idx_fin (índices de esa \
lista, inclusive en ambos extremos) que corresponden al pedido. NUNCA \
inventes un timestamp en segundos — siempre elegí índices reales de la \
lista.

Si el pedido es claro y la frase/momento referenciado existe en la \
transcripción, devolvé confianza=true con los índices elegidos y un \
motivo breve (1 frase) de qué interpretaste. Si el pedido es ambiguo, \
referencia algo que no aparece en la transcripción, o no podés \
determinar con seguridad razonable qué rango corresponde, devolvé \
confianza=false con un motivo específico de por qué no pudiste — NUNCA \
adivines un rango "aproximado" cuando no estás seguro. Ante la duda, \
preferí confianza=false: alguien va a revisar tu respuesta a mano en ese \
caso, así que es preferible que no adivines a que cortes mal un video \
que después se publica."""

_SCHEMA = {
    "type": "object",
    "properties": {
        "confianza": {"type": "boolean"},
        "idx_inicio": {"type": "integer"},
        "idx_fin": {"type": "integer"},
        "motivo": {"type": "string"},
    },
    "required": ["confianza", "idx_inicio", "idx_fin", "motivo"],
    "additionalProperties": False,
}


@dataclass
class InterpretacionCorreccion:
    confianza: bool
    timestamp_inicio: float | None
    timestamp_fin: float | None
    motivo: str


class InterpretacionError(Exception):
    """La interpretación del pedido de corrección con la API de Anthropic falló."""


def _client():
    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise InterpretacionError("Falta la variable de entorno ANTHROPIC_API_KEY (revisa tu .env)")
    return anthropic.Anthropic(api_key=api_key)


def interpretar_correccion(comentarios_video: str, segments: list[dict]) -> InterpretacionCorreccion:
    """Interpreta comentarios_video contra segments (data["segments"] del
    .json maestro de transcribir.py) y devuelve los nuevos timestamps, o
    confianza=False si no se puede determinar con seguridad. Lanza
    InterpretacionError si falla la llamada a la API o la respuesta no es
    utilizable (a diferencia de confianza=False, que es una respuesta
    válida del modelo diciendo "no sé")."""
    if not segments:
        raise InterpretacionError("La transcripción no tiene segmentos")

    lista = _construir_lista_segmentos(segments)
    mensaje_usuario = (
        f"Pedido de corrección: {comentarios_video}\n\n"
        f"Transcripción completa del programa ({len(segments)} segmentos):\n\n{lista}"
    )

    client = _client()
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            thinking={"type": "adaptive"},
            system=SYSTEM_PROMPT,
            output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
            messages=[{"role": "user", "content": mensaje_usuario}],
        )
    except Exception as e:
        raise InterpretacionError(f"Llamada a la API de Anthropic falló: {e}") from e

    if response.stop_reason == "refusal":
        raise InterpretacionError("La API de Anthropic rechazó la solicitud (stop_reason=refusal)")

    try:
        texto = next(b.text for b in response.content if b.type == "text")
        data = json.loads(texto)
    except (StopIteration, json.JSONDecodeError, TypeError) as e:
        raise InterpretacionError(f"Respuesta de la API no tiene el formato esperado: {e}") from e

    motivo = data.get("motivo", "")

    if not data.get("confianza"):
        return InterpretacionCorreccion(confianza=False, timestamp_inicio=None, timestamp_fin=None, motivo=motivo)

    idx_inicio, idx_fin = data.get("idx_inicio"), data.get("idx_fin")
    n = len(segments)
    if not isinstance(idx_inicio, int) or not isinstance(idx_fin, int) or not (0 <= idx_inicio <= idx_fin < n):
        # El modelo dijo que tenía confianza pero los índices no son
        # utilizables — se trata igual que "sin confianza", nunca se usa
        # un índice fuera de rango.
        return InterpretacionCorreccion(
            confianza=False,
            timestamp_inicio=None,
            timestamp_fin=None,
            motivo=f"El modelo devolvió índices inválidos (idx_inicio={idx_inicio}, idx_fin={idx_fin}, n_segmentos={n}).",
        )

    return InterpretacionCorreccion(
        confianza=True,
        timestamp_inicio=segments[idx_inicio]["start"],
        timestamp_fin=segments[idx_fin]["end"],
        motivo=motivo,
    )
