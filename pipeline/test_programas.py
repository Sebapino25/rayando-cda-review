"""Tests del mecanismo multi-programa (config.PROGRAMA). Cada caso corre en un
subproceso porque config se evalúa una sola vez al importarse."""
import json
import os
import subprocess
import sys
from pathlib import Path

PIPELINE = Path(__file__).parent


def _py(codigo: str, programa: str | None, extra_env: dict | None = None) -> str:
    env = {k: v for k, v in os.environ.items() if k != "PROGRAMA"}
    if programa:
        env["PROGRAMA"] = programa
    env.update(extra_env or {})
    r = subprocess.run(
        [sys.executable, "-c", codigo], cwd=PIPELINE, env=env,
        capture_output=True, text=True, encoding="utf-8",
    )
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def test_default_es_rayando_sin_cambios():
    out = _py(
        "import config, detectar_momentos as d, copys_ia as c, corregir_nombres as n;"
        "print(config.PROGRAMA, config.CANDIDATOS_MAX_N, config.SUPABASE_SCHEMA,"
        " config.PORTADA_MARCA_TEXTO, config.PROMPT_DETECCION is None,"
        " 'Rayando el CDA' in d.SYSTEM_PROMPT, 'entre 5 y 8' in d.SYSTEM_PROMPT,"
        " 'Rayando el CDA' in c.SYSTEM_PROMPT,"
        " n.construir_initial_prompt().startswith('Rayando el CDA, programa de Universidad de Chile. '))",
        None,
    )
    assert out == "rayando 8 rayando_cda RAYANDO EL CDA True True True True True"


def test_spa_aplica_perfil():
    out = _py(
        "import config, detectar_momentos as d, copys_ia as c, corregir_nombres as n;"
        "print(config.PROGRAMA, config.CANDIDATOS_MAX_N, config.SUPABASE_SCHEMA,"
        " config.PORTADA_MARCA_TEXTO, config.CIERRE_VERTICAL_FILES, config.AUTO_PUBLICAR_INSTAGRAM,"
        " config.PORTADA_VS_BADGE_COLOR, config.SUPABASE_CLIPS_VIDEO_BUCKET)",
        "spa",
    )
    assert out == "spa 7 siempre_pasa_algo SIEMPRE PASA ALGO [] False (228, 50, 220) clips-video-spa"


def test_spa_prompts_sin_rayando_ni_llaves_sueltas():
    out = _py(
        "import config, detectar_momentos as d, copys_ia as c;"
        "p=d.SYSTEM_PROMPT;"
        "print('SPAreírse' in p, 'entre 4 y 7' in p, 'entre 15 y 90' in p,"
        " '{' in p or '}' in p, 'Rayando' in p or 'Rayando' in c.SYSTEM_PROMPT,"
        " 'SPAreírse' in c.SYSTEM_PROMPT)",
        "spa",
    )
    assert out == "True True True False False True"


def test_spa_diccionario_corrige_y_no_toca_rayando():
    out = _py(
        "import corregir_nombres as n;"
        "print(n.corregir_texto('jaaland y mago jimenez en spa reirse'))",
        "spa",
    )
    assert out == "Haaland y Mago Jiménez en SPAreírse"
    out = _py("import corregir_nombres as n; print(n.corregir_texto('wanders'))", None)
    assert out == "Wanderers"


def test_clave_desconocida_en_perfil_falla_fuerte(tmp_path):
    perfil = PIPELINE / "programas" / "_tmp_typo.json"
    perfil.write_text(json.dumps({"config": {"CANDIDATOS_MAX_NN": 3}}), encoding="utf-8")
    try:
        r = subprocess.run(
            [sys.executable, "-c", "import config"], cwd=PIPELINE,
            env={**os.environ, "PROGRAMA": "_tmp_typo"}, capture_output=True, text=True,
        )
        assert r.returncode != 0 and "CANDIDATOS_MAX_NN" in r.stderr
    finally:
        perfil.unlink()
