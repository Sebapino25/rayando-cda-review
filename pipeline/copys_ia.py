"""Genera los copys de Instagram/YouTube/TikTok y el título de portada con
la API de Anthropic a partir de la transcripción cruda del clip, cuando no
hay override manual en clip_overrides.json (ver cortar_clip.build_copys).

Edita la transcripción (saca muletillas, repeticiones, tartamudeos de audio
en vivo) pero no inventa contenido: no le agrega a la persona palabras o
ideas que no dijo.

Los hashtags NO los genera el modelo — se agregan después en
cortar_clip.py de forma determinística (config.COPYS_HASHTAGS_BASE +
hashtags_extra del override), así que este módulo solo devuelve el cuerpo
del texto sin hashtags.

Requiere ANTHROPIC_API_KEY en el .env.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from dotenv import load_dotenv

import config

load_dotenv(config.PROJECT_DIR / ".env")

MODEL = "claude-opus-4-8"

CONTEXTO_PROGRAMA = (
    '"Rayando el CDA" es un programa semanal de hinchas de Universidad de '
    "Chile (la U), hecho por 3 personas: un periodista, un editor y una "
    'persona a cargo de estrategia/producción. Identidad "Orozquista": '
    "crítico de la dirigencia actual del club, no oficialista. Tono "
    "cercano, chileno, directo — nada formal ni de comunicado de prensa."
)

REGLA_EDICION = (
    "Regla de edición de la transcripción (aplica a las tres plataformas): "
    'sacá muletillas ("onda", "eh", repeticiones, tartamudeos de audio en '
    "vivo), pero es edición, no invención — no le agregues a la persona "
    "palabras o ideas que no dijo. El objetivo es que se lea bien escrito, "
    "no que se genere contenido nuevo.\n\n"
    "Ortografía: el texto editado tiene que tener ortografía y "
    "acentuación correctas del español, sin excepción — incluye las "
    "tildes que falten en la transcripción cruda de Whisper.\n\n"
    "Voseo chileno: el tono de este programa usa voseo chileno "
    '("no le digai", "vai", "erís", "cachái", etc.). NUNCA lo conviertas '
    'a conjugación de vosotros de España (ej. "digáis", "vais") ni a '
    '"tú" estándar (ej. "no le digas", "vas") — el voseo chileno se '
    "mantiene tal cual, solo corregile la tilde si le falta (ej. "
    '"digai" → "digái", nunca "digáis").\n\n'
    "Nombres propios: NUNCA cambies, adivines ni \"corrijas\" un nombre "
    "propio por tu cuenta, aunque te parezca un error de transcripción. "
    "Dejalo exactamente como aparece en la transcripción que te paso. La "
    "corrección de nombres propios ya pasa antes por un corrector "
    "determinístico aparte (diccionario del programa); si un nombre te "
    "llega tal cual, es porque ese corrector no lo tocó — no es tu tarea "
    "adivinar si está bien o mal."
)

SYSTEM_PROMPT = f"""Sos redactor de copys para redes sociales de "Rayando el CDA".

{CONTEXTO_PROGRAMA}

{REGLA_EDICION}

Te paso el nombre del clip (solo de referencia, nunca lo uses como título) \
y su transcripción cruda tal cual salió de Whisper. Generá el copy para \
cada plataforma:

- Instagram: 3-5 líneas. Empezá con un gancho de una sola línea — lo \
primero que lee alguien scrolleando. El gancho es una línea NUEVA que vos \
redactás para enganchar, nunca la primera frase (ni una versión apenas \
parafraseada) de la transcripción — esto aplica sin importar el formato \
de origen: una respuesta de entrevista, un rant o discurso ya \
declarativo del panel, o un diálogo. Aunque la frase original ya suene \
potente o citable tal cual, igual tenés que escribir un gancho con una \
construcción distinta a cualquier oración textual de la transcripción, \
no una cita disfrazada de gancho. Seguí con el contexto editado de la \
transcripción — ahí sí podés citar o parafrasear de cerca. NO incluyas \
hashtags (se agregan aparte).
- YouTube: título corto y directo basado en el contenido real del clip \
(nunca genérico ni basado en el nombre de la carpeta/archivo). \
Descripción de 1-2 líneas editada de la transcripción. Sin hashtags.
- TikTok: el más corto y directo de los tres. Gancho fuerte en la \
primera línea, más informal/crudo que el de Instagram, con la misma \
regla del gancho de Instagram: es una línea nueva, no una cita textual \
de la transcripción. NO incluyas hashtags (se agregan aparte).
- Portada (imagen del clip): título de 2 a 6 palabras, estilo titular \
editorial/cintillo deportivo — no es una oración completa ni una cita, \
es la versión más corta y gritada de la idea, pensada para leerse en \
menos de un segundo sobre una imagen. Puede usar ¡!/¿? si el tono lo \
pide, pero no es obligatorio. Sin hashtags.

Cada plataforma tiene que sentirse escrita para esa plataforma, no \
recortada de otra:
- El gancho de Instagram, el título de YouTube, el gancho de TikTok y el \
título de portada NO pueden repetir la misma frase o construcción casi \
textual entre sí — buscá un ángulo o forma de decirlo distinta para cada \
uno, aunque describan el mismo momento del clip.
- El copy de TikTok en particular no es "el de Instagram pero más \
corto": tiene que tener su propio ángulo, más crudo/directo/informal, \
no la misma frase editada a la mitad.

Devolvé únicamente los cinco campos pedidos."""

_SCHEMA = {
    "type": "object",
    "properties": {
        "copy_instagram_cuerpo": {
            "type": "string",
            "description": "Copy de Instagram completo (gancho + contexto editado), sin hashtags.",
        },
        "youtube_titulo": {
            "type": "string",
            "description": "Título corto y directo para YouTube, basado en el contenido real del clip.",
        },
        "youtube_descripcion": {
            "type": "string",
            "description": "Descripción de 1-2 líneas para YouTube, sin hashtags.",
        },
        "copy_tiktok_cuerpo": {
            "type": "string",
            "description": "Copy de TikTok completo (gancho fuerte + contexto editado), sin hashtags.",
        },
        "titulo_portada": {
            "type": "string",
            "description": "Título corto (2-6 palabras) estilo titular editorial para la portada del clip, sin hashtags.",
        },
    },
    "required": [
        "copy_instagram_cuerpo",
        "youtube_titulo",
        "youtube_descripcion",
        "copy_tiktok_cuerpo",
        "titulo_portada",
    ],
    "additionalProperties": False,
}


@dataclass
class CopysGenerados:
    copy_instagram_cuerpo: str
    youtube_titulo: str
    youtube_descripcion: str
    copy_tiktok_cuerpo: str
    titulo_portada: str


class CopyIAError(Exception):
    """La generación de copys con la API de Anthropic falló."""


def _client():
    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise CopyIAError("Falta la variable de entorno ANTHROPIC_API_KEY (revisa tu .env)")
    return anthropic.Anthropic(api_key=api_key)


def generar_copys(nombre_clip: str, transcripcion: str) -> CopysGenerados:
    """Genera copy_instagram_cuerpo/youtube_titulo/youtube_descripcion/
    copy_tiktok_cuerpo/titulo_portada con la API de Anthropic a partir de la
    transcripción cruda del clip. Lanza CopyIAError si falta la API key, si
    la API rechaza la solicitud o si la respuesta no es JSON válido."""
    client = _client()
    mensaje_usuario = (
        f"Nombre del clip (carpeta, NO usar como título): {nombre_clip}\n\n"
        f"Transcripción cruda:\n{transcripcion}"
    )
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=2048,
            thinking={"type": "adaptive"},
            system=SYSTEM_PROMPT,
            output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
            messages=[{"role": "user", "content": mensaje_usuario}],
        )
    except Exception as e:
        raise CopyIAError(f"Llamada a la API de Anthropic falló: {e}") from e

    if response.stop_reason == "refusal":
        raise CopyIAError("La API de Anthropic rechazó la solicitud (stop_reason=refusal)")

    try:
        texto = next(b.text for b in response.content if b.type == "text")
        data = json.loads(texto)
        return CopysGenerados(**data)
    except (StopIteration, json.JSONDecodeError, TypeError) as e:
        raise CopyIAError(f"Respuesta de la API no tiene el formato esperado: {e}") from e
