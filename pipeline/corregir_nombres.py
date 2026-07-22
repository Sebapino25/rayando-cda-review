"""Corrección de nombres propios en subtítulos (.srt/.ass) y transcripciones (.json).

Se apoya en `diccionario.json` (términos correctos del universo de "Rayando el
CDA" + variantes mal transcritas ya detectadas). Aplica:

1. Reemplazo exacto de "correcciones_especiales" (frases completas puntuales).
2. Reemplazo exacto de variantes conocidas por término (palabra o frase completa,
   case-insensitive, respetando límites de palabra).
3. Fuzzy matching palabra por palabra contra la forma "correcto" de cada término,
   para variantes no listadas todavía (typos nuevos de Whisper).

Se usa como paso de post-procesamiento automático al final de `transcribir.py`
(sobre el .srt/.json maestro) y también se aplica de nuevo al generar los
subtítulos de cada clip en `cortar_clip.py` (capa extra de seguridad, barata).

También se puede correr manualmente:

    python corregir_nombres.py "ruta\\archivo.srt" "ruta\\archivo.json"
"""

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

DICCIONARIO_PATH = Path(__file__).parent / "diccionario.json"

STOPWORDS = {
    "la", "el", "los", "las", "de", "del", "que", "y", "a", "en", "un", "una",
    "es", "con", "por", "no", "se", "lo", "su", "mas", "más", "para", "como",
    "pero", "les", "les", "eso", "esa", "ese", "esta", "este",
}

FUZZY_UMBRAL = 0.84
FUZZY_MAX_DIFERENCIA_LARGO = 2
FUZZY_LARGO_MINIMO = 5


def cargar_diccionario(path: Path = DICCIONARIO_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalizar(s: str) -> str:
    return s.strip().lower()


def _construir_indices(diccionario: dict):
    variantes_frase = []  # (variante_normalizada, correcto), multi-palabra
    variantes_palabra = []  # (variante_normalizada, correcto), 1 palabra
    canonicos_palabra = []  # (correcto_normalizado, correcto), para fuzzy

    for termino in diccionario.get("terminos", []):
        correcto = termino["correcto"]
        if " " not in correcto:
            canonicos_palabra.append((_normalizar(correcto), correcto))
        for variante in termino.get("variantes", []):
            n = _normalizar(variante)
            if not n:
                continue
            if " " in n:
                variantes_frase.append((n, correcto))
            else:
                variantes_palabra.append((n, correcto))

    variantes_frase.sort(key=lambda par: -len(par[0].split()))
    return variantes_frase, variantes_palabra, canonicos_palabra


def _es_similar(a: str, b: str) -> bool:
    if abs(len(a) - len(b)) > FUZZY_MAX_DIFERENCIA_LARGO:
        return False
    return difflib.SequenceMatcher(None, a, b).ratio() >= FUZZY_UMBRAL


def corregir_texto(texto: str, diccionario: dict | None = None) -> str:
    """Aplica correcciones especiales, de diccionario y fuzzy sobre un string."""
    if not texto:
        return texto
    if diccionario is None:
        diccionario = cargar_diccionario()

    resultado = texto

    for correccion in diccionario.get("correcciones_especiales", []):
        patron = re.compile(re.escape(correccion["buscar"]), re.IGNORECASE)
        resultado = patron.sub(correccion["reemplazar"], resultado)

    variantes_frase, variantes_palabra, canonicos_palabra = _construir_indices(diccionario)

    for variante, correcto in variantes_frase:
        patron = re.compile(r"(?<!\w)" + re.escape(variante) + r"(?!\w)", re.IGNORECASE)
        resultado = patron.sub(correcto, resultado)

    for variante, correcto in variantes_palabra:
        patron = re.compile(r"(?<!\w)" + re.escape(variante) + r"(?!\w)", re.IGNORECASE)
        resultado = patron.sub(correcto, resultado)

    def _fuzzy_token(m: re.Match) -> str:
        palabra = m.group(0)
        low = _normalizar(palabra)
        if low in STOPWORDS or len(low) < FUZZY_LARGO_MINIMO:
            return palabra
        for canon_norm, canon in canonicos_palabra:
            if low == canon_norm:
                return palabra if palabra == canon else canon
            if _es_similar(canon_norm, low):
                return canon
        return palabra

    resultado = re.sub(r"[^\W\d_]+", _fuzzy_token, resultado, flags=re.UNICODE)
    return resultado


def corregir_srt(path: Path, diccionario: dict | None = None) -> int:
    if diccionario is None:
        diccionario = cargar_diccionario()
    contenido = path.read_text(encoding="utf-8")
    bloques = contenido.split("\n\n")
    cambios = 0
    nuevos_bloques = []
    for bloque in bloques:
        lineas = bloque.split("\n")
        if len(lineas) >= 3 and "-->" in lineas[1]:
            texto_original = "\n".join(lineas[2:])
            texto_corregido = corregir_texto(texto_original, diccionario)
            if texto_corregido != texto_original:
                cambios += 1
            nuevos_bloques.append("\n".join(lineas[:2] + [texto_corregido]))
        else:
            nuevos_bloques.append(bloque)
    path.write_text("\n\n".join(nuevos_bloques), encoding="utf-8")
    return cambios


def corregir_json(path: Path, diccionario: dict | None = None) -> int:
    if diccionario is None:
        diccionario = cargar_diccionario()
    data = json.loads(path.read_text(encoding="utf-8"))
    cambios = 0
    for segmento in data.get("segments", []):
        original = segmento.get("text", "")
        corregido = corregir_texto(original, diccionario)
        if corregido != original:
            segmento["text"] = corregido
            cambios += 1
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return cambios


_ASS_DIALOGUE_RE = re.compile(
    r"^(Dialogue: [^,]*,[^,]*,[^,]*,[^,]*,[^,]*,[^,]*,[^,]*,[^,]*,)(.*)$",
    re.MULTILINE,
)


def corregir_ass(path: Path, diccionario: dict | None = None) -> int:
    if diccionario is None:
        diccionario = cargar_diccionario()
    contenido = path.read_text(encoding="utf-8")
    cambios = 0

    def _sub(m: re.Match) -> str:
        nonlocal cambios
        prefijo, texto = m.group(1), m.group(2)
        texto_plano = texto.replace("\\N", "\n")
        corregido = corregir_texto(texto_plano, diccionario).replace("\n", "\\N")
        if corregido != texto:
            cambios += 1
        return prefijo + corregido

    nuevo = _ASS_DIALOGUE_RE.sub(_sub, contenido)
    path.write_text(nuevo, encoding="utf-8")
    return cambios


def construir_initial_prompt(diccionario: dict | None = None) -> str:
    """Frase con los términos correctos, para pasar como initial_prompt a faster-whisper."""
    if diccionario is None:
        diccionario = cargar_diccionario()
    terminos = [t["correcto"] for t in diccionario.get("terminos", [])]
    return "Rayando el CDA, programa de Universidad de Chile. " + ", ".join(terminos) + "."


def corregir_archivo(path: Path, diccionario: dict | None = None) -> int:
    if path.suffix == ".srt":
        return corregir_srt(path, diccionario)
    if path.suffix == ".json":
        return corregir_json(path, diccionario)
    if path.suffix == ".ass":
        return corregir_ass(path, diccionario)
    raise ValueError(f"Extensión no soportada para corrección: {path}")


def main():
    parser = argparse.ArgumentParser(
        description="Corrige nombres propios mal transcritos en .srt/.json/.ass usando diccionario.json"
    )
    parser.add_argument("archivos", nargs="+", help="Rutas a archivos .srt, .json o .ass")
    args = parser.parse_args()

    diccionario = cargar_diccionario()
    for archivo in args.archivos:
        p = Path(archivo)
        if not p.exists():
            print(f"  (no existe: {p})")
            continue
        try:
            n = corregir_archivo(p, diccionario)
        except ValueError as e:
            print(f"  {e}")
            continue
        print(f"{p}: {n} segmentos corregidos")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
