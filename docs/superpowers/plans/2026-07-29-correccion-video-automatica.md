# Corrección automática de video (subsistema 5) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que un pedido de "Corrección de video" (in/out point) hecho por el equipo editorial en `comentarios_video` se aplique solo — sin que nadie vuelva a cortar el clip a mano — enganchado al disparador automático ya existente.

**Architecture:** Un script nuevo (`pipeline/reprocesar_video.py`) busca filas `estado='correccion_video'` en Supabase, usa la API de Anthropic para interpretar el pedido en texto libre contra la transcripción completa del programa (nunca adivina: si no hay confianza, aborta y avisa), y si hay confianza vuelve a cortar el clip desde la grabación original con el nuevo rango, reusando las funciones ya existentes de `cortar_clip.py`/`publicar.py`. Se engancha a `auto_procesar.ps1` (loop de 5 min, Task Scheduler) para correr sin intervención manual.

**Tech Stack:** Python 3.12, API de Anthropic (`claude-opus-4-8`, mismo modelo que `detectar_momentos.py`), ffmpeg/ffprobe, PowerShell 5.1, Supabase (postgres + storage).

## Global Constraints

- Nunca adivinar: si la interpretación del pedido no tiene confianza suficiente, o la correlación fila↔carpeta es ambigua (0 o >1 candidatas), el script aborta sin tocar nada — nunca aplica "la mejor estimación".
- Toda falla (interpretación sin confianza, carpeta no encontrada/ambigua, error técnico de recorte, error de subida) avisa **solo** al dueño del proyecto (`seba.pino.v@gmail.com`), nunca al equipo — esto corre desatendido, a diferencia de `reprocesar_subtitulos.py` que hoy se corre a mano.
- El clip corregido vuelve a `estado='pendiente'` (revisión fresca), no a `'aprobado'` directo.
- `comentarios_video` se conserva (no se borra) como registro histórico del pedido.
- `copy_instagram`/`copy_tiktok`/`youtube_titulo`/`youtube_descripcion`/`titulo` (copys ya curados) **no se regeneran** — la corrección es solo de timing, no de contenido. Igual que hace hoy `reprocesar_subtitulos.py` con estos mismos campos.
- Las pruebas automatizadas nunca tocan clips reales — usan/mockean, nunca `estado='prueba'` de producción sin el protocolo de `app/README.md`.
- Este repo no usa pytest: scripts standalone (`python test_*.py`) con `assert` simple, mismo patrón que `test_transcribir_cpu_fallback.py`.

---

### Task 1: Extraer módulo compartido de correlación fila↔carpeta

**Files:**
- Create: `pipeline/correlacionar_clip.py`
- Create: `pipeline/test_correlacionar_clip.py`
- Modify: `pipeline/reprocesar_subtitulos.py` (elimina el código movido, importa del módulo nuevo)

**Interfaces:**
- Produces: `correlacionar_clip.encontrar_carpetas_candidatas(row: dict) -> list[Path]`, `correlacionar_clip.candidata_mas_parecida(row: dict) -> tuple[Path, float] | None`, `correlacionar_clip._normalizar(texto: str | None) -> str`, `correlacionar_clip.parse_srt(path: Path) -> list[tuple[float, float, str]]`. Usado por `reprocesar_subtitulos.py` (Task existente, se actualiza acá) y por `reprocesar_video.py` (Task 3).

Hoy `pipeline/reprocesar_subtitulos.py` (líneas 24-158) tiene toda la lógica de "encontrar la carpeta local de un clip a partir de su fila de Supabase" mezclada con la lógica de reproceso de subtítulos. `reprocesar_video.py` (Task 3) necesita EXACTAMENTE la misma correlación (mismo mecanismo: match exacto de texto contra `transcripcion_original`, nunca adivinar). Se extrae a un módulo compartido en vez de duplicarla, y de paso se le suma el test que hoy no tiene.

- [ ] **Step 1: Crear `pipeline/correlacionar_clip.py` con el código movido**

```python
"""Correlaciona una fila de rayando_cda.clips con su carpeta local en
clips\\<semana>\\<nombre>\\, comparando el texto de subtitulos.srt (unido)
contra transcripcion_original de esa fila. Usado por
reprocesar_subtitulos.py y reprocesar_video.py — ninguna columna en
Supabase guarda la carpeta local, así que esta es la única forma de
encontrarla.

El match tiene que ser exacto y único: si no hay ninguna coincidencia o
hay más de una, quien llama debe abortar y reportarlo, nunca adivinar.
"""

from __future__ import annotations

import difflib
import re
from pathlib import Path

import config

SRT_TIME_RE = re.compile(r"(\d{2}):(\d{2}):(\d{2}),(\d{3})")


def _srt_timestamp_to_seconds(ts: str) -> float:
    hh, mm, ss, ms = SRT_TIME_RE.match(ts.strip()).groups()
    return int(hh) * 3600 + int(mm) * 60 + int(ss) + int(ms) / 1000


def parse_srt(path: Path) -> list[tuple[float, float, str]]:
    """Lee un subtitulos.srt ya generado por cortar_clip.build_clip_srt y
    devuelve la misma estructura (cs, ce, text) que build_clip_srt/
    build_clip_ass reciben, para poder reusar esas funciones tal cual."""
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        return []
    segmentos = []
    for bloque in re.split(r"\n\s*\n", content):
        lineas = bloque.strip().splitlines()
        if len(lineas) < 3:
            continue
        inicio_str, fin_str = (t.strip() for t in lineas[1].split("-->"))
        inicio = _srt_timestamp_to_seconds(inicio_str)
        fin = _srt_timestamp_to_seconds(fin_str)
        texto = " ".join(lineas[2:]).strip()
        segmentos.append((inicio, fin, texto))
    return segmentos


def _normalizar(texto: str | None) -> str:
    return " ".join((texto or "").split())


def encontrar_carpetas_candidatas(row: dict) -> list[Path]:
    """Busca TODAS las carpetas locales (clips\\<semana>\\<nombre>\\) cuyo
    subtitulos.srt (texto unido) calza EXACTO con transcripcion_original de
    esta fila. En el caso sano esto devuelve una sola carpeta; quien llama
    es responsable de detenerse (no adivinar) si la lista queda vacía o
    tiene más de un elemento."""
    semana = row.get("semana") or ""
    fecha_dir = config.CLIPS_DIR / str(semana)
    if not fecha_dir.is_dir():
        return []

    objetivo = _normalizar(row.get("transcripcion_original"))
    if not objetivo:
        return []

    coincidencias = []
    for carpeta in sorted(p for p in fecha_dir.iterdir() if p.is_dir()):
        srt_path = carpeta / "subtitulos.srt"
        if not srt_path.exists():
            continue
        segmentos = parse_srt(srt_path)
        texto = _normalizar(" ".join(t for _, _, t in segmentos))
        if texto == objetivo:
            coincidencias.append(carpeta)
    return coincidencias


def candidata_mas_parecida(row: dict) -> tuple[Path, float] | None:
    """Diagnóstico para cuando no hubo match exacto: entre todas las
    carpetas de la misma semana, devuelve la que más se parece (ratio de
    difflib) a transcripcion_original, junto con el ratio. Es solo
    informativo — nunca se usa para elegir la carpeta a procesar."""
    semana = row.get("semana") or ""
    fecha_dir = config.CLIPS_DIR / str(semana)
    if not fecha_dir.is_dir():
        return None

    objetivo = _normalizar(row.get("transcripcion_original"))
    if not objetivo:
        return None

    mejor: tuple[Path, float] | None = None
    for carpeta in sorted(p for p in fecha_dir.iterdir() if p.is_dir()):
        srt_path = carpeta / "subtitulos.srt"
        if not srt_path.exists():
            continue
        segmentos = parse_srt(srt_path)
        texto = _normalizar(" ".join(t for _, _, t in segmentos))
        ratio = difflib.SequenceMatcher(None, texto, objetivo).ratio()
        if mejor is None or ratio > mejor[1]:
            mejor = (carpeta, ratio)
    return mejor
```

- [ ] **Step 2: Escribir el test standalone (que hoy fallaría si algo se rompe en la extracción)**

Crear `pipeline/test_correlacionar_clip.py`:

```python
"""Prueba AISLADA de correlacionar_clip: verifica los casos 0/1/>1
coincidencias al buscar la carpeta local de una fila de Supabase. Usa una
carpeta temporal (monkeypatch de config.CLIPS_DIR), nunca clips reales.

Uso:
    python test_correlacionar_clip.py
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import config
import correlacionar_clip


def _crear_clip(base: Path, semana: str, nombre: str, srt_texto: str) -> None:
    carpeta = base / semana / nombre
    carpeta.mkdir(parents=True)
    srt = f"1\n00:00:00,000 --> 00:00:02,000\n{srt_texto}\n"
    (carpeta / "subtitulos.srt").write_text(srt, encoding="utf-8")


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="rayando_cda_test_"))
    try:
        with patch.object(config, "CLIPS_DIR", tmp):
            _crear_clip(tmp, "2026-07-27", "clip-a", "hola que tal")
            _crear_clip(tmp, "2026-07-27", "clip-b", "otro clip distinto")

            # Caso: 1 coincidencia exacta
            fila_ok = {"semana": "2026-07-27", "transcripcion_original": "hola que tal"}
            resultado = correlacionar_clip.encontrar_carpetas_candidatas(fila_ok)
            assert len(resultado) == 1, f"esperaba 1 coincidencia, hubo {len(resultado)}"
            assert resultado[0].name == "clip-a"

            # Caso: 0 coincidencias
            fila_sin_match = {"semana": "2026-07-27", "transcripcion_original": "esto no existe en ningun lado"}
            resultado = correlacionar_clip.encontrar_carpetas_candidatas(fila_sin_match)
            assert resultado == [], f"esperaba 0 coincidencias, hubo {len(resultado)}"

            # Caso: >1 coincidencias (mismo texto en dos carpetas)
            _crear_clip(tmp, "2026-07-27", "clip-c", "hola que tal")
            resultado = correlacionar_clip.encontrar_carpetas_candidatas(fila_ok)
            assert len(resultado) == 2, f"esperaba 2 coincidencias (ambigüedad), hubo {len(resultado)}"

            # candidata_mas_parecida nunca debe lanzar, solo informar
            pista = correlacionar_clip.candidata_mas_parecida(fila_sin_match)
            assert pista is not None
            assert pista[0].name in ("clip-a", "clip-b", "clip-c")

        print("OK: encontrar_carpetas_candidatas/candidata_mas_parecida cubren los casos 0/1/>1.")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Correr el test y confirmar que pasa**

Run: `cd pipeline && python test_correlacionar_clip.py`
Expected: `OK: encontrar_carpetas_candidatas/candidata_mas_parecida cubren los casos 0/1/>1.` y código de salida 0.

- [ ] **Step 4: Actualizar `reprocesar_subtitulos.py` para importar del módulo nuevo**

En `pipeline/reprocesar_subtitulos.py`:
- Eliminar las definiciones de `SRT_TIME_RE`, `_srt_timestamp_to_seconds`, `parse_srt`, `_normalizar`, `encontrar_carpetas_candidatas`, `candidata_mas_parecida` (lo que se movió a `correlacionar_clip.py`).
- Agregar el import:
```python
from correlacionar_clip import (
    _normalizar,
    candidata_mas_parecida,
    encontrar_carpetas_candidatas,
    parse_srt,
)
```
- El resto del archivo (`redistribuir_texto`, `_siguiente_version_dir`, `respaldar_version_anterior`, `buscar_pendientes`, `procesar_fila`, `main`) queda igual — todos siguen funcionando porque los nombres importados son los mismos.

- [ ] **Step 5: Confirmar que `reprocesar_subtitulos.py` sigue funcionando (dry-run, sin tocar nada real)**

Run: `cd pipeline && python reprocesar_subtitulos.py`
Expected: imprime `No hay clips con cambios pendientes...` (o la lista de pendientes reales si los hay) sin ningún `ImportError`/`NameError` — confirma que la extracción no rompió nada.

- [ ] **Step 6: Commit**

```bash
git add pipeline/correlacionar_clip.py pipeline/test_correlacionar_clip.py pipeline/reprocesar_subtitulos.py
git commit -m "Extraer correlacionar_clip.py (fila<->carpeta) de reprocesar_subtitulos.py, con tests"
```

---

### Task 2: Módulo intérprete de pedidos de corrección (IA)

**Files:**
- Create: `pipeline/interpretar_correccion.py`
- Create: `pipeline/test_interpretar_correccion.py`

**Interfaces:**
- Consumes: `detectar_momentos._construir_lista_segmentos(segments: list[dict]) -> str` (reusa el mismo formato de lista numerada con `empieza_oracion`/`termina_oracion` que ya usa la detección de candidatos — nunca se le pasa al modelo un timestamp en segundos libre, siempre índices de segmento real).
- Produces: `interpretar_correccion.InterpretacionCorreccion` (dataclass: `confianza: bool`, `timestamp_inicio: float | None`, `timestamp_fin: float | None`, `motivo: str`), `interpretar_correccion.interpretar_correccion(comentarios_video: str, segments: list[dict]) -> InterpretacionCorreccion`, `interpretar_correccion.InterpretacionError` (excepción). Usado por `reprocesar_video.py` (Task 3).

Mismo patrón de llamada a la API de Anthropic que `detectar_momentos.py`/`copys_ia.py` (`client.messages.create` con `output_config={"format": {"type": "json_schema", ...}}`, `thinking={"type": "adaptive"}`, mismo modelo `config.CANDIDATOS_MODEL`). La diferencia clave: el modelo puede devolver `confianza=false` explícito, y el código nunca debe usar `timestamp_inicio`/`timestamp_fin` cuando `confianza` es `false`.

- [ ] **Step 1: Escribir el test (que hoy falla porque el módulo no existe)**

Crear `pipeline/test_interpretar_correccion.py`:

```python
"""Prueba AISLADA de interpretar_correccion: mockea el cliente de
Anthropic (nunca llama a la API real) y verifica que (a) con una
respuesta confiada devuelve los timestamps correctos calzados a
segmentos reales, (b) con confianza=false no inventa timestamps, y (c)
si el modelo devuelve índices inválidos, se trata igual que "sin
confianza" (no se usan índices fuera de rango).

Uso:
    python test_interpretar_correccion.py
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import interpretar_correccion as ic

SEGMENTS = [
    {"start": 0.0, "end": 2.0, "text": "Buenas noches a todos."},
    {"start": 2.0, "end": 5.5, "text": "Hoy vamos a hablar del clásico universitario."},
    {"start": 5.5, "end": 9.0, "text": "Y ahora pasamos al informe de lesionados."},
]


class _FakeTextBlock:
    def __init__(self, text: str):
        self.type = "text"
        self.text = text


def _fake_response(payload: dict, stop_reason: str = "end_turn"):
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=[_FakeTextBlock(json.dumps(payload))],
    )


def test_confiado() -> None:
    payload = {"confianza": True, "idx_inicio": 1, "idx_fin": 2, "motivo": "Empieza en 'Hoy vamos...'"}
    fake_client = SimpleNamespace(
        messages=SimpleNamespace(create=lambda **kwargs: _fake_response(payload))
    )
    with patch.object(ic, "_client", lambda: fake_client):
        resultado = ic.interpretar_correccion("Empezá desde que dice 'Hoy vamos'", SEGMENTS)
    assert resultado.confianza is True
    assert resultado.timestamp_inicio == 2.0, resultado.timestamp_inicio
    assert resultado.timestamp_fin == 9.0, resultado.timestamp_fin


def test_sin_confianza() -> None:
    payload = {"confianza": False, "idx_inicio": 0, "idx_fin": 0, "motivo": "No encuentro esa frase en la transcripción."}
    fake_client = SimpleNamespace(
        messages=SimpleNamespace(create=lambda **kwargs: _fake_response(payload))
    )
    with patch.object(ic, "_client", lambda: fake_client):
        resultado = ic.interpretar_correccion("Cortá donde dice algo que no está", SEGMENTS)
    assert resultado.confianza is False
    assert resultado.timestamp_inicio is None
    assert resultado.timestamp_fin is None
    assert "No encuentro" in resultado.motivo


def test_indices_invalidos_se_tratan_como_sin_confianza() -> None:
    payload = {"confianza": True, "idx_inicio": 5, "idx_fin": 9, "motivo": "fuera de rango"}
    fake_client = SimpleNamespace(
        messages=SimpleNamespace(create=lambda **kwargs: _fake_response(payload))
    )
    with patch.object(ic, "_client", lambda: fake_client):
        resultado = ic.interpretar_correccion("pedido cualquiera", SEGMENTS)
    assert resultado.confianza is False
    assert resultado.timestamp_inicio is None


def main() -> None:
    test_confiado()
    test_sin_confianza()
    test_indices_invalidos_se_tratan_como_sin_confianza()
    print("OK: interpretar_correccion cubre confianza / sin-confianza / índices inválidos.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Correr el test y confirmar que falla**

Run: `cd pipeline && python test_interpretar_correccion.py`
Expected: `ModuleNotFoundError: No module named 'interpretar_correccion'`

- [ ] **Step 3: Implementar `pipeline/interpretar_correccion.py`**

```python
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
```

- [ ] **Step 4: Correr el test y confirmar que pasa**

Run: `cd pipeline && python test_interpretar_correccion.py`
Expected: `OK: interpretar_correccion cubre confianza / sin-confianza / índices inválidos.` y código de salida 0.

- [ ] **Step 5: Commit**

```bash
git add pipeline/interpretar_correccion.py pipeline/test_interpretar_correccion.py
git commit -m "Agregar interpretar_correccion.py: interpreta pedidos de corrección de in/out con IA"
```

---

### Task 3: `reprocesar_video.py` — localizar, interpretar y decidir (sin tocar archivos todavía)

**Files:**
- Create: `pipeline/reprocesar_video.py`
- Create: `pipeline/test_reprocesar_video_decision.py`

**Interfaces:**
- Consumes: `correlacionar_clip.encontrar_carpetas_candidatas`/`candidata_mas_parecida` (Task 1), `interpretar_correccion.interpretar_correccion`/`InterpretacionCorreccion`/`InterpretacionError` (Task 2), `cortar_clip.load_master_segments(video_path: Path) -> list[dict] | None`, `cortar_clip.resolve_video(video_arg: str) -> Path`.
- Produces: `reprocesar_video.buscar_pendientes(supabase, clip_id: str | None) -> list[dict]`, `reprocesar_video.DecisionReproceso` (dataclass: `carpeta: Path | None`, `nuevo_inicio: float | None`, `nuevo_fin: float | None`, `motivo_abort: str | None` — `motivo_abort` no-`None` significa "no se puede continuar, avisar y no tocar nada"), `reprocesar_video.decidir(row: dict) -> DecisionReproceso`. `decidir()` es la parte pura/testeable (localizar carpeta + interpretar pedido); el I/O real (recorte, subida, update de Supabase) se agrega en la Task 4 sobre este mismo archivo.

Esta task deja el archivo en un estado intermedio pero completo y testeable: puede decidir qué haría (incluido en dry-run) sin ejecutar ningún ffmpeg/YouTube/Supabase todavía. La Task 4 completa `procesar_fila()` para que `--apply` ejecute de verdad.

- [ ] **Step 1: Escribir el test de la lógica de decisión (falla porque el módulo no existe)**

Crear `pipeline/test_reprocesar_video_decision.py`:

```python
"""Prueba AISLADA de la lógica de decisión de reprocesar_video.py
(decidir()): localizar la carpeta e interpretar el pedido, SIN tocar
ningún archivo ni llamar a la API real. Mockea correlacionar_clip e
interpretar_correccion.

Uso:
    python test_reprocesar_video_decision.py
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import interpretar_correccion as ic
import reprocesar_video as rv

FILA = {
    "id": "abc-123",
    "semana": "2026-07-27",
    "comentarios_video": "Empezá 2 segundos antes",
    "transcripcion_original": "hola que tal",
}


def test_decide_confiado_cuando_hay_una_carpeta_y_confianza() -> None:
    carpeta_falsa = Path("clips/2026-07-27/clip-a")
    interpretacion = ic.InterpretacionCorreccion(
        confianza=True, timestamp_inicio=10.0, timestamp_fin=20.0, motivo="ok"
    )
    with patch("reprocesar_video.encontrar_carpetas_candidatas", return_value=[carpeta_falsa]), \
         patch("reprocesar_video.interpretar_correccion", return_value=interpretacion), \
         patch("reprocesar_video.cargar_segments_de_carpeta", return_value=[{"start": 0, "end": 1, "text": "x"}]):
        decision = rv.decidir(FILA)
    assert decision.motivo_abort is None
    assert decision.carpeta == carpeta_falsa
    assert decision.nuevo_inicio == 10.0
    assert decision.nuevo_fin == 20.0


def test_aborta_si_no_hay_carpeta() -> None:
    with patch("reprocesar_video.encontrar_carpetas_candidatas", return_value=[]):
        decision = rv.decidir(FILA)
    assert decision.motivo_abort is not None
    assert "carpeta" in decision.motivo_abort.lower()


def test_aborta_si_hay_mas_de_una_carpeta() -> None:
    carpetas = [Path("clips/2026-07-27/clip-a"), Path("clips/2026-07-27/clip-c")]
    with patch("reprocesar_video.encontrar_carpetas_candidatas", return_value=carpetas):
        decision = rv.decidir(FILA)
    assert decision.motivo_abort is not None
    assert "ambig" in decision.motivo_abort.lower() or "más de una" in decision.motivo_abort.lower()


def test_aborta_si_la_ia_no_tiene_confianza() -> None:
    carpeta_falsa = Path("clips/2026-07-27/clip-a")
    interpretacion = ic.InterpretacionCorreccion(
        confianza=False, timestamp_inicio=None, timestamp_fin=None, motivo="frase no encontrada"
    )
    with patch("reprocesar_video.encontrar_carpetas_candidatas", return_value=[carpeta_falsa]), \
         patch("reprocesar_video.interpretar_correccion", return_value=interpretacion), \
         patch("reprocesar_video.cargar_segments_de_carpeta", return_value=[{"start": 0, "end": 1, "text": "x"}]):
        decision = rv.decidir(FILA)
    assert decision.motivo_abort is not None
    assert "frase no encontrada" in decision.motivo_abort


def main() -> None:
    test_decide_confiado_cuando_hay_una_carpeta_y_confianza()
    test_aborta_si_no_hay_carpeta()
    test_aborta_si_hay_mas_de_una_carpeta()
    test_aborta_si_la_ia_no_tiene_confianza()
    print("OK: reprocesar_video.decidir() cubre confiado / sin-carpeta / ambiguo / sin-confianza.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Correr el test y confirmar que falla**

Run: `cd pipeline && python test_reprocesar_video_decision.py`
Expected: `ModuleNotFoundError: No module named 'reprocesar_video'`

- [ ] **Step 3: Implementar el esqueleto de `reprocesar_video.py` con `buscar_pendientes()` y `decidir()`**

```python
"""Cierra el loop de corrección de in/out points pedida por el equipo
editorial: busca en rayando_cda.clips las filas con
estado='correccion_video', usa la API de Anthropic (interpretar_correccion)
para interpretar comentarios_video contra la transcripción completa del
programa y, si hay confianza, vuelve a cortar el clip (horizontal +
vertical con subtítulos/logo/portada) desde la grabación original con el
nuevo rango, lo sube como nuevo video no listado de YouTube y actualiza la
fila (estado vuelve a 'pendiente').

Nunca adivina: si la interpretación no tiene confianza, o la carpeta local
no se puede correlacionar sin ambigüedad, aborta sin tocar nada.

Corre en dry-run por defecto. Usa --apply para ejecutar de verdad,
--clip-id para probar contra un solo clip, y --uno para procesar solo la
fila más antigua pendiente (pensado para el disparador automático, que
llama a este script cada 5 minutos y deja que la siguiente corrida
procese el resto).
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import config
import cortar_clip
import publicar
from correlacionar_clip import candidata_mas_parecida, encontrar_carpetas_candidatas
from interpretar_correccion import InterpretacionError, interpretar_correccion


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
```

- [ ] **Step 4: Correr el test y confirmar que pasa**

Run: `cd pipeline && python test_reprocesar_video_decision.py`
Expected: `OK: reprocesar_video.decidir() cubre confiado / sin-carpeta / ambiguo / sin-confianza.` y código de salida 0.

- [ ] **Step 5: Commit**

```bash
git add pipeline/reprocesar_video.py pipeline/test_reprocesar_video_decision.py
git commit -m "reprocesar_video.py: localizar carpeta e interpretar pedido de corrección (sin ejecutar todavía)"
```

---

### Task 4: `reprocesar_video.py` — ejecutar la corrección (`--apply`)

**Files:**
- Modify: `pipeline/reprocesar_video.py`

**Interfaces:**
- Consumes: `correlacionar_clip.respaldar_version_anterior` — **no existe todavía en `correlacionar_clip.py`**; en este task se mueve `respaldar_version_anterior`/`_siguiente_version_dir` de `reprocesar_subtitulos.py` a `correlacionar_clip.py` (mismo criterio de la Task 1: lo necesitan ambos scripts). `cortar_clip.cut_horizontal`, `cortar_clip.clip_segments`, `cortar_clip.split_into_captions`, `cortar_clip.build_clip_srt`, `cortar_clip.build_clip_ass`, `cortar_clip.build_vertical`, `cortar_clip.join_transcripcion`, `cortar_clip._cargar_overrides`, `cortar_clip.format_hhmmss`, `cortar_clip.program_date_from_name`, `portadas.build_portadas`, `publicar.validar_clip`, `publicar.ClipInvalido`, `publicar.subir_youtube`, `publicar.subir_portada_storage`, `publicar.subir_video_storage`, `publicar.actualizar_clip_supabase`, `publicar.get_supabase_client`.
- Produces: `reprocesar_video.procesar_fila(row: dict, apply: bool) -> bool` (`True` = se corrigió con éxito o no había nada que hacer en dry-run; `False` = falló o abortó — usado por `main()` en la Task 5 para el contrato de exit code), `reprocesar_video.EjecutarError` (excepción para fallas técnicas del recorte/subida, distinta de `motivo_abort` que ya cubre correlación/interpretación).

- [ ] **Step 1: Mover `respaldar_version_anterior`/`_siguiente_version_dir` a `correlacionar_clip.py`**

En `pipeline/correlacionar_clip.py`, agregar al final (mismo cuerpo que hoy tiene `reprocesar_subtitulos.py`):

```python
import shutil


def _siguiente_version_dir(carpeta: Path) -> Path:
    n = 1
    while (carpeta / f"v{n}").exists():
        n += 1
    return carpeta / f"v{n}"


def respaldar_version_anterior(carpeta: Path) -> Path:
    """Mueve vertical.mp4 + subtitulos.srt/.ass (y horizontal_original.mp4,
    si existe) a una subcarpeta vN\\ antes de sobreescribirlos."""
    destino = _siguiente_version_dir(carpeta)
    destino.mkdir(parents=True, exist_ok=False)
    for nombre in ("vertical.mp4", "subtitulos.srt", "subtitulos.ass", "horizontal_original.mp4"):
        origen = carpeta / nombre
        if origen.exists():
            shutil.move(str(origen), str(destino / nombre))
    return destino
```

Nota: se agrega `horizontal_original.mp4` a la lista de archivos respaldados (`reprocesar_subtitulos.py` no lo necesitaba porque no re-cortaba el horizontal; `reprocesar_video.py` sí re-corta ese archivo, así que también hay que respaldar la versión anterior).

En `pipeline/reprocesar_subtitulos.py`, eliminar `_siguiente_version_dir`/`respaldar_version_anterior` y agregarlos al import ya existente de `correlacionar_clip`:

```python
from correlacionar_clip import (
    _normalizar,
    candidata_mas_parecida,
    encontrar_carpetas_candidatas,
    parse_srt,
    respaldar_version_anterior,
)
```

Run: `cd pipeline && python reprocesar_subtitulos.py`
Expected: sigue funcionando igual que en la Task 1 (sin `ImportError`).

- [ ] **Step 2: Implementar `procesar_fila()` en `reprocesar_video.py`**

Agregar al final de `pipeline/reprocesar_video.py`:

```python
from correlacionar_clip import respaldar_version_anterior
import portadas


class EjecutarError(Exception):
    """Falló un paso técnico al ejecutar la corrección (recorte, validación o subida)."""


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
    titulo_portada = overrides.get("titulo_portada")
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
        print(f"  ABORTADO: {decision.motivo_abort}")
        return False

    print(f"  Carpeta local: {decision.carpeta}")
    print(f"  Nuevo rango: {cortar_clip.format_hhmmss(decision.nuevo_inicio)} -> {cortar_clip.format_hhmmss(decision.nuevo_fin)}")
    print(f"  Interpretación: {decision.interpretacion_motivo}")

    if not apply:
        print("  [dry-run] Se respaldaría la versión anterior, se re-cortaría con este rango, "
              "se subiría un video nuevo a YouTube y se actualizaría la fila a estado='pendiente'.")
        return True

    metadata_path = decision.carpeta / "metadata.json"
    import json
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    video_path = Path(metadata["video_fuente"])
    nombre_clip = decision.carpeta.name
    program_date = cortar_clip.program_date_from_name(video_path)

    print("  Respaldando versión anterior (vertical.mp4 + horizontal_original.mp4 + subtítulos) en vN\\...")
    destino_backup = respaldar_version_anterior(decision.carpeta)
    print(f"    Respaldado en: {destino_backup}")

    try:
        vertical_path, transcripcion_texto = _ejecutar_recorte(
            decision.carpeta, video_path, decision.nuevo_inicio, decision.nuevo_fin, nombre_clip
        )
    except EjecutarError as e:
        print(f"  FALLÓ: {e}")
        print(f"  (versión anterior respaldada en {destino_backup}, la fila de Supabase no se tocó)")
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

    print(f"  Listo. Clip vuelve a 'pendiente' para revisión. youtube_video_id: {video_id_anterior} -> {nuevo_video_id}")
    print(f"  NOTA: el video anterior ({video_id_anterior}) sigue en YouTube como no listado; bórralo a mano si ya no sirve.")
    return True
```

- [ ] **Step 3: Prueba manual con el fixture de QA (dry-run, sin `--apply`)**

Esto no es un test automatizado (requiere una fila real en Supabase y una carpeta local real, igual que `reprocesar_subtitulos.py` no tiene test automatizado de su camino feliz). Verificación manual siguiendo el protocolo de `app/README.md`:

1. Poné el clip fixture (`estado='prueba'`) en `estado='correccion_video'` con un `comentarios_video` de prueba (ej. `"Empezá 1 segundo antes"`), apuntando a una carpeta local real de un clip ya cortado (podés reusar `transcripcion_original` de un clip real existente para que la correlación encuentre carpeta).
2. Run: `cd pipeline && python reprocesar_video.py --clip-id <id-del-fixture>`
3. Expected: imprime la carpeta encontrada, el nuevo rango interpretado y termina en `[dry-run] Se respaldaría...` sin tocar ningún archivo ni la fila de Supabase.
4. Volvé a poner el fixture en `estado='prueba'` al terminar (protocolo de `app/README.md`).

- [ ] **Step 4: Commit**

```bash
git add pipeline/reprocesar_video.py pipeline/correlacionar_clip.py pipeline/reprocesar_subtitulos.py
git commit -m "reprocesar_video.py: ejecutar la corrección (--apply) reusando cortar_clip.py/publicar.py"
```

---

### Task 5: CLI de `reprocesar_video.py` (`--apply`/`--clip-id`/`--uno`) con contrato de exit codes

**Files:**
- Modify: `pipeline/reprocesar_video.py`

**Interfaces:**
- Produces: contrato de exit code de `reprocesar_video.py` cuando se corre como script: `0` = no había ninguna fila pendiente (nada que hacer), `1` = al menos una fila falló o abortó, `3` = se procesó al menos una fila y todas terminaron en éxito. Este contrato lo consume `auto_procesar.ps1` en la Task 6 para decidir qué mail mandar.

- [ ] **Step 1: Implementar `main()`**

Agregar al final de `pipeline/reprocesar_video.py`:

```python
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
        help="Procesa solo la fila pendiente más antigua (pensado para el disparador "
             "automático: deja que la siguiente corrida procese el resto).",
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

    if args.uno:
        filas = filas[:1]

    print(f"{'[APPLY]' if args.apply else '[DRY-RUN]'} {len(filas)} clip(s) pendiente(s) de corrección.")
    resultados = [procesar_fila(row, apply=args.apply) for row in filas]

    if all(resultados):
        sys.exit(3 if args.apply else 0)
    sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verificar el contrato de exit codes a mano**

Run: `cd pipeline && python reprocesar_video.py; echo "exit=$?"`
Expected (si no hay filas pendientes reales en Supabase): imprime `No hay clips pendientes de corrección de video.` y `exit=0`.

Run: `cd pipeline && python reprocesar_video.py --clip-id id-que-no-existe; echo "exit=$?"`
Expected: imprime `El clip id-que-no-existe no está en estado='correccion_video'.` y `exit=0` (ningún clip pendiente con ese id no es una falla, es "nada que hacer").

- [ ] **Step 3: Commit**

```bash
git add pipeline/reprocesar_video.py
git commit -m "reprocesar_video.py: CLI (--apply/--clip-id/--uno) con contrato de exit codes 0/1/3"
```

---

### Task 6: Enganchar en el disparador automático (`auto_procesar.ps1`) + documentar

**Files:**
- Modify: `pipeline/auto_procesar.ps1`
- Modify: `pipeline/README.md`

**Interfaces:**
- Consumes: contrato de exit codes de `reprocesar_video.py` (Task 5): `0` = nada pendiente (no mandar mail), `1` = falla (mail solo al dueño con tail del log), `3` = corregido con éxito (mail al equipo).

- [ ] **Step 1: Agregar el bloque nuevo a `auto_procesar.ps1`**

En `pipeline/auto_procesar.ps1`, después del `foreach ($rec in $candidatos) { ... }` (línea 109, antes del final del archivo), agregar:

```powershell
# --- Corrección automática de in/out points pedida por el equipo editorial ---
# Un solo clip por corrida (--uno), igual que el procesamiento de
# grabaciones más arriba: si hay más de uno pendiente, la siguiente
# corrida (5 min después) procesa el resto.
$logCorreccion = Join-Path $LogsDir "correccion_video.log"
Push-Location $PipelineDir
try {
    & python reprocesar_video.py --apply --uno *>> $logCorreccion
    $exitCode = $LASTEXITCODE
} finally {
    Pop-Location
}

if ($exitCode -eq 3) {
    Enviar-Alerta "Rayando el CDA: se aplicó una corrección de video" `
        "Se aplicó un pedido de corrección de video automáticamente. Entrá a la app para revisar el clip corregido: $AppUrl`n`nLog: $logCorreccion" `
        $TeamEmails
} elseif ($exitCode -eq 1) {
    $tail = Obtener-TailLog $logCorreccion
    Enviar-Alerta "Rayando el CDA: falló la corrección automática de video" `
        "Falló o no se pudo interpretar con confianza un pedido de corrección de video.`n`nÚltimas líneas del log ($logCorreccion):`n$tail`n`nEl clip queda en estado='correccion_video' sin tocar; revisar y corregir a mano si hace falta (ver pipeline/README.md)."
}
# exitCode 0 (nada pendiente): no se manda mail.
```

- [ ] **Step 2: Documentar en `pipeline/README.md`**

En `pipeline/README.md`, dentro de la sección "## Disparador automático (Task Scheduler)" (después del párrafo de "Notificaciones por mail"), agregar:

```markdown
**Corrección automática de video:** además de procesar grabaciones
nuevas, cada corrida también revisa si hay algún clip en
`estado='correccion_video'` (pedido de ajustar el in/out point vía
`comentarios_video` en la app de revisión) y, si lo hay, corre
`reprocesar_video.py --apply --uno` para interpretarlo con IA y volver a
cortar el clip solo. Si la IA no tiene confianza en el pedido, o no se
puede encontrar la carpeta local del clip sin ambigüedad, el clip queda
sin tocar en `estado='correccion_video'` y llega un mail solo a
`seba.pino.v@gmail.com` con el detalle — nunca se adivina un corte. Si
sale bien, el clip vuelve a `estado='pendiente'` y el equipo recibe el
mismo tipo de aviso que al terminar de procesar una grabación nueva.
```

- [ ] **Step 3: Commit**

```bash
git add pipeline/auto_procesar.ps1 pipeline/README.md
git commit -m "Enganchar reprocesar_video.py al disparador automático (auto_procesar.ps1)"
```
