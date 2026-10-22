"""Número de capítulo de cada programa (PLAN-CAPSULAS.md, Fase 1).

Reglas:
- La fecha del programa es la de inicio de la grabación según el nombre del
  mkv de OBS ("2026-10-26 22-53-58.mkv"). Si la grabación empezó un martes
  antes de las 06:00, cuenta como el lunes anterior (programa que se pasó de
  la medianoche, o un corte de OBS de madrugada).
- Lunes: si ya hay un capítulo con esa fecha, se reusa (reprocesar o varios
  mkv la misma noche no suman); si no, se crea MAX(numero)+1 como 'normal'.
- Otro día: sin capítulo, salvo --extraordinario (crea MAX+1 como
  'extraordinario', o reusa el de esa fecha si ya existe) o --capitulo N
  (fuerza un número que ya existe).
- Una fecha anterior al último capítulo registrado que no tenga capítulo
  propio (ej. reprocesar un programa viejo) NO crea uno nuevo: quedaría con
  el número de la semana siguiente. Se avisa y queda sin capítulo, salvo
  --capitulo N.

La decisión (resolver_capitulo) es pura y tiene pruebas en
test_capitulos.py; asignar_capitulo() la conecta con Supabase
(rayando_cda.capitulos, ver supabase_migration_capitulos.sql).
"""

from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass
from pathlib import Path

import config

_INICIO_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\d{2})-(\d{2})-(\d{2})")

# Hasta qué hora del martes una grabación todavía cuenta como el lunes.
HORA_CORTE_MADRUGADA = 6


class CapituloError(Exception):
    """Combinación de parámetros/estado que no permite decidir el capítulo."""


@dataclass(frozen=True)
class Decision:
    numero: int | None
    crear: bool = False  # True = hay que insertar el capítulo en la tabla
    tipo: str | None = None  # 'normal' | 'extraordinario' (solo si crear)
    motivo: str = ""


def inicio_grabacion(video_path: Path) -> _dt.datetime:
    """Fecha y hora de inicio según el nombre que pone OBS. Si el nombre no
    tiene ese formato, cae a la fecha de modificación del archivo (mismo
    fallback que cortar_clip.program_date_from_name)."""
    m = _INICIO_RE.match(video_path.stem)
    if m:
        fecha, hh, mm, ss = m.groups()
        return _dt.datetime.fromisoformat(f"{fecha}T{hh}:{mm}:{ss}")
    return _dt.datetime.fromtimestamp(video_path.stat().st_mtime)


def fecha_programa(inicio: _dt.datetime) -> _dt.date:
    if inicio.weekday() == 1 and inicio.hour < HORA_CORTE_MADRUGADA:
        return inicio.date() - _dt.timedelta(days=1)
    return inicio.date()


def resolver_capitulo(
    fecha: _dt.date,
    existentes: dict[int, _dt.date],
    extraordinario: bool = False,
    capitulo_forzado: int | None = None,
) -> Decision:
    """Decide el capítulo de un programa. `existentes` es {numero: fecha} de
    rayando_cda.capitulos."""
    if extraordinario and capitulo_forzado is not None:
        raise CapituloError("--extraordinario y --capitulo no se pueden usar juntos.")

    if capitulo_forzado is not None:
        if capitulo_forzado not in existentes:
            raise CapituloError(
                f"El capítulo {capitulo_forzado} no existe en la tabla capitulos "
                "(--capitulo solo fuerza un número ya registrado)."
            )
        return Decision(capitulo_forzado, motivo=f"forzado con --capitulo {capitulo_forzado}")

    por_fecha = {f: n for n, f in existentes.items()}
    if fecha in por_fecha:
        return Decision(por_fecha[fecha], motivo=f"ya existía un capítulo con fecha {fecha}")

    es_lunes = fecha.weekday() == 0
    if not es_lunes and not extraordinario:
        return Decision(None, motivo=f"{fecha} no es lunes y no se pasó --extraordinario")

    if not existentes:
        raise CapituloError("La tabla capitulos está vacía: falta la semilla (ver supabase_migration_capitulos.sql).")

    ultima_fecha = max(existentes.values())
    if fecha < ultima_fecha:
        return Decision(
            None,
            motivo=(
                f"{fecha} es anterior al último capítulo registrado ({ultima_fecha}) y no tiene "
                "capítulo propio: no se crea uno nuevo. Usa --capitulo N si corresponde."
            ),
        )

    tipo = "normal" if es_lunes else "extraordinario"
    numero = max(existentes) + 1
    return Decision(numero, crear=True, tipo=tipo, motivo=f"capítulo nuevo ({tipo}) para {fecha}")


def _leer_existentes(supabase) -> dict[int, _dt.date]:
    import publicar

    filas = publicar.reintentar_transitorio(
        supabase.table(config.SUPABASE_CAPITULOS_TABLE).select("numero,fecha").execute
    ).data
    return {int(f["numero"]): _dt.date.fromisoformat(f["fecha"]) for f in filas}


def asignar_capitulo(
    video_path: Path,
    extraordinario: bool = False,
    capitulo_forzado: int | None = None,
    dry_run: bool = False,
) -> int | None:
    """Resuelve el capítulo de una grabación y, si hace falta, lo crea en
    Supabase (salvo dry_run). Devuelve el número o None."""
    import publicar

    inicio = inicio_grabacion(video_path)
    fecha = fecha_programa(inicio)
    supabase = publicar.get_supabase_client()
    existentes = _leer_existentes(supabase)
    decision = resolver_capitulo(fecha, existentes, extraordinario, capitulo_forzado)

    print(f"Capítulo: grabación iniciada {inicio:%Y-%m-%d %H:%M} -> programa del {fecha}: ", end="")
    if decision.numero is None:
        print(f"sin capítulo ({decision.motivo}).")
        return None
    if not decision.crear:
        print(f"{decision.numero} ({decision.motivo}).")
        return decision.numero
    if dry_run:
        print(f"{decision.numero} — [dry-run] se crearía ({decision.motivo}).")
        return decision.numero

    payload = {"numero": decision.numero, "fecha": fecha.isoformat(), "tipo": decision.tipo}
    try:
        publicar.reintentar_transitorio(
            supabase.table(config.SUPABASE_CAPITULOS_TABLE).insert(payload).execute
        )
    except Exception:
        # Otra corrida pudo haberlo creado entre la lectura y el insert
        # (fecha y número son únicos): si ya está esa fecha, se usa esa.
        existentes = _leer_existentes(supabase)
        reusado = {f: n for n, f in existentes.items()}.get(fecha)
        if reusado is None:
            raise
        print(f"{reusado} (lo creó otra corrida recién).")
        return reusado
    print(f"{decision.numero} ({decision.motivo}).")
    return decision.numero
