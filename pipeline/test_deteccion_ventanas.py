"""Tests de la detección por ventanas (detectar_momentos). No llaman a la API:
se reemplaza _llamar_modelo por un falso."""
import config
import detectar_momentos as d


def _segmentos(n=400, paso=10.0):
    # n segmentos de `paso` segundos cada uno; texto con punto final.
    return [{"start": i * paso, "end": (i + 1) * paso, "text": f"segmento {i}."} for i in range(n)]


def test_ventanas_cubren_todo_con_solape():
    segs = _segmentos(400)  # 4000 s
    v = d._ventanas(segs, 900, 90)
    assert v[0][0] == 0 and v[-1][1] == 400
    # cada ventana (salvo la última) incluye 90 s de solape: 900+90 = 99 segmentos
    assert v[0] == (0, 99)
    # sin huecos: el inicio de cada ventana es anterior o igual al fin de la previa
    for (a0, a1), (b0, b1) in zip(v, v[1:]):
        assert b0 <= a1


def test_cola_corta_se_une_a_la_ventana_anterior():
    segs = _segmentos(190)  # 1900 s: sobran 100 s (< 300) después de 2 ventanas
    v = d._ventanas(segs, 900, 90)
    assert len(v) == 2 and v[-1][1] == 190


def test_sin_ventana_devuelve_todo():
    segs = _segmentos(50)
    assert d._ventanas(segs, 0, 90) == [(0, 50)]


def test_lista_conserva_indices_globales_y_oracion_previa():
    segs = _segmentos(10)
    segs[4]["text"] = "sin punto"
    lista = d._construir_lista_segmentos(segs, 5, 7).splitlines()
    assert lista[0].startswith("[5] ") and "empieza_oracion=false" in lista[0]
    assert lista[-1].startswith("[6] ")


def _cand(i0, i1, puntaje, segs):
    return d._validar_candidatos(
        [{"idx_inicio": i0, "idx_fin": i1, "razon": "x", "puntaje": puntaje}], segs
    )[0]


def test_combinar_elige_por_puntaje_y_descarta_solapados():
    segs = _segmentos(400)
    a = _cand(10, 14, 6, segs)    # 50 s
    b = _cand(12, 16, 9, segs)    # se superpone con a, mejor puntaje
    c = _cand(200, 204, 7, segs)
    e = _cand(300, 304, 5, segs)
    out = d._combinar_ventanas([[a], [b, c], [e]], pool_n=2)
    assert [x.idx_inicio for x in out] == [12, 200]  # b y c, en orden cronológico


def test_validar_descarta_fuera_de_ventana():
    segs = _segmentos(400)
    crudos = [{"idx_inicio": 5, "idx_fin": 9, "razon": "x", "puntaje": 8}]
    assert d._validar_candidatos(crudos, segs, None, 100, 199) == []
    assert len(d._validar_candidatos(crudos, segs, None, 0, 99)) == 1


def test_detectar_por_ventanas_integra_todo(monkeypatch):
    segs = _segmentos(400)  # 4000 s -> 5 ventanas de 900 s (la cola de 400 s se queda)
    monkeypatch.setattr(config, "DETECCION_VENTANA_SEG", 900)
    monkeypatch.setattr(config, "DETECCION_VENTANA_SOLAPE_SEG", 90)
    monkeypatch.setattr(config, "DETECCION_POR_VENTANA_MAX", 3)
    monkeypatch.setattr(config, "CANDIDATOS_POOL_N", 4)
    monkeypatch.setattr(config, "PROMPT_DETECCION", "entre {min_n} y {max_n} / {dur_min} {dur_max}")
    llamadas = []

    def falso(system, mensaje, schema):
        llamadas.append((system, mensaje, schema))
        # primer índice de la lista de esta ventana
        primero = int(mensaje.split("\n[", 1)[1].split("]", 1)[0])
        return [
            {"idx_inicio": primero + 2, "idx_fin": primero + 6, "razon": "r", "puntaje": 5 + (primero // 100) % 5},
            {"idx_inicio": primero + 20, "idx_fin": primero + 24, "razon": "r2", "puntaje": 3},
        ]

    monkeypatch.setattr(d, "_llamar_modelo", falso)
    out = d.detectar_candidatos(segs)
    assert len(llamadas) >= 4
    assert "entre 0 y 3" in llamadas[0][0] and "NOTA" in llamadas[0][0]
    assert "puntaje" in llamadas[0][2]["properties"]["candidatos"]["items"]["required"]
    assert len(out) == 4
    assert [c.timestamp_inicio for c in out] == sorted(c.timestamp_inicio for c in out)
    assert all(c.puntaje is not None for c in out)


def test_sin_ventanas_usa_una_sola_llamada(monkeypatch):
    segs = _segmentos(50)
    monkeypatch.setattr(config, "DETECCION_VENTANA_SEG", 0)
    n = []

    def falso(system, mensaje, schema):
        n.append(1)
        return [{"idx_inicio": 1, "idx_fin": 5, "razon": "r"}]

    monkeypatch.setattr(d, "_llamar_modelo", falso)
    out = d.detectar_candidatos(segs)
    assert len(n) == 1 and len(out) == 1 and out[0].puntaje is None
