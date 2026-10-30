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


def test_recda_es_alias_de_rayando():
    out = _py("import config; print(config.PROGRAMA, config.SUPABASE_SCHEMA, config.DIA_PROGRAMA, config.REDES)", "recda")
    assert out == "rayando rayando_cda 0 ('youtube', 'instagram', 'tiktok')"


def test_spa_trae_redes_y_dia():
    out = _py("import config; print(config.DIA_PROGRAMA, config.REDES)", "spa")
    assert out == "3 ('youtube',)"


def test_bandera_programa_fija_la_variable_antes_de_config():
    codigo = (
        "import sys; sys.argv = ['x', 'archivo.mkv', '--programa', 'spa', '--dry-run'];"
        "import programa_cli, config; print(config.PROGRAMA, sys.argv[1:])"
    )
    assert _py(codigo, None) == "spa ['archivo.mkv', '--dry-run']"
    codigo = "import sys; sys.argv = ['x', '--programa=recda']; import programa_cli, config; print(config.PROGRAMA, sys.argv[1:])"
    assert _py(codigo, None) == "rayando []"
    # Sin bandera manda la variable de entorno, como antes.
    assert _py("import sys; sys.argv = ['x']; import programa_cli, config; print(config.PROGRAMA)", "spa") == "spa"


def test_youtube_de_spa_no_se_hereda_de_recda(tmp_path):
    # Sin YOUTUBE_CLIENT_ID/SECRET propios en .env.spa, SPA no puede subir a
    # YouTube (usaría el proyecto/canal de Recda): publicar lo detecta.
    env_spa = tmp_path / ".env.spa"
    env_spa.write_text("YOUTUBE_TOKEN_FILE=youtube_token_spa.json\n", encoding="utf-8")
    codigo = (
        "import config, publicar, pathlib;"
        f"config.PROJECT_DIR = pathlib.Path(r'{tmp_path}');"
        "print(publicar.youtube_faltante())"
    )
    out = _py(codigo, "spa")
    assert "YOUTUBE_CLIENT_ID" in out and "YOUTUBE_CLIENT_SECRET" in out and "TOKEN_FILE" not in out
    env_spa.write_text("YOUTUBE_CLIENT_ID=a\nYOUTUBE_CLIENT_SECRET=b\nYOUTUBE_TOKEN_FILE=no_existe_spa.json\n", encoding="utf-8")
    out = _py(codigo, "spa", {"YOUTUBE_TOKEN_FILE": "no_existe_spa.json"})
    assert "autorizar_youtube.py --programa spa" in out
    # Rayando no se revisa (comportamiento de siempre).
    assert _py("import publicar; print(publicar.youtube_faltante())", None) == "None"
