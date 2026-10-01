"""Prueba AISLADA de interpretar_correccion: mockea el cliente de
Anthropic (nunca llama a la API real) y verifica que (a) con una
respuesta confiada devuelve los timestamps correctos calzados a
segmentos reales, (b) con confianza=false no inventa timestamps, (c)
si el modelo devuelve índices inválidos, se trata igual que "sin
confianza" (no se usan índices fuera de rango), y (d) si la respuesta se
cortó por límite de tokens se lanza un InterpretacionError específico de
truncamiento (no el genérico de "formato inesperado").

El mock imita client.messages.stream() (context manager con
get_final_message), que es como llama interpretar_correccion desde que
usa streaming + max_tokens=16000, igual que detectar_momentos.py.

Uso:
    python test_interpretar_correccion.py
"""
from __future__ import annotations

import json
from contextlib import contextmanager
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


def _fake_client(payload: dict, stop_reason: str = "end_turn"):
    """Cliente falso cuyo messages.stream(...) es un context manager con
    get_final_message(), como el del SDK real."""
    respuesta = _fake_response(payload, stop_reason)

    @contextmanager
    def stream(**kwargs):
        yield SimpleNamespace(get_final_message=lambda: respuesta)

    return SimpleNamespace(messages=SimpleNamespace(stream=stream))


def test_confiado() -> None:
    payload = {"confianza": True, "idx_inicio": 1, "idx_fin": 2, "motivo": "Empieza en 'Hoy vamos...'"}
    fake_client = _fake_client(payload)
    with patch.object(ic, "_client", lambda: fake_client):
        resultado = ic.interpretar_correccion("Empezá desde que dice 'Hoy vamos'", SEGMENTS)
    assert resultado.confianza is True
    assert resultado.timestamp_inicio == 2.0, resultado.timestamp_inicio
    assert resultado.timestamp_fin == 9.0, resultado.timestamp_fin


def test_rango_actual_llega_al_modelo() -> None:
    """Pedidos relativos ("15 segundos antes") dependen de que el modelo sepa
    dónde empieza/termina el clip hoy: el rango debe ir en el mensaje."""
    capturado = {}
    respuesta = _fake_response({"confianza": True, "cambia_corte": True, "idx_inicio": 0, "idx_fin": 2, "titulo_nuevo": "", "motivo": "x"})

    @contextmanager
    def stream(**kwargs):
        capturado.update(kwargs)
        yield SimpleNamespace(get_final_message=lambda: respuesta)

    fake_client = SimpleNamespace(messages=SimpleNamespace(stream=stream))
    with patch.object(ic, "_client", lambda: fake_client):
        ic.interpretar_correccion("que parta 15 segundos antes", SEGMENTS, inicio_actual=5.5, fin_actual=9.0)
        con = capturado["messages"][0]["content"]
        ic.interpretar_correccion("que parta 15 segundos antes", SEGMENTS)
        sin = capturado["messages"][0]["content"]
    assert "Rango actual del clip: 5.5s -> 9.0s" in con, con
    assert "Rango actual" not in sin
    assert "Rango actual del clip" in ic.SYSTEM_PROMPT


def test_sin_confianza() -> None:
    payload = {"confianza": False, "idx_inicio": 0, "idx_fin": 0, "motivo": "No encuentro esa frase en la transcripción."}
    fake_client = _fake_client(payload)
    with patch.object(ic, "_client", lambda: fake_client):
        resultado = ic.interpretar_correccion("Cortá donde dice algo que no está", SEGMENTS)
    assert resultado.confianza is False
    assert resultado.timestamp_inicio is None
    assert resultado.timestamp_fin is None
    assert "No encuentro" in resultado.motivo


def test_indices_invalidos_se_tratan_como_sin_confianza() -> None:
    payload = {"confianza": True, "idx_inicio": 5, "idx_fin": 9, "motivo": "fuera de rango"}
    fake_client = _fake_client(payload)
    with patch.object(ic, "_client", lambda: fake_client):
        resultado = ic.interpretar_correccion("pedido cualquiera", SEGMENTS)
    assert resultado.confianza is False
    assert resultado.timestamp_inicio is None


def test_truncado_por_max_tokens() -> None:
    """stop_reason='max_tokens' tiene que dar un error de TRUNCAMIENTO, no el
    genérico de 'formato inesperado' (que llevaría a buscar un bug de schema
    inexistente)."""
    payload = {"confianza": True, "idx_inicio": 1, "idx_fin": 2, "motivo": "cortado"}
    fake_client = _fake_client(payload, stop_reason="max_tokens")
    with patch.object(ic, "_client", lambda: fake_client):
        try:
            ic.interpretar_correccion("pedido cualquiera", SEGMENTS)
        except ic.InterpretacionError as e:
            mensaje = str(e)
        else:
            raise AssertionError("esperaba InterpretacionError por truncamiento")
    assert "max_tokens" in mensaje, mensaje
    assert "formato esperado" not in mensaje, mensaje


def test_solo_titulo_no_toca_el_corte() -> None:
    payload = {
        "confianza": True, "cambia_corte": False, "idx_inicio": 0, "idx_fin": 0,
        "titulo_nuevo": '"El país es anti U de Chile"', "motivo": "Cambio de título",
    }
    fake_client = _fake_client(payload)
    with patch.object(ic, "_client", lambda: fake_client):
        resultado = ic.interpretar_correccion('Cambiar el título por "El país es anti U de Chile"', SEGMENTS)
    assert resultado.confianza is True
    assert resultado.timestamp_inicio is None and resultado.timestamp_fin is None
    # Sin las comillas envolventes, texto literal.
    assert resultado.titulo_nuevo == "El país es anti U de Chile", resultado.titulo_nuevo


def test_corte_y_titulo_juntos() -> None:
    payload = {
        "confianza": True, "cambia_corte": True, "idx_inicio": 1, "idx_fin": 1,
        "titulo_nuevo": "Clásico  universitario", "motivo": "Corte + título",
    }
    fake_client = _fake_client(payload)
    with patch.object(ic, "_client", lambda: fake_client):
        resultado = ic.interpretar_correccion("pedido", SEGMENTS)
    assert resultado.confianza is True
    assert (resultado.timestamp_inicio, resultado.timestamp_fin) == (2.0, 5.5)
    assert resultado.titulo_nuevo == "Clásico universitario"


def test_sin_corte_ni_titulo_es_sin_confianza() -> None:
    payload = {
        "confianza": True, "cambia_corte": False, "idx_inicio": 0, "idx_fin": 0,
        "titulo_nuevo": "  ", "motivo": "nada",
    }
    fake_client = _fake_client(payload)
    with patch.object(ic, "_client", lambda: fake_client):
        resultado = ic.interpretar_correccion("pedido", SEGMENTS)
    assert resultado.confianza is False
    assert resultado.titulo_nuevo is None


def main() -> None:
    test_confiado()
    test_rango_actual_llega_al_modelo()
    test_sin_confianza()
    test_indices_invalidos_se_tratan_como_sin_confianza()
    test_truncado_por_max_tokens()
    test_solo_titulo_no_toca_el_corte()
    test_corte_y_titulo_juntos()
    test_sin_corte_ni_titulo_es_sin_confianza()
    print("OK: interpretar_correccion cubre confianza / sin-confianza / índices inválidos / truncamiento / título.")


if __name__ == "__main__":
    main()
